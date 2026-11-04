"""Trending AI topics for the admin Cron input panel.

Pulls a short pulse from Hacker News, AIM, AI newsletters, lab blogs, and
tech press, then asks Muse for the top ~4 video topics with
trend scores. Users can also search for a custom topic.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_setup import log
from ..pipeline import topic_prep

_LOG = log.bind(task="auto-topics")
# Trending list auto-refreshes from the live pulse when older than this (seconds).
_CACHE_TTL = 3600
_TRENDING_LIMIT = 4
_SEED_TOPICS = [
    "Agentic AI workflows that actually ship",
    "Open multimodal models vs closed APIs this week",
    "RAG failure modes teams keep hitting",
    "AI coding agents: what changed this week",
]

_SOURCE_LABELS = {
    "hackernews": "Hacker News",
    "aim": "AIM",
    "the_batch": "The Batch",
    "tldr_ai": "TLDR AI",
    "bens_bites": "Ben's Bites",
    "import_ai": "Import AI",
    "latent_space": "Latent Space",
    "alphasignal": "AlphaSignal",
    "interconnects": "Interconnects",
    "last_week_in_ai": "Last Week in AI",
    "rundown_ai": "The Rundown AI",
    "ahead_of_ai": "Ahead of AI",
    "hf_blog": "Hugging Face Blog",
    "openai_news": "OpenAI",
    "anthropic": "Anthropic",
    "deepmind": "DeepMind",
    "simonw": "Simon Willison",
    "techcrunch_ai": "TechCrunch AI",
    "mit_tr": "MIT Tech Review",
    "marktechpost": "Marktechpost",
    "venturebeat_ai": "VentureBeat AI",
    "reddit_ml": "r/MachineLearning",
    "semianalysis": "SemiAnalysis",
}


def _topics_root() -> Path:
    root = get_settings().auto_output_path / "topics"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _cache_path() -> Path:
    return _topics_root() / "trending_cache.json"


def _slug(topic: str) -> str:
    base = re.sub(r"[^\w\s-]", "", (topic or "topic").lower()).strip()
    base = re.sub(r"[\s_-]+", "-", base)[:64].strip("-") or "topic"
    return base


def _topic_id(topic: str) -> str:
    return f"topic:{_slug(topic)}"


def _load_cache() -> dict:
    path = _cache_path()
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_cache(data: dict) -> None:
    path = _cache_path()
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _load_prep(topic_id: str) -> dict | None:
    folder = _topics_root() / topic_id.replace("topic:", "")
    prep_path = folder / "prep.json"
    if not prep_path.is_file():
        return None
    try:
        return json.loads(prep_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _list_prepared() -> dict[str, dict]:
    out: dict[str, dict] = {}
    root = _topics_root()
    for d in root.iterdir():
        if not d.is_dir():
            continue
        prep = d / "prep.json"
        if not prep.is_file():
            continue
        try:
            data = json.loads(prep.read_text(encoding="utf-8"))
        except Exception:
            continue
        tid = data.get("id") or f"topic:{d.name}"
        out[tid] = data
    return out


def _normalize_sources(raw: Any) -> list[str]:
    if isinstance(raw, str):
        parts = [p.strip() for p in raw.split(",") if p.strip()]
    elif isinstance(raw, list):
        parts = [str(p).strip() for p in raw if str(p).strip()]
    else:
        parts = []
    out: list[str] = []
    for p in parts:
        key = p.lower().replace(" ", "_")
        label = _SOURCE_LABELS.get(key) or _SOURCE_LABELS.get(p) or p
        if label not in out:
            out.append(label)
    return out[:4]


def _trend_score(heat: int, sources: list[str], blurb: str = "") -> int:
    """Map model heat (1–10) into a display trend score, lightly boosted by sources."""
    score = max(1, min(10, int(heat or 5)))
    if any("Hacker News" in s for s in sources):
        score = min(10, score + 1)
    if len(sources) >= 2:
        score = min(10, score + 1)
    if re.search(r"\b(this week|today|launch|released|breaking)\b", blurb or "", re.I):
        score = min(10, score + 1)
    return score


def _fetch_fresh_topics() -> tuple[list[dict], dict[str, Any]]:
    """Ask Muse Spark for top trending topics from HN / AIM / newsletter pulse."""
    research_block = ""
    pulse_meta: dict[str, Any] = {}
    try:
        from ..pipeline import topic_research

        research_block, pulse_meta = topic_research.gather_ai_news_pulse(max_hits=32)
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"AI news pulse soft-fail: {e}")
        try:
            from ..pipeline import topic_research

            research_block, pulse_meta = topic_research.research_topics(
                "trending AI machine learning news this week Hacker News AIM newsletter",
                context="Curate educational YouTube topics for GenAI practitioners.",
            )
        except Exception as e2:  # noqa: BLE001
            _LOG.warning(f"topic trend research soft-fail: {e2}")

    prompt = f"""Pick the TOP {_TRENDING_LIMIT} timely AI / ML video topics for a technical YouTube channel.

Rules:
- Prefer stories from the **last 7 days** in the live pulse below (ignore stale viral posts unless they resurfaced this week).
- Concrete and teachable (models, techniques, product patterns) — not vague hype.
- Each topic must be distinct. Titles under 80 characters.
- trend_score is 1–10 (10 = hottest right now).
- sources: short list of where signal came from (e.g. "Hacker News", "AIM", "Interconnects").

Seed ideas (only if pulse is thin):
{json.dumps(_SEED_TOPICS, indent=2)}

Live AI news pulse:
{(research_block or "(none — invent careful timely topics and mark trend_score ≤6)")[:9000]}

Reply with ONLY valid JSON (no markdown fences, no commentary). Schema:
{{"topics":[{{"title":"...","blurb":"one sentence why it matters now","trend_score":8,"sources":["Hacker News"]}}]}}
Exactly {_TRENDING_LIMIT} topics, ranked hottest first.
"""
    topics: list[dict] = []
    used_model = topic_prep.lite_model()
    try:
        from pydantic import BaseModel, ConfigDict, Field

        class _T(BaseModel):
            model_config = ConfigDict(extra="ignore")
            title: str = ""
            blurb: str = ""
            trend_score: int = 5
            heat: int = 0  # legacy alias
            sources: list[str] = Field(default_factory=list)

        class _Bag(BaseModel):
            model_config = ConfigDict(extra="ignore")
            topics: list[_T] = Field(default_factory=list)

        parsed, used_model = topic_prep.generate_structured_lite(
            prompt,
            _Bag,
            task="trending-topics",
            want_json=True,
        )
        for t in parsed.topics:
            title = (t.title or "").strip()
            if len(title) < 8:
                continue
            sources = _normalize_sources(t.sources)
            heat = int(t.trend_score or t.heat or 5)
            score = _trend_score(heat, sources, t.blurb or "")
            topics.append({
                "id": _topic_id(title),
                "title": title[:120],
                "blurb": (t.blurb or "")[:240],
                "heat": score,
                "trend_score": score,
                "sources": sources,
                "kind": "topic",
                "model": used_model,
            })
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"lite topic list failed ({e}); using pulse/seeds")

    # If LLM failed, turn top pulse headlines into topics.
    if not topics:
        for hit in (pulse_meta.get("hits") or [])[:_TRENDING_LIMIT]:
            if not isinstance(hit, dict):
                continue
            title = (hit.get("title") or "").strip()
            if len(title) < 8:
                continue
            src = _normalize_sources([hit.get("source") or "web"])
            raw_score = int(hit.get("score") or 40)
            score = max(4, min(10, 4 + raw_score // 80))
            topics.append({
                "id": _topic_id(title),
                "title": title[:120],
                "blurb": (hit.get("snippet") or "From this week's AI news pulse")[:240],
                "heat": score,
                "trend_score": score,
                "sources": src,
                "kind": "topic",
                "url": hit.get("url") or "",
            })

    if not topics:
        for title in _SEED_TOPICS[:_TRENDING_LIMIT]:
            topics.append({
                "id": _topic_id(title),
                "title": title,
                "blurb": "Curated GenAI explainer topic",
                "heat": 6,
                "trend_score": 6,
                "sources": ["Curated"],
                "kind": "topic",
            })

    seen: set[str] = set()
    out: list[dict] = []
    for t in topics:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        out.append(t)
        if len(out) >= _TRENDING_LIMIT:
            break
    meta = {
        "model": used_model,
        "backends": pulse_meta.get("backends") or [],
        "sources": pulse_meta.get("sources") or [
            {"id": k, "label": v} for k, v in _SOURCE_LABELS.items()
        ],
        "limit": _TRENDING_LIMIT,
    }
    return out, meta


def _archive_topic_row(row: dict, *, batch_at: float) -> None:
    """Move a topic out of the live trending slot without losing prep/queue work."""
    from .. import db

    tid = row.get("id") or ""
    if not tid:
        return
    keep_status = row.get("status") or "trending"
    if row.get("prepared"):
        keep_status = "prepared"
    elif row.get("job_id") or keep_status in {"queued", "done"}:
        keep_status = keep_status if keep_status in {"queued", "done"} else "prepared"
    elif keep_status not in {"prepared", "selected", "queued", "done"}:
        keep_status = "archived"
    data = dict(row)
    extra = {k: v for k, v in data.items() if k not in {
        "id", "title", "blurb", "heat", "status", "selected", "prepared",
        "truthfulness", "prep", "content_md", "job_id", "folder", "model",
        "created_at", "updated_at", "kind",
    }}
    extra["in_trending"] = False
    extra["archived_at"] = batch_at
    try:
        db.upsert_topic({
            "id": tid,
            "title": row.get("title") or tid,
            "blurb": row.get("blurb") or "",
            "heat": row.get("heat") or row.get("trend_score") or 5,
            "status": keep_status,
            "selected": bool(row.get("selected")),
            "prepared": bool(row.get("prepared")),
            "truthfulness": row.get("truthfulness") or None,
            "job_id": row.get("job_id") or None,
            "folder": row.get("folder") or None,
            "data": extra,
        })
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"topic archive soft-fail ({tid}): {e}")


def _archive_previous_trending(
    previous: list[dict],
    *,
    new_ids: set[str],
    batch_at: float,
) -> None:
    """Retire the last trending batch so the UI shows fresh picks on top."""
    from .. import db

    seen: set[str] = set()
    for t in previous or []:
        tid = t.get("id") or ""
        if not tid or tid in new_ids or tid in seen:
            continue
        seen.add(tid)
        existing = db.get_topic(tid) or t
        _archive_topic_row(existing, batch_at=batch_at)

    for row in db.list_topics(limit=200):
        tid = row.get("id") or ""
        if not tid or tid in new_ids:
            continue
        if row.get("in_trending"):
            _archive_topic_row(row, batch_at=batch_at)


def _assemble_trending_response(
    topics: list[dict],
    *,
    fetched_at: float | None,
    model: str = "",
    backends: list | None = None,
    sources: list | None = None,
    cache_age_s: int = 0,
) -> dict[str, Any]:
    """Merge DB prep/selection state onto a trending topic list."""
    from .. import db

    db_by_id = {t["id"]: t for t in db.list_topics(limit=200)}
    prepared_files = _list_prepared()
    trending: list[dict] = []
    archive: list[dict] = []
    seen: set[str] = set()
    for t in (topics or [])[:_TRENDING_LIMIT]:
        row = dict(t)
        tid = row.get("id") or ""
        if not tid or tid in seen:
            continue
        seen.add(tid)
        db_row = db_by_id.get(tid) or {}
        prep = prepared_files.get(tid) or _load_prep(tid) or db_row.get("prep")
        score = int(row.get("trend_score") or row.get("heat") or db_row.get("heat") or 5)
        row["trend_score"] = max(1, min(10, score))
        row["heat"] = row["trend_score"]
        row["sources"] = row.get("sources") or list(db_row.get("sources") or [])
        row["fetched_at"] = fetched_at or db_row.get("trending_batch_at") or 0
        if prep or db_row.get("prepared"):
            prep = prep or {}
            row["prepared"] = True
            row["truthfulness"] = (
                prep.get("truthfulness") or db_row.get("truthfulness") or "medium"
            )
            row["truthfulness_notes"] = prep.get("truthfulness_notes") or ""
            row["citations"] = prep.get("citations") or (db_row.get("prep") or {}).get("citations") or []
            row["claims"] = prep.get("claims") or (db_row.get("prep") or {}).get("claims") or []
            row["prep_title"] = prep.get("title") or row.get("title")
            row["folder"] = prep.get("folder") or db_row.get("folder") or ""
            row["job_id"] = db_row.get("job_id") or ""
            if db_row.get("title"):
                row["title"] = db_row["title"]
        else:
            row["prepared"] = False
        row["selected"] = bool(db_row.get("selected"))
        row["status"] = db_row.get("status") or "trending"
        row["updated_at"] = db_row.get("updated_at") or fetched_at or 0
        trending.append(row)

    for tid, db_row in db_by_id.items():
        if tid in seen:
            continue
        if db_row.get("in_trending"):
            continue
        status = db_row.get("status") or ""
        if status == "trending" and not db_row.get("archived_at"):
            continue
        if status not in {"archived", "prepared", "selected", "queued", "done"}:
            if not (db_row.get("prepared") or db_row.get("selected") or db_row.get("job_id")):
                continue
        prep = db_row.get("prep") or _load_prep(tid) or {}
        archive.append({
            "id": tid,
            "title": db_row.get("title") or tid,
            "blurb": db_row.get("blurb") or "",
            "heat": db_row.get("heat") or 5,
            "trend_score": int(db_row.get("trend_score") or db_row.get("heat") or 5),
            "sources": list(db_row.get("sources") or []),
            "kind": "topic",
            "prepared": bool(db_row.get("prepared")),
            "selected": bool(db_row.get("selected")),
            "status": status or ("prepared" if db_row.get("prepared") else "archived"),
            "truthfulness": db_row.get("truthfulness") or prep.get("truthfulness") or "",
            "truthfulness_notes": prep.get("truthfulness_notes") or "",
            "citations": prep.get("citations") or [],
            "claims": prep.get("claims") or [],
            "prep_title": prep.get("title") or db_row.get("title"),
            "folder": db_row.get("folder") or "",
            "job_id": db_row.get("job_id") or "",
            "updated_at": db_row.get("updated_at") or db_row.get("archived_at") or 0,
            "archived_at": db_row.get("archived_at") or db_row.get("updated_at") or 0,
        })

    archive.sort(
        key=lambda r: float(r.get("updated_at") or r.get("archived_at") or 0),
        reverse=True,
    )

    return {
        "topics": trending,
        "archive": archive,
        "extras": archive,
        "fetched_at": fetched_at,
        "model": model or "",
        "cache_age_s": cache_age_s,
        "cache_ttl_s": _CACHE_TTL,
        "limit": _TRENDING_LIMIT,
        "backends": backends or [],
        "sources": sources or [
            {"id": k, "label": v} for k, v in _SOURCE_LABELS.items()
        ],
        "from_cache": True,
        "stale": cache_age_s >= _CACHE_TTL if _CACHE_TTL else False,
    }


def _seed_topics_to_db(topics: list[dict], *, model: str = "", batch_at: float | None = None) -> None:
    """Persist trending topics without clobbering prepared / queued rows."""
    from .. import db

    batch_at = float(batch_at or time.time())
    for t in topics:
        tid = t.get("id") or ""
        if not tid:
            continue
        try:
            existing = db.get_topic(tid)
            if existing and (
                existing.get("prepared")
                or existing.get("job_id")
                or (existing.get("status") or "") in {"prepared", "queued", "done"}
            ):
                # Keep user work; mark as current trending batch only.
                db.upsert_topic({
                    "id": tid,
                    "data": {
                        "in_trending": True,
                        "trending_batch_at": batch_at,
                        "sources": t.get("sources") or existing.get("sources") or [],
                        "trend_score": t.get("trend_score") or t.get("heat") or existing.get("heat") or 5,
                    },
                })
                continue
            db.upsert_topic({
                "id": tid,
                "title": t.get("title") or tid,
                "blurb": t.get("blurb") or "",
                "heat": t.get("trend_score") or t.get("heat") or 5,
                "status": (existing or {}).get("status") or "trending",
                "selected": bool((existing or {}).get("selected")),
                "prepared": bool((existing or {}).get("prepared")),
                "truthfulness": (existing or {}).get("truthfulness") or None,
                "model": model or None,
                "data": {
                    "in_trending": True,
                    "trending_batch_at": batch_at,
                    "sources": t.get("sources") or [],
                    "trend_score": t.get("trend_score") or t.get("heat") or 5,
                    "kind": t.get("kind") or "topic",
                },
            })
        except Exception as e:  # noqa: BLE001
            _LOG.warning(f"topic db seed soft-fail: {e}")


def _topics_from_db_trending() -> list[dict]:
    """Rebuild the latest trending list from DB when the file cache is missing."""
    from .. import db

    rows = db.list_topics(limit=200)
    marked = [r for r in rows if r.get("in_trending")]
    if not marked:
        marked = [
            r for r in rows
            if r.get("in_trending") or (r.get("status") or "") == "trending"
        ]
    if not marked:
        return []
    latest_batch = max(float(r.get("trending_batch_at") or 0) for r in marked)
    if latest_batch > 0:
        marked = [
            r for r in marked
            if float(r.get("trending_batch_at") or 0) >= latest_batch - 1
        ]
    marked.sort(
        key=lambda r: (
            -float(r.get("trending_batch_at") or 0),
            -int(r.get("trend_score") or r.get("heat") or 0),
            -float(r.get("updated_at") or 0),
        )
    )
    out: list[dict] = []
    for r in marked[:_TRENDING_LIMIT]:
        out.append({
            "id": r["id"],
            "title": r.get("title") or r["id"],
            "blurb": r.get("blurb") or "",
            "heat": r.get("heat") or 5,
            "trend_score": int(r.get("trend_score") or r.get("heat") or 5),
            "sources": list(r.get("sources") or []) if isinstance(r.get("sources"), list) else [],
            "kind": "topic",
        })
    return out


def list_trending(*, refresh: bool = False) -> dict[str, Any]:
    """Return trending topics from cache/DB, refreshing when stale.

    Network + Lite curation run when:
    - ``refresh=True`` (user clicked Refresh), or
    - there is no saved trending list yet, or
    - the cached list is older than ``_CACHE_TTL`` (default 1 hour).
    """
    cache = _load_cache()
    age = time.time() - float(cache.get("fetched_at") or 0) if cache.get("fetched_at") else 0
    stale = bool(_CACHE_TTL and age >= _CACHE_TTL)

    if not refresh and not stale and cache.get("topics"):
        return _assemble_trending_response(
            cache.get("topics") or [],
            fetched_at=cache.get("fetched_at"),
            model=cache.get("model") or "",
            backends=cache.get("backends") or [],
            sources=cache.get("sources") or [],
            cache_age_s=int(age),
        )

    if not refresh and not stale:
        db_topics = _topics_from_db_trending()
        if db_topics:
            cache = {
                "fetched_at": time.time(),
                "model": "",
                "topics": db_topics,
                "backends": [],
                "sources": [{"id": k, "label": v} for k, v in _SOURCE_LABELS.items()],
                "limit": _TRENDING_LIMIT,
                "restored_from_db": True,
            }
            _save_cache(cache)
            return _assemble_trending_response(
                db_topics,
                fetched_at=cache["fetched_at"],
                sources=cache["sources"],
                cache_age_s=0,
            )

    previous = list(cache.get("topics") or [])
    if stale and previous and not refresh:
        _LOG.info(f"trending cache stale ({int(age)}s) — refreshing pulse")

    try:
        topics, meta = _fetch_fresh_topics()
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"trending refresh failed ({e}); keeping previous list")
        if previous:
            out = _assemble_trending_response(
                previous,
                fetched_at=cache.get("fetched_at"),
                model=cache.get("model") or "",
                backends=cache.get("backends") or [],
                sources=cache.get("sources") or [],
                cache_age_s=int(age),
            )
            out["from_cache"] = True
            out["stale"] = True
            out["refresh_error"] = str(e)
            return out
        raise

    batch_at = time.time()
    new_ids = {t.get("id") or "" for t in topics if t.get("id")}
    if previous or refresh or stale:
        _archive_previous_trending(previous, new_ids=new_ids, batch_at=batch_at)

    cache = {
        "fetched_at": batch_at,
        "model": meta.get("model") or "",
        "topics": topics,
        "backends": meta.get("backends") or [],
        "sources": meta.get("sources") or [],
        "limit": meta.get("limit") or _TRENDING_LIMIT,
    }
    _save_cache(cache)
    _seed_topics_to_db(topics, model=cache.get("model") or "", batch_at=batch_at)
    out = _assemble_trending_response(
        topics,
        fetched_at=cache["fetched_at"],
        model=cache.get("model") or "",
        backends=cache.get("backends") or [],
        sources=cache.get("sources") or [],
        cache_age_s=0,
    )
    out["from_cache"] = False
    out["refreshed"] = bool(refresh or stale)
    out["stale"] = False
    return out


def search_topics(query: str) -> dict[str, Any]:
    """Search the web + news pulse for a user query; return up to 4 scored topics."""
    q = re.sub(r"\s+", " ", (query or "").strip())
    if len(q) < 2:
        raise ValueError("Search query is too short")

    research_block = ""
    meta: dict[str, Any] = {}
    try:
        from ..pipeline import topic_research

        research_block, meta = topic_research.research_topics(
            q,
            context=(
                "User is searching for an educational AI/ML YouTube topic. "
                "Prefer Hacker News, AIM, Interconnects, Latent Space, lab blogs, and AI press."
            ),
        )
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"topic search research soft-fail: {e}")

    hn_hits: list[dict] = []
    try:
        from ..pipeline import topic_research as tr

        for h in tr._search_hackernews(q, 8, float(get_settings().topic_research_timeout or 8)):
            hn_hits.append({
                "title": h.title,
                "url": h.url,
                "snippet": h.snippet,
                "source": "hackernews",
                "score": h.score,
            })
    except Exception as e:  # noqa: BLE001
        _LOG.debug(f"HN search soft-fail: {e}")

    prompt = f"""The user searched for an AI video topic: {q!r}

From the research below, propose up to {_TRENDING_LIMIT} strong, teachable topic angles.
Each needs a trend_score 1–10 and sources.

Research:
{(research_block or "(thin research)")[:6000]}

HN hits:
{json.dumps(hn_hits[:6], indent=2)[:2000]}

Return JSON:
{{"topics":[{{"title":"...","blurb":"why this angle works","trend_score":1-10,"sources":["Hacker News"]}}]}}
If research is thin, still return 1–2 careful angles for the query itself.
"""
    topics: list[dict] = []
    used_model = topic_prep.lite_model()
    try:
        from pydantic import BaseModel, Field

        class _T(BaseModel):
            title: str = ""
            blurb: str = ""
            trend_score: int = 5
            sources: list[str] = Field(default_factory=list)

        class _Bag(BaseModel):
            topics: list[_T] = Field(default_factory=list)

        parsed, used_model = topic_prep.generate_structured_lite(
            prompt,
            _Bag,
            task="topic-search",
            want_json=True,
        )
        for t in parsed.topics:
            title = (t.title or "").strip()
            if len(title) < 6:
                continue
            sources = _normalize_sources(t.sources) or ["Search"]
            score = _trend_score(int(t.trend_score or 5), sources, t.blurb or "")
            topics.append({
                "id": _topic_id(title),
                "title": title[:120],
                "blurb": (t.blurb or "")[:240],
                "heat": score,
                "trend_score": score,
                "sources": sources,
                "kind": "search",
                "model": used_model,
            })
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"topic search LLM soft-fail: {e}")

    if not topics:
        topics.append({
            "id": _topic_id(q),
            "title": q[:120],
            "blurb": "Your search — prepare this as a video topic",
            "heat": 7,
            "trend_score": 7,
            "sources": ["Search"],
            "kind": "search",
        })
        for h in hn_hits[:3]:
            title = (h.get("title") or "").strip()
            if len(title) < 8:
                continue
            score = max(4, min(10, 4 + int(h.get("score") or 0) // 80))
            topics.append({
                "id": _topic_id(title),
                "title": title[:120],
                "blurb": (h.get("snippet") or "From Hacker News")[:240],
                "heat": score,
                "trend_score": score,
                "sources": ["Hacker News"],
                "kind": "search",
                "url": h.get("url") or "",
            })

    seen: set[str] = set()
    out: list[dict] = []
    for t in topics:
        if t["id"] in seen:
            continue
        seen.add(t["id"])
        out.append(t)
        if len(out) >= _TRENDING_LIMIT:
            break

    return {
        "query": q,
        "topics": out,
        "model": used_model,
        "backends": meta.get("backends") or [],
        "limit": _TRENDING_LIMIT,
    }


def select_topic(topic_id: str, *, selected: bool = True, title: str = "", blurb: str = "") -> dict[str, Any]:
    """Persist a user selection in SQLite (data-wise tracking)."""
    from .. import db

    tid = (topic_id or "").strip()
    if not tid:
        raise ValueError("topic_id required")
    existing = db.get_topic(tid)
    if not existing:
        title = title.strip()
        heat = 5
        for t in (_load_cache().get("topics") or []):
            if t.get("id") == tid:
                title = title or t.get("title") or ""
                blurb = blurb or t.get("blurb") or ""
                heat = t.get("trend_score") or t.get("heat") or 5
                break
        if not title:
            title = tid.replace("topic:", "").replace("-", " ")
        db.upsert_topic({
            "id": tid,
            "title": title,
            "blurb": blurb,
            "heat": heat,
            "status": "selected" if selected else "trending",
            "selected": selected,
            "prepared": False,
        })
    row = db.mark_topic_selected(tid, selected=selected)
    _LOG.info(f"topic {'selected' if selected else 'deselected'}: {tid}")
    return row or {}


def prepare(topic_id: str = "", topic: str = "", *, force: bool = False) -> dict[str, Any]:
    """Prepare rich content for one topic using Muse Spark + research.

    Returns the existing prep when already prepared (unless ``force=True``).
    """
    from .. import costs, db

    title = (topic or "").strip()
    tid = (topic_id or "").strip()
    if not title and tid.startswith("topic:"):
        db_row = db.get_topic(tid)
        if db_row and db_row.get("title"):
            title = db_row["title"]
        else:
            for t in (_load_cache().get("topics") or []):
                if t.get("id") == tid:
                    title = t.get("title") or ""
                    break
        if not title:
            title = tid.replace("topic:", "").replace("-", " ")
    if not title:
        raise ValueError("topic or topic_id required")
    if not tid:
        tid = _topic_id(title)

    # Reuse saved prep — avoid duplicate Lite/research spend on every click.
    if not force:
        existing = db.get_topic(tid) or {}
        cached = None
        if existing.get("prepared") and isinstance(existing.get("prep"), dict):
            cached = dict(existing["prep"])
        if not cached:
            cached = _load_prep(tid)
        if cached and (cached.get("summary") or cached.get("outline") or cached.get("narrative")):
            folder = _topics_root() / (cached.get("folder") or tid.replace("topic:", ""))
            folder.mkdir(parents=True, exist_ok=True)
            if not (folder / "content.md").is_file():
                source = topic_prep.brief_to_source_text(cached)
                (folder / "content.md").write_text(source, encoding="utf-8")
            record = {
                **cached,
                "id": tid,
                "folder": folder.name,
                "content_path": "content.md",
                "cached": True,
            }
            _LOG.info(f"reusing prepared topic {tid} (no re-fetch)")
            return record

    with costs.job_context(f"topic-prep:{tid.replace('topic:', '')[:40]}"):
        prep = topic_prep.prepare_topic(title)
    folder = _topics_root() / tid.replace("topic:", "")
    folder.mkdir(parents=True, exist_ok=True)
    source = topic_prep.brief_to_source_text(prep)
    (folder / "content.md").write_text(source, encoding="utf-8")
    record = {
        **prep,
        "id": tid,
        "folder": folder.name,
        "content_path": "content.md",
        "source_chars": len(source),
        "cached": False,
    }
    (folder / "prep.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    try:
        db.upsert_topic({
            "id": tid,
            "title": prep.get("title") or title,
            "blurb": (prep.get("summary") or "")[:240],
            "heat": 8,
            "status": "prepared",
            "selected": True,
            "prepared": True,
            "truthfulness": prep.get("truthfulness") or "medium",
            "prep": record,
            "content_md": source,
            "folder": folder.name,
            "model": prep.get("model") or topic_prep.lite_model(),
        })
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"topic db prep persist soft-fail: {e}")
    _LOG.success(
        f"prepared {tid} ({prep.get('truthfulness')}) via {prep.get('model')} "
        f"cites={len(prep.get('citations') or [])}"
    )
    return record


def get_prepared(topic_id: str) -> dict | None:
    return _load_prep(topic_id)


def queue_video_from_prep(
    topic_id: str,
    *,
    user_id: str = "system",
    video_opts: dict | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Create a Studio job from prepared markdown and start the pipeline.

    Reuses an existing non-failed job for this topic unless ``force=True``.
    """
    from ..config import WORKSPACE_DIR
    from ..jobs import store
    from ..orchestrator import run_pipeline
    from ..video_options import normalize_video_options
    from .. import db
    import shutil
    import threading

    prep = _load_prep(topic_id)
    if not prep:
        db_row = db.get_topic(topic_id) or {}
        if isinstance(db_row.get("prep"), dict):
            prep = db_row["prep"]
    if not prep:
        title = (db.get_topic(topic_id) or {}).get("title") or ""
        if not title:
            for t in (_load_cache().get("topics") or []):
                if t.get("id") == topic_id:
                    title = t.get("title") or ""
                    break
        if not title:
            title = topic_id.replace("topic:", "").replace("-", " ")
        try:
            prep = prepare(topic_id=topic_id, topic=title)
        except Exception as e:
            raise FileNotFoundError(f"Auto-prepare failed for {topic_id}: {e}") from e

    folder = _topics_root() / (prep.get("folder") or topic_id.replace("topic:", ""))
    content_path = folder / "content.md"
    if not content_path.is_file() and prep:
        # Restore content.md from DB brief when the file was cleaned up.
        source = topic_prep.brief_to_source_text(prep)
        folder.mkdir(parents=True, exist_ok=True)
        content_path.write_text(source, encoding="utf-8")
    if not content_path.is_file():
        raise FileNotFoundError("content.md missing — prepare the topic first")

    db_row = db.get_topic(topic_id) or {}
    existing_job_id = str(db_row.get("job_id") or "").strip()
    if existing_job_id and not force:
        try:
            existing_job = store.get(existing_job_id)
        except Exception:
            existing_job = None
        status = str(getattr(existing_job, "status", "") or "").lower() if existing_job else ""
        from ..workspace_store import resolve_job_dir
        try:
            work_exists = resolve_job_dir(existing_job_id, create=False).is_dir()
        except Exception:
            work_exists = False
        # Only reuse if the job is actively queued/running and workspace exists on disk.
        if existing_job and work_exists and status in {"queued", "running"}:
            _LOG.info(f"reusing active topic job {existing_job_id} (status={status})")
            return {
                "ok": True,
                "job_id": existing_job_id,
                "topic_id": topic_id,
                "truthfulness": prep.get("truthfulness"),
                "title": prep.get("title") or prep.get("topic"),
                "reused": True,
                "status": status,
            }

    opts = normalize_video_options(**(video_opts or {}))
    clean_title = str(prep.get("title") or prep.get("topic") or "topic")[:80].strip()
    opts["automation_kind"] = "topic"
    opts["automation_title"] = clean_title
    opts["extra_topics"] = prep.get("topic") or ""
    opts["topic_prep"] = {
        "id": topic_id,
        "truthfulness": prep.get("truthfulness"),
        "citations": prep.get("citations") or [],
        "model": prep.get("model"),
    }
    fname = f"{clean_title.replace('/', '-')}.md"
    job = store.create(fname, options=opts, user_id=user_id)
    from ..workspace_store import resolve_job_dir

    work = resolve_job_dir(job.id, create=True)
    shutil.copyfile(content_path, work / "input.md")
    store.set_content(job, "extracted_text", content_path.read_text(encoding="utf-8"))
    store.set_content(job, "slide_title", clean_title)
    store.set_content(job, "title", clean_title)
    store.set_content(job, "publish_title", clean_title)
    store.set_content(job, "topic_truthfulness", prep.get("truthfulness") or "medium")
    store.set_content(job, "topic_citations", prep.get("citations") or [])
    store.set_content(job, "topic_prep_model", prep.get("model") or "")

    def _run() -> None:
        try:
            run_pipeline(job)
        except Exception as e:  # noqa: BLE001
            _LOG.error(f"topic job {job.id} failed: {e}")

    threading.Thread(target=_run, daemon=True, name=f"topic-job-{job.id}").start()
    try:
        db.upsert_topic({
            "id": topic_id,
            "title": prep.get("title") or prep.get("topic") or topic_id,
            "status": "queued",
            "selected": True,
            "prepared": True,
            "truthfulness": prep.get("truthfulness") or "",
            "prep": prep,
            "job_id": job.id,
            "folder": prep.get("folder") or "",
            "model": prep.get("model") or "",
        })
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"topic db queue persist soft-fail: {e}")
    return {
        "ok": True,
        "job_id": job.id,
        "topic_id": topic_id,
        "truthfulness": prep.get("truthfulness"),
        "title": prep.get("title") or prep.get("topic"),
        "reused": False,
    }
