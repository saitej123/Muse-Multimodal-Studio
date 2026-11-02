"""LLM / paid-API cost tracking (admin only).

Every LLM or paid-API call records a usage event: which provider/model, how
many prompt/response tokens (the provider's own count when it reports one,
otherwise an estimate), and an estimated dollar cost from per-model rates.

Events are written to the SQLite table ``usage_events`` in ``workspace/sessions.db``.

Design notes:
  * Never raises into the caller - a tracking failure must not break generation.
  * Rates are per 1M tokens, overridable via ``settings`` (``.env``).
  * Reports recompute $ from the current rates, so rows stored at $0 (unknown
    model at the time) still show a useful estimate after the rate table updates.
"""
from __future__ import annotations

import contextvars
import json
import re
import time
import uuid
from functools import wraps
from contextlib import contextmanager
from typing import Iterator

from .db import _connect, _lock
from .logging_setup import log

# Set while a job pipeline (or thumbnail) runs so usage events attribute spend.
_current_job_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "cost_job_id", default=""
)


def get_job_id() -> str:
    return (_current_job_id.get() or "").strip()


@contextmanager
def job_context(job_id: str) -> Iterator[None]:
    """Attribute LLM / paid-API usage to ``job_id`` for the duration of the block."""
    token = _current_job_id.set((job_id or "").strip())
    try:
        yield
    finally:
        _current_job_id.reset(token)

def bind_context(fn):
    """Wrap ``fn`` so it runs inside the *current* context.

    Thread pools do not inherit context variables, so usage from parallel slide
    or voice calls lost its job id and never showed under "By job". Wrap the
    callable on the submitting thread: ``pool.submit(costs.bind_context(fn), x)``.
    """
    snapshot = contextvars.copy_context()

    @wraps(fn)
    def _run(*args, **kwargs):
        # A Context can only be entered by one thread at a time, so each call
        # runs in its own copy of the snapshot.
        return snapshot.copy().run(fn, *args, **kwargs)

    return _run


# Built-in default rates (USD per 1M tokens): (input_rate, output_rate).
# Admins can override any of these via .env (see config.cost_rates).
# Sources: Meta Model API and OpenAI public pricing (paid tier, standard).
_DEFAULT_RATES: dict[str, tuple[float, float]] = {
    # Meta Model API — Standard mode, USD / 1M tokens.
    # https://dev.meta.ai/docs/pricing-rate-limits
    "muse-wonder-1.0": (4.00, 20.0),
    "muse-spark-1.3": (1.25, 4.25),
    "muse-spark-1.2": (1.25, 4.25),
    "muse-spark-1.1": (1.25, 4.25),
    "muse-spark-1.3-contributor": (0.10, 0.20),
    "muse-spark-1.2-contributor": (0.10, 0.20),
    # OpenAI
    "gpt-4o": (2.50, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4.1-mini": (0.40, 1.60),
}

# Family fallbacks when an exact model id isn't listed (longest match wins).
_FAMILY_RATES: list[tuple[str, tuple[float, float]]] = [
    ("muse-spark-1.3-contributor", (0.10, 0.20)),
    ("muse-spark-1.2-contributor", (0.10, 0.20)),
    ("muse-wonder", (4.00, 20.0)),
    ("muse-spark", (1.25, 4.25)),
    ("muse-image", (0.0, 0.0)),
    ("muse", (4.00, 20.0)),
    ("gpt-4o-mini", (0.15, 0.60)),
    ("gpt-4o", (2.50, 10.0)),
    ("gpt-4.1-mini", (0.40, 1.60)),
    ("gpt-4.1", (2.0, 8.0)),
    ("gpt-4", (2.50, 10.0)),
]

# Flat USD per generated image when kind=image (or model name has "image") and
# the caller didn't count image output tokens.
# Muse Image is $0.01 per image.
_IMAGE_FLAT_USD: dict[str, float] = {
    # Muse Image is $0.01 per generated image, not per token.
    "muse-image-1.0": 0.01,
    "muse-image": 0.01,
}
_IMAGE_FLAT_DEFAULT = 0.01


def _ensure_schema() -> None:
    conn = _connect()
    with _lock:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS usage_events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ts           REAL,
                provider     TEXT,
                model        TEXT,
                kind         TEXT,
                in_tokens    INTEGER,
                out_tokens   INTEGER,
                cost_usd     REAL,
                job_id       TEXT
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_usage_job ON usage_events(job_id)")
        conn.commit()


def _normalize_model(model: str) -> str:
    return re.sub(r"\s+", "", (model or "").strip().lower())


def _rate_for(model: str) -> tuple[float, float]:
    """Return (input_rate, output_rate) USD per 1M tokens for ``model``.

    Order: explicit .env override -> exact default -> family prefix -> zero.
    """
    from .config import get_settings

    key = _normalize_model(model)
    if not key:
        return (0.0, 0.0)

    overrides = get_settings().cost_rate_map()
    if key in overrides:
        return overrides[key]
    for name, rate in overrides.items():
        if key.startswith(name) or name.startswith(key):
            return rate

    if key in _DEFAULT_RATES:
        return _DEFAULT_RATES[key]
    for name, rate in _DEFAULT_RATES.items():
        if key.startswith(name) or name.startswith(key):
            return rate

    for prefix, rate in sorted(_FAMILY_RATES, key=lambda x: len(x[0]), reverse=True):
        if prefix in key:
            return rate
    return (0.0, 0.0)


def _image_flat_for(model: str) -> float:
    key = _normalize_model(model)
    for name, usd in _IMAGE_FLAT_USD.items():
        if name in key or key.startswith(name):
            return usd
    if "image" in key:
        return _IMAGE_FLAT_DEFAULT
    return 0.0


def estimate_cost(
    *,
    provider: str,
    model: str,
    kind: str = "text",
    in_tokens: int = 0,
    out_tokens: int = 0,
) -> float:
    """Estimate USD cost for one call (0 for ollama / unknown free local)."""
    if (provider or "").lower() in {"ollama", "narration"}:
        return 0.0
    it = max(0, int(in_tokens or 0))
    ot = max(0, int(out_tokens or 0))
    kind_l = (kind or "").lower()
    model_l = _normalize_model(model)
    # Muse Voice Transcribe is $0.18 per hour. Callers pass seconds in in_tokens.
    if kind_l == "asr" or "voice-transcribe" in model_l:
        return round((it / 3600.0) * 0.18, 6)
    # Web search grounding is $2.50 per 1,000 queries.
    if kind_l == "search":
        return 0.0025
    # Muse Image is a flat per image. Token counts on that response are not billed.
    if model_l.startswith("muse-image") or (
        kind_l in {"image", "img", "thumbnail"} and "muse-image" in model_l
    ):
        return _image_flat_for(model) or 0.01
    in_rate, out_rate = _rate_for(model)
    cost = (it / 1_000_000) * in_rate + (ot / 1_000_000) * out_rate
    # Image generations often report 0 output tokens — charge a flat per image.
    if kind_l in ("image", "img", "thumbnail") or (
        "image" in model_l and not model_l.startswith("muse-image")
    ):
        if ot <= 0:
            cost += _image_flat_for(model)
    return round(cost, 6)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token) when a provider reports none."""
    return max(0, round(len(text or "") / 4))


def record(
    *,
    provider: str,
    model: str,
    kind: str = "text",
    in_tokens: int | None = None,
    out_tokens: int | None = None,
    prompt: str = "",
    output: str = "",
    job_id: str = "",
) -> None:
    """Record one usage event. Never raises.

    ``in_tokens``/``out_tokens`` are used when known; otherwise estimated from
    ``prompt``/``output`` length. ``job_id`` defaults to the active
    :func:`job_context` when omitted.
    """
    try:
        _ensure_schema()
        it = int(in_tokens if in_tokens is not None else estimate_tokens(prompt))
        ot = int(out_tokens if out_tokens is not None else estimate_tokens(output))
        cost = estimate_cost(
            provider=provider, model=model, kind=kind, in_tokens=it, out_tokens=ot
        )
        jid = (job_id or get_job_id() or "").strip()
        ts = time.time()
        conn = _connect()
        with _lock:
            conn.execute(
                "INSERT INTO usage_events (ts, provider, model, kind, in_tokens, out_tokens, cost_usd, job_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (ts, provider, model, kind, it, ot, cost, jid),
            )
            conn.commit()
        _mirror_remote(
            {
                "id": uuid.uuid4().hex, "ts": ts, "provider": provider, "model": model,
                "kind": kind, "in_tokens": it, "out_tokens": ot, "cost_usd": cost, "job_id": jid,
            }
        )
    except Exception as e:  # noqa: BLE001 - tracking must never break a run
        log.bind(task="cost").warning(f"usage record failed (ignored): {e}")


def _mirror_remote(doc: dict) -> None:
    """Costs stay in SQLite. Nothing is copied to a remote store."""
    del doc


def _job_labels(job_ids: list[str]) -> dict[str, dict]:
    """Map job_id -> {title, filename, status} from the jobs table."""
    ids = [j for j in job_ids if j]
    if not ids:
        return {}
    out: dict[str, dict] = {}
    # Synthetic topic-prep sessions (not in jobs table).
    real_ids: list[str] = []
    for jid in ids:
        if str(jid).startswith("topic-prep:"):
            slug = str(jid).split(":", 1)[-1].replace("-", " ")
            out[jid] = {
                "title": f"Topic prep · {slug}",
                "filename": "",
                "status": "prep",
            }
        else:
            real_ids.append(jid)
    if not real_ids:
        return out
    try:
        conn = _connect()
        placeholders = ",".join("?" * len(real_ids))
        with _lock:
            rows = conn.execute(
                f"SELECT id, filename, status, data FROM jobs WHERE id IN ({placeholders})",
                real_ids,
            ).fetchall()
        for r in rows:
            title = ""
            try:
                data = json.loads(r["data"] or "{}")
                content = data.get("content") or {}
                title = (
                    content.get("slide_title")
                    or content.get("title")
                    or (content.get("meta") or {}).get("title")
                    or ""
                )
            except Exception:  # noqa: BLE001
                title = ""
            out[r["id"]] = {
                "title": (title or r["filename"] or r["id"]).strip(),
                "filename": r["filename"] or "",
                "status": r["status"] or "",
            }
    except Exception as e:  # noqa: BLE001
        log.bind(task="cost").warning(f"job label lookup failed: {e}")
    return out


_EVENT_KEYS = ("ts", "provider", "model", "kind", "in_tokens", "out_tokens", "cost_usd", "job_id")


def _load_events(since: float) -> tuple[list[dict], str]:
    """Events since ``since``, read from SQLite."""
    _ensure_schema()
    conn = _connect()
    with _lock:
        rows = conn.execute(
            "SELECT ts, provider, model, kind, in_tokens, out_tokens, cost_usd, job_id "
            "FROM usage_events WHERE ts >= ?",
            (since,),
        ).fetchall()
    return [dict(r) for r in rows], "sqlite"


def storage_info(backend: str) -> dict:
    """Which store the numbers came from, for the dashboard badge."""
    return {
        "backend": backend or "sqlite",
        "mode": "local",
        "connected": False,
        "project": None,
        "collection": "usage_events",
        "warning": "",
        "pending": 0,
    }


def _blank_agg() -> dict:
    return {"c": 0, "it": 0, "ot": 0, "cost": 0.0}


def _add(agg: dict, it: int, ot: int, cost: float) -> None:
    agg["c"] += 1
    agg["it"] += it
    agg["ot"] += ot
    agg["cost"] += cost


def report(days: int = 30, *, debug: bool = False) -> dict:
    """Aggregate usage for the admin dashboard.

    Totals plus per-model, per-job/session and per-day breakdowns for the last
    ``days``. Cost is recomputed from the current rate table for every event.
    """
    days = max(1, int(days))
    try:
        since = time.time() - days * 86400
        events, backend = _load_events(since)

        total = _blank_agg()
        by_model: dict[tuple[str, str], dict] = {}
        by_job: dict[str, dict] = {}
        by_job_model: dict[tuple[str, str, str], dict] = {}
        by_day: dict[int, dict] = {}
        for e in events:
            it = int(e.get("in_tokens") or 0)
            ot = int(e.get("out_tokens") or 0)
            prov = e.get("provider") or ""
            model = e.get("model") or ""
            cost = estimate_cost(
                provider=prov, model=model, kind=e.get("kind") or "text",
                in_tokens=it, out_tokens=ot,
            )
            e["_cost"] = cost
            ts = float(e.get("ts") or 0)
            jid = (e.get("job_id") or "").strip()
            _add(total, it, ot, cost)
            _add(by_model.setdefault((prov, model), _blank_agg()), it, ot, cost)
            _add(by_day.setdefault(int(ts // 86400) * 86400, _blank_agg()), it, ot, cost)
            if jid:
                j = by_job.setdefault(jid, {**_blank_agg(), "last_ts": 0.0, "first_ts": ts})
                _add(j, it, ot, cost)
                j["last_ts"] = max(j["last_ts"], ts)
                j["first_ts"] = min(j["first_ts"], ts)
                _add(by_job_model.setdefault((jid, prov, model), _blank_agg()), it, ot, cost)

        labels = _job_labels(list(by_job))
        models_by_job: dict[str, list] = {}
        for (jid, prov, model), a in sorted(
            by_job_model.items(), key=lambda kv: (-kv[1]["cost"], -kv[1]["c"])
        ):
            models_by_job.setdefault(jid, []).append(
                {"provider": prov, "model": model, "c": a["c"], "it": a["it"],
                 "ot": a["ot"], "cost": round(a["cost"], 4)}
            )
        by_job_out = []
        for jid, a in by_job.items():
            meta = labels.get(jid) or {}
            by_job_out.append(
                {
                    "job_id": jid,
                    "title": meta.get("title") or jid,
                    "filename": meta.get("filename") or "",
                    "status": meta.get("status") or "",
                    "c": a["c"], "it": a["it"], "ot": a["ot"],
                    "cost": round(a["cost"], 4),
                    "last_ts": a["last_ts"], "first_ts": a["first_ts"],
                    "models": models_by_job.get(jid) or [],
                }
            )
        by_job_out.sort(key=lambda j: float(j.get("last_ts") or 0), reverse=True)

        out: dict = {
            "days": days,
            "calls": total["c"],
            "in_tokens": total["it"],
            "out_tokens": total["ot"],
            "cost_usd": round(total["cost"], 4),
            "by_model": [
                {"provider": p_, "model": m_, "c": a["c"], "it": a["it"], "ot": a["ot"], "cost": a["cost"]}
                for (p_, m_), a in sorted(by_model.items(), key=lambda kv: (-kv[1]["cost"], -kv[1]["c"]))
            ],
            "by_job": by_job_out,
            "by_day": [
                {"day": d, "calls": a["c"], "cost_usd": round(a["cost"], 4)}
                for d, a in sorted(by_day.items(), reverse=True)
            ],
            "storage": storage_info(backend),
            "rates_note": "Estimates use Meta Model API list prices and the token counts Muse reports.",
        }
        if debug:
            recent = sorted(events, key=lambda e: float(e.get("ts") or 0), reverse=True)[:250]
            out["debug_events"] = [
                {**{k: e.get(k) for k in _EVENT_KEYS}, "cost_usd": e.get("_cost", 0.0)} for e in recent
            ]
        return out
    except Exception as e:  # noqa: BLE001
        log.bind(task="cost").warning(f"usage report failed: {e}")
        return {
            "days": days, "calls": 0, "in_tokens": 0, "out_tokens": 0, "cost_usd": 0.0,
            "by_model": [], "by_job": [], "by_day": [],
            "storage": storage_info("error"), "error": str(e)[:200],
        }
