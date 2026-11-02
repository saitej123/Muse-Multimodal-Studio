"""Admin-selectable runtime overrides for LLM + image backends.

Persisted under ``workspace/runtime_settings.json`` and applied onto the live
``Settings`` object so cron / jobs pick them up without restarting. Also mirrors
key values into ``.env`` so they survive a full process restart.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .config import BASE_DIR, WORKSPACE_DIR, get_settings
from .logging_setup import log

_FILE = WORKSPACE_DIR / "runtime_settings.json"

# Fields admins may change from the dashboard.
_ALLOWED: dict[str, type] = {
    "llm_provider": str,
    "muse_model": str,
    "muse_vision_model": str,
    "thumbnail_backend": str,
    "auto_video_style": str,
    "auto_video_theme": str,
}

_ENV_KEYS = {
    "llm_provider": "LLM_PROVIDER",
    "muse_model": "MUSE_MODEL",
    "muse_vision_model": "MUSE_VISION_MODEL",
    "thumbnail_backend": "THUMBNAIL_BACKEND",
    "auto_video_style": "AUTO_VIDEO_STYLE",
    "auto_video_theme": "AUTO_VIDEO_THEME",
}

_PROVIDER_CHOICES = ("muse",)
_THUMB_CHOICES = ("auto", "nano_banana", "none")


def _load_raw() -> dict[str, Any]:
    if not _FILE.is_file():
        return {}
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _normalize(updates: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, typ in _ALLOWED.items():
        if key not in updates:
            continue
        raw = updates[key]
        if raw is None:
            continue
        val = typ(raw).strip() if typ is str else typ(raw)
        if typ is str and not val:
            continue
        if key == "llm_provider":
            # Hosted studio is Muse. Older muse/ollama/openai/auto values map here.
            if str(val).lower() in {"muse", "google", "ollama", "openai", "auto"}:
                val = "muse"
            if val not in _PROVIDER_CHOICES:
                raise ValueError(
                    f"llm_provider must be one of: {', '.join(_PROVIDER_CHOICES)}"
                )
        if key == "thumbnail_backend":
            val = str(val).lower()
            # Legacy local backends → Nano Banana (Boogu stack removed).
            if val in ("boogu", "sana", "local"):
                val = "nano_banana"
            if val not in _THUMB_CHOICES:
                raise ValueError(
                    f"thumbnail_backend must be one of: {', '.join(_THUMB_CHOICES)}"
                )
        if key == "auto_video_style":
            val = str(val).strip().lower()
            from .video_options import AUTO_VIDEO_STYLE, STYLE_ALIASES, VIDEO_STYLES
            val = STYLE_ALIASES.get(val, val)
            if val not in VIDEO_STYLES and val != AUTO_VIDEO_STYLE:
                raise ValueError("auto_video_style is not a known layout template")
        if key == "auto_video_theme":
            val = str(val).strip().lower()
            from .video_options import AUTO_VIDEO_THEME, VIDEO_THEMES, alias_theme
            val = alias_theme(val)
            if val not in VIDEO_THEMES and val != AUTO_VIDEO_THEME:
                raise ValueError("auto_video_theme is not a known color theme")
        if key in ("muse_model", "muse_vision_model") and typ is str:
            from .pipeline.llm_client import normalize_muse_model
            val = normalize_muse_model(val)
        out[key] = val
    return out


def apply_to_settings(data: dict[str, Any] | None = None) -> None:
    """Mutate the cached Settings instance with persisted overrides."""
    try:
        payload = _normalize(data if data is not None else _load_raw())
    except ValueError as e:
        # Never crash the app on a stale/legacy settings file.
        log.warning(f"runtime_settings skipped: {e}")
        return
    if not payload:
        return
    s = get_settings()
    for k, v in payload.items():
        setattr(s, k, v)


def current() -> dict[str, Any]:
    """Snapshot of effective values + available choices for the admin UI."""
    apply_to_settings()
    s = get_settings()
    provider = s.active_provider
    return {
        "llm_provider": "muse",
        "active_provider": provider,
        "muse_model": s.muse_model,
        "muse_vision_model": s.muse_vision_model,
        "text_model": s.llm_text_model,
        "vision_model": s.llm_vision_model,
        "thumbnail_backend": (s.thumbnail_backend or "auto").strip().lower() or "auto",
        "auto_video_style": (getattr(s, "auto_video_style", None) or "whiteboard").strip().lower(),
        "auto_video_theme": (getattr(s, "auto_video_theme", None) or "snow").strip().lower(),
        "choices": {
            "llm_provider": list(_PROVIDER_CHOICES),
            "thumbnail_backend": list(_THUMB_CHOICES),
            "muse_models": [
                "muse-wonder-1.0",
                "muse-spark-1.3",
                "muse-spark-1.2",
            ],
            "muse_models": [
                "muse-wonder-1.0",
                "muse-spark-1.3",
                "muse-spark-1.2",
            ],
        },
        "persisted": _load_raw(),
    }


def _mirror_env(updates: dict[str, Any]) -> None:
    """Best-effort: update KEY=value lines in ``.env`` without rewriting secrets."""
    env_path = BASE_DIR / ".env"
    if not env_path.is_file():
        return
    try:
        text = env_path.read_text(encoding="utf-8")
    except OSError:
        return
    lines = text.splitlines()
    for field, env_key in _ENV_KEYS.items():
        if field not in updates:
            continue
        value = str(updates[field])
        pattern = re.compile(rf"^\s*{re.escape(env_key)}\s*=")
        replaced = False
        for i, line in enumerate(lines):
            if pattern.match(line):
                lines[i] = f"{env_key}={value}"
                replaced = True
                break
        if not replaced:
            lines.append(f"{env_key}={value}")
    try:
        env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    except OSError as e:
        log.bind(task="settings").warning(f"could not mirror .env: {e}")


def save(updates: dict[str, Any]) -> dict[str, Any]:
    """Validate, persist, apply, and return the effective snapshot."""
    normalized = _normalize(updates)
    if not normalized:
        raise ValueError("No valid settings fields provided")
    merged = {**_load_raw(), **normalized}
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    apply_to_settings(merged)
    _mirror_env(normalized)
    log.bind(task="settings").info(
        "admin runtime settings updated: "
        + ", ".join(f"{k}={normalized[k]}" for k in normalized)
    )
    return current()


def load_on_startup() -> None:
    """Called from app lifespan so overrides survive restarts."""
    apply_to_settings()
