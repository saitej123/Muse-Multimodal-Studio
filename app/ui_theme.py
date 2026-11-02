"""App-wide UI color palette (admin-controlled).

The palette drives CSS custom properties on the frontend so tabs, chips,
buttons, format cards, and progress bars stay in sync. Stored as JSON on disk
so it survives restarts. Login loads the same palette via the public API.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import WORKSPACE_DIR

_PALETTE_FILE = WORKSPACE_DIR / "ui_palette.json"

# Default matches the Indigo preset (first run).
DEFAULT_PALETTE: dict[str, str] = {
    "name": "Indigo",
    "primary": "239 84% 67%",
    "primary_foreground": "0 0% 100%",
    "brand": "239 84% 67%",
    "brand_2": "243 75% 59%",
    "blue": "239 84% 67%",
    "blue_2": "243 75% 59%",
}

PRESET_PALETTES: list[dict[str, Any]] = [
    {
        "name": "Ocean Blue",
        "primary": "217 91% 60%",
        "primary_foreground": "0 0% 100%",
        "brand": "217 91% 60%",
        "brand_2": "221 83% 53%",
        "blue": "217 91% 60%",
        "blue_2": "221 83% 53%",
    },
    {
        "name": "Royal Blue",
        "primary": "224 76% 48%",
        "primary_foreground": "0 0% 100%",
        "brand": "224 76% 48%",
        "brand_2": "226 71% 40%",
        "blue": "224 76% 48%",
        "blue_2": "226 71% 40%",
    },
    {
        "name": "Sky Blue",
        "primary": "199 89% 48%",
        "primary_foreground": "0 0% 100%",
        "brand": "199 89% 48%",
        "brand_2": "201 96% 40%",
        "blue": "199 89% 48%",
        "blue_2": "201 96% 40%",
    },
    DEFAULT_PALETTE,
    {
        "name": "Teal",
        "primary": "173 80% 40%",
        "primary_foreground": "0 0% 100%",
        "brand": "173 80% 40%",
        "brand_2": "175 84% 32%",
        "blue": "173 80% 40%",
        "blue_2": "175 84% 32%",
    },
    {
        "name": "Violet",
        "primary": "262 83% 58%",
        "primary_foreground": "0 0% 100%",
        "brand": "262 83% 58%",
        "brand_2": "271 81% 56%",
        "blue": "262 83% 58%",
        "blue_2": "271 81% 56%",
    },
    {
        "name": "Rose",
        "primary": "347 77% 50%",
        "primary_foreground": "0 0% 100%",
        "brand": "347 77% 50%",
        "brand_2": "349 89% 42%",
        "blue": "347 77% 50%",
        "blue_2": "349 89% 42%",
    },
    {
        "name": "Emerald",
        "primary": "160 84% 39%",
        "primary_foreground": "0 0% 100%",
        "brand": "160 84% 39%",
        "brand_2": "161 94% 30%",
        "blue": "160 84% 39%",
        "blue_2": "161 94% 30%",
    },
    {
        "name": "Amber",
        "primary": "32 95% 44%",
        "primary_foreground": "0 0% 100%",
        "brand": "32 95% 44%",
        "brand_2": "25 95% 40%",
        "blue": "32 95% 44%",
        "blue_2": "25 95% 40%",
    },
    {
        "name": "Slate",
        "primary": "215 20% 45%",
        "primary_foreground": "0 0% 100%",
        "brand": "215 20% 45%",
        "brand_2": "215 25% 35%",
        "blue": "215 20% 45%",
        "blue_2": "215 25% 35%",
    },
    {
        "name": "Cyan",
        "primary": "189 94% 43%",
        "primary_foreground": "0 0% 100%",
        "brand": "189 94% 43%",
        "brand_2": "192 91% 36%",
        "blue": "189 94% 43%",
        "blue_2": "192 91% 36%",
    },
    {
        "name": "Fuchsia",
        "primary": "292 84% 51%",
        "primary_foreground": "0 0% 100%",
        "brand": "292 84% 51%",
        "brand_2": "295 72% 45%",
        "blue": "292 84% 51%",
        "blue_2": "295 72% 45%",
    },
]

_KEYS = ("primary", "primary_foreground", "brand", "brand_2", "blue", "blue_2")


def _validate_palette(data: dict) -> dict[str, str]:
    out = dict(DEFAULT_PALETTE)
    for k in _KEYS:
        v = str(data.get(k) or "").strip()
        if v:
            out[k] = v
    name = str(data.get("name") or out.get("name") or DEFAULT_PALETTE["name"]).strip()
    out["name"] = name or DEFAULT_PALETTE["name"]
    if out.get("primary"):
        out["blue"] = out["primary"]
    if out.get("brand_2"):
        out["blue_2"] = out["brand_2"]
    return out


def get_palette() -> dict[str, str]:
    try:
        if _PALETTE_FILE.exists():
            raw = json.loads(_PALETTE_FILE.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return _validate_palette(raw)
    except Exception:
        pass
    return dict(DEFAULT_PALETTE)


def save_palette(data: dict) -> dict[str, str]:
    palette = _validate_palette(data)
    _PALETTE_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PALETTE_FILE.write_text(json.dumps(palette, indent=2), encoding="utf-8")
    return palette


def palette_response() -> dict:
    return {"palette": get_palette(), "presets": PRESET_PALETTES}
