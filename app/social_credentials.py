"""Admin-managed social media credentials for posting.

Secrets live in ``workspace/social_credentials.json``. The public API never
returns cleartext secrets — only masked previews and ready/enabled flags.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import WORKSPACE_DIR
from .logging_setup import log

_FILE = WORKSPACE_DIR / "social_credentials.json"

PLATFORM_FIELDS: dict[str, list[tuple[str, str, bool]]] = {
    # (key, label, is_secret)
    "youtube": [
        ("client_secrets_path", "Path to client_secrets.json (optional override)", True),
        ("privacy", "Privacy (public / unlisted / private)", False),
    ],
    "instagram": [
        ("access_token", "Meta Graph access token", True),
        ("ig_user_id", "Instagram Business / Creator user id", False),
    ],
    "x": [
        ("bearer_token", "X API Bearer token (app-only)", True),
        ("api_key", "API Key", True),
        ("api_secret", "API Secret", True),
        ("access_token", "User access token", True),
        ("access_token_secret", "User access token secret", True),
    ],
    "linkedin": [
        ("access_token", "LinkedIn OAuth access token", True),
        ("person_urn", "Author URN (urn:li:person:…)", False),
        ("organization_urn", "Optional org URN (urn:li:organization:…)", False),
    ],
}

_BOOL_KEYS = ("enabled", "auto_post")
_PLATFORMS = tuple(PLATFORM_FIELDS.keys())
_LABELS = {
    "youtube": "YouTube",
    "instagram": "Instagram",
    "x": "Twitter / X",
    "linkedin": "LinkedIn",
}


def _blank_platform() -> dict[str, Any]:
    return {"enabled": False, "auto_post": False}


def _load_raw() -> dict[str, Any]:
    if not _FILE.is_file():
        return {}
    try:
        data = json.loads(_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_raw(data: dict[str, Any]) -> None:
    _FILE.parent.mkdir(parents=True, exist_ok=True)
    _FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def get_all() -> dict[str, dict[str, Any]]:
    raw = _load_raw()
    out: dict[str, dict[str, Any]] = {}
    for p in _PLATFORMS:
        base = _blank_platform()
        cur = raw.get(p) if isinstance(raw.get(p), dict) else {}
        base.update({k: v for k, v in cur.items() if v is not None})
        out[p] = base
    return out


def get_platform(platform: str) -> dict[str, Any]:
    return get_all().get(platform, _blank_platform())


def _mask(value: str) -> str:
    v = str(value or "")
    if not v:
        return ""
    if len(v) <= 4:
        return "***"
    return "***" + v[-4:]


def _platform_ready(platform: str, cfg: dict[str, Any]) -> bool:
    if not cfg.get("enabled"):
        return False
    if platform == "youtube":
        from .config import get_settings
        path = str(cfg.get("client_secrets_path") or "").strip()
        if path:
            return Path(path).is_file()
        try:
            return get_settings().youtube_secrets_path.is_file()
        except Exception:
            return False
    if platform == "instagram":
        return bool(str(cfg.get("access_token") or "").strip() and str(cfg.get("ig_user_id") or "").strip())
    if platform == "x":
        oauth1 = all(
            str(cfg.get(k) or "").strip()
            for k in ("api_key", "api_secret", "access_token", "access_token_secret")
        )
        return oauth1 or bool(str(cfg.get("bearer_token") or "").strip())
    if platform == "linkedin":
        return bool(
            str(cfg.get("access_token") or "").strip()
            and (
                str(cfg.get("person_urn") or "").strip()
                or str(cfg.get("organization_urn") or "").strip()
            )
        )
    return False


def public_status() -> dict[str, Any]:
    """Safe snapshot for the admin UI (masked secrets)."""
    platforms = []
    all_cfg = get_all()
    for name, fields in PLATFORM_FIELDS.items():
        cfg = all_cfg.get(name, {})
        field_rows = []
        configured = 0
        for key, label, secret in fields:
            raw = str(cfg.get(key) or "").strip()
            if raw:
                configured += 1
            field_rows.append({
                "key": key,
                "label": label,
                "secret": secret,
                "configured": bool(raw),
                "masked": _mask(raw) if secret and raw else raw,
                "has_value": bool(raw),
            })
        platforms.append({
            "id": name,
            "label": _LABELS[name],
            "enabled": bool(cfg.get("enabled")),
            "auto_post": bool(cfg.get("auto_post")),
            "ready": _platform_ready(name, cfg),
            "fields": field_rows,
            "configured_fields": configured,
        })
    return {"platforms": platforms}


def update_platform(platform: str, updates: dict[str, Any]) -> dict[str, Any]:
    if platform not in PLATFORM_FIELDS:
        raise ValueError(f"Unknown platform: {platform}")
    all_cfg = get_all()
    cfg = dict(all_cfg.get(platform) or _blank_platform())
    allowed = {k for k, _, _ in PLATFORM_FIELDS[platform]} | set(_BOOL_KEYS)

    for key, val in (updates or {}).items():
        if key not in allowed:
            continue
        if key in _BOOL_KEYS:
            cfg[key] = bool(val)
            continue
        if val is None:
            continue
        s = str(val).strip()
        # Blank or still-masked value = keep existing secret.
        if s == "" or s.startswith("***"):
            continue
        cfg[key] = s

    all_cfg[platform] = cfg
    _save_raw(all_cfg)
    log.bind(task="social-creds").info(
        f"updated {platform} credentials (enabled={cfg.get('enabled')})"
    )
    return public_status()


def clear_field(platform: str, key: str) -> dict[str, Any]:
    if platform not in PLATFORM_FIELDS:
        raise ValueError(f"Unknown platform: {platform}")
    all_cfg = get_all()
    cfg = dict(all_cfg.get(platform) or _blank_platform())
    cfg[key] = ""
    all_cfg[platform] = cfg
    _save_raw(all_cfg)
    return public_status()


def platforms_for_auto_post() -> list[str]:
    return [
        p
        for p, cfg in get_all().items()
        if cfg.get("enabled") and cfg.get("auto_post") and _platform_ready(p, cfg)
    ]
