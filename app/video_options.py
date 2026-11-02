"""Shared video format and duration presets for UI/API/pipeline stages."""
from __future__ import annotations

import re
from copy import deepcopy


VIDEO_FORMATS: dict[str, dict] = {
    "youtube_video": {
        "key": "youtube_video",
        "label": "YouTube Video",
        "platform": "YouTube",
        "description": "Standard 16:9 landscape video for full YouTube uploads.",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "width": 1920,
        "height": 1080,
        "min_duration": 15,
        "max_duration": 3600,
        "duration_options": [0, 60, 180, 300, 480, 600, 900, 1200, 1800, 3600],
        "recommended_duration": 480,
        "tags": ["education", "tutorial", "youtube video"],
    },
    "youtube_shorts": {
        "key": "youtube_shorts",
        "label": "YouTube Shorts",
        "platform": "YouTube Shorts",
        "description": "Vertical 9:16 short-form lesson. Supports current Shorts-friendly durations up to 3 minutes.",
        "aspect_ratio": "9:16",
        "orientation": "vertical",
        "width": 1080,
        "height": 1920,
        "min_duration": 15,
        "max_duration": 180,
        "duration_options": [0, 15, 30, 45, 60, 90, 120, 180],
        "recommended_duration": 60,
        "tags": ["education", "tutorial", "shorts", "#Shorts"],
    },
    "instagram_reels": {
        "key": "instagram_reels",
        "label": "Instagram Reels",
        "platform": "Instagram Reels",
        "description": "Vertical 9:16 Reels export with punchy pacing and mobile-safe framing.",
        "aspect_ratio": "9:16",
        "orientation": "vertical",
        "width": 1080,
        "height": 1920,
        "min_duration": 15,
        "max_duration": 180,
        "duration_options": [0, 15, 30, 45, 60, 90, 120, 180],
        "recommended_duration": 60,
        "tags": ["education", "tutorial", "instagram reels", "reels"],
    },
    "tiktok": {
        "key": "tiktok",
        "label": "TikTok",
        "platform": "TikTok",
        "description": "Vertical 9:16 TikTok video — fast hook, high energy, mobile-first.",
        "aspect_ratio": "9:16",
        "orientation": "vertical",
        "width": 1080,
        "height": 1920,
        "min_duration": 15,
        "max_duration": 600,
        "duration_options": [0, 15, 30, 45, 60, 90, 180, 300],
        "recommended_duration": 45,
        "tags": ["education", "tutorial", "tiktok", "fyp", "learnontiktok"],
    },
    "instagram_square": {
        "key": "instagram_square",
        "label": "Square (1:1)",
        "platform": "Instagram Feed",
        "description": "Square 1:1 feed video for Instagram/Facebook — great for in-feed autoplay.",
        "aspect_ratio": "1:1",
        "orientation": "square",
        "width": 1080,
        "height": 1080,
        "min_duration": 15,
        "max_duration": 600,
        "duration_options": [0, 30, 45, 60, 90, 120, 180, 300],
        "recommended_duration": 60,
        "tags": ["education", "tutorial", "instagram", "reels"],
    },
    "linkedin_video": {
        "key": "linkedin_video",
        "label": "LinkedIn Video",
        "platform": "LinkedIn",
        "description": "Landscape 16:9 video tuned for a professional LinkedIn audience.",
        "aspect_ratio": "16:9",
        "orientation": "landscape",
        "width": 1920,
        "height": 1080,
        "min_duration": 30,
        "max_duration": 600,
        "duration_options": [0, 60, 120, 180, 300, 600],
        "recommended_duration": 120,
        "tags": ["education", "professional", "linkedin", "career"],
    },
}


DEFAULT_VIDEO_FORMAT = "youtube_video"


# ---------------------------------------------------------------------------
#  VIDEO THEMES  (color palettes)
#
#  Each theme is fully self-contained so new ones can be added by appending a
#  dict here — no other code changes needed. A theme defines:
#    base      : global surface/text tokens + page background + grid line color
#    palettes  : the per-slide accent triples (--a primary, --b secondary,
#                --glow bg bloom) that rotate across slides to stay visually
#                fresh. Any length >= 1 works; slides cycle through them.
#    mermaid   : colors injected into Mermaid's themeVariables + active-node
#                highlight so diagrams match the palette.
#    swatch    : 2-3 representative colors shown in the UI picker.
# ---------------------------------------------------------------------------
VIDEO_THEMES: dict[str, dict] = {
    "aurora": {
        "key": "aurora",
        "label": "Aurora (Dark)",
        "description": "Dark node-graph aesthetic with vivid multi-color accents.",
        "base": {
            "ink": "#f4f4f5", "muted": "#a1a1aa", "panel": "#141417",
            "line": "rgba(255,255,255,.08)", "bg": "#0a0a0c",
            "grid": "rgba(255,255,255,.045)", "caption_bg": "rgba(10,10,12,.72)",
            "caption_text": "#d4d4d8", "diagram_bg": "#0b0b0f", "dark": True,
        },
        "palettes": [
            {"a": "#a855f7", "b": "#8b5cf6", "glow": "#7c3aed"},
            {"a": "#38bdf8", "b": "#22d3ee", "glow": "#0ea5e9"},
            {"a": "#fb5a3c", "b": "#ff8a5b", "glow": "#f43f5e"},
            {"a": "#34d399", "b": "#10b981", "glow": "#059669"},
            {"a": "#fbbf24", "b": "#f59e0b", "glow": "#d97706"},
            {"a": "#c084fc", "b": "#a855f7", "glow": "#9333ea"},
        ],
        "mermaid": {
            "primaryColor": "#17171c", "primaryBorderColor": "#a855f7",
            "primaryTextColor": "#f4f4f5", "lineColor": "#52525b",
            "mainBkg": "#141417", "secondaryColor": "#1c1c22",
            "tertiaryColor": "#0e0e12",
            "activeFill": "#a855f7", "activeStroke": "#c084fc",
        },
        "swatch": ["#a855f7", "#38bdf8", "#34d399"],
    },
    "midnight": {
        "key": "midnight",
        "label": "Midnight Blue",
        "description": "Calm deep-blue palette with cool cyan/indigo accents.",
        "base": {
            "ink": "#eef2ff", "muted": "#94a3c4", "panel": "#131a2b",
            "line": "rgba(148,163,196,.14)", "bg": "#080b16",
            "grid": "rgba(148,163,255,.05)", "caption_bg": "rgba(8,11,22,.74)",
            "caption_text": "#c7d2fe", "diagram_bg": "#0a0f1e", "dark": True,
        },
        "palettes": [
            {"a": "#60a5fa", "b": "#3b82f6", "glow": "#2563eb"},
            {"a": "#22d3ee", "b": "#06b6d4", "glow": "#0891b2"},
            {"a": "#818cf8", "b": "#6366f1", "glow": "#4f46e5"},
            {"a": "#5eead4", "b": "#2dd4bf", "glow": "#14b8a6"},
        ],
        "mermaid": {
            "primaryColor": "#16203a", "primaryBorderColor": "#60a5fa",
            "primaryTextColor": "#eef2ff", "lineColor": "#475569",
            "mainBkg": "#131a2b", "secondaryColor": "#1a2440",
            "tertiaryColor": "#0d1424",
            "activeFill": "#3b82f6", "activeStroke": "#93c5fd",
        },
        "swatch": ["#60a5fa", "#22d3ee", "#818cf8"],
    },
    "sunset": {
        "key": "sunset",
        "label": "Sunset Ember",
        "description": "Warm dark palette with amber, coral and rose accents.",
        "base": {
            "ink": "#fdf4ec", "muted": "#c9a99a", "panel": "#1e1512",
            "line": "rgba(255,214,170,.12)", "bg": "#120b09",
            "grid": "rgba(255,190,140,.05)", "caption_bg": "rgba(18,11,9,.74)",
            "caption_text": "#f5d6c2", "diagram_bg": "#170f0c", "dark": True,
        },
        "palettes": [
            {"a": "#fb923c", "b": "#f97316", "glow": "#ea580c"},
            {"a": "#fb7185", "b": "#f43f5e", "glow": "#e11d48"},
            {"a": "#fbbf24", "b": "#f59e0b", "glow": "#d97706"},
            {"a": "#f472b6", "b": "#ec4899", "glow": "#db2777"},
        ],
        "mermaid": {
            "primaryColor": "#241813", "primaryBorderColor": "#fb923c",
            "primaryTextColor": "#fdf4ec", "lineColor": "#7c5a4a",
            "mainBkg": "#1e1512", "secondaryColor": "#2a1c16",
            "tertiaryColor": "#170f0c",
            "activeFill": "#f97316", "activeStroke": "#fdba74",
        },
        "swatch": ["#fb923c", "#fb7185", "#fbbf24"],
    },
    "paper": {
        "key": "paper",
        "label": "Clean Light",
        "description": "Bright white palette with crisp indigo/teal accents.",
        "base": {
            "ink": "#0f172a", "muted": "#64748b", "panel": "#ffffff",
            "line": "rgba(15,23,42,.10)", "bg": "#f8fafc",
            "grid": "rgba(15,23,42,.045)", "caption_bg": "rgba(255,255,255,.85)",
            "caption_text": "#1e293b", "diagram_bg": "#ffffff", "dark": False,
        },
        "palettes": [
            {"a": "#6366f1", "b": "#818cf8", "glow": "#a5b4fc"},
            {"a": "#0ea5e9", "b": "#38bdf8", "glow": "#7dd3fc"},
            {"a": "#059669", "b": "#10b981", "glow": "#6ee7b7"},
            {"a": "#e11d48", "b": "#f43f5e", "glow": "#fda4af"},
            {"a": "#d97706", "b": "#f59e0b", "glow": "#fcd34d"},
        ],
        "mermaid": {
            "primaryColor": "#eef2ff", "primaryBorderColor": "#6366f1",
            "primaryTextColor": "#0f172a", "lineColor": "#94a3b8",
            "mainBkg": "#ffffff", "secondaryColor": "#f1f5f9",
            "tertiaryColor": "#e2e8f0",
            "activeFill": "#6366f1", "activeStroke": "#4f46e5",
        },
        "swatch": ["#6366f1", "#0ea5e9", "#059669"],
    },
    "emerald": {
        "key": "emerald",
        "label": "Emerald Terminal",
        "description": "Dark console look with matrix-green and lime accents.",
        "base": {
            "ink": "#e7fbef", "muted": "#7fae92", "panel": "#0f1a14",
            "line": "rgba(110,231,183,.14)", "bg": "#060d0a",
            "grid": "rgba(52,211,153,.05)", "caption_bg": "rgba(6,13,10,.76)",
            "caption_text": "#bbf7d0", "diagram_bg": "#08120d", "dark": True,
        },
        "palettes": [
            {"a": "#34d399", "b": "#10b981", "glow": "#059669"},
            {"a": "#a3e635", "b": "#84cc16", "glow": "#65a30d"},
            {"a": "#2dd4bf", "b": "#14b8a6", "glow": "#0d9488"},
            {"a": "#4ade80", "b": "#22c55e", "glow": "#16a34a"},
        ],
        "mermaid": {
            "primaryColor": "#0f1f18", "primaryBorderColor": "#34d399",
            "primaryTextColor": "#e7fbef", "lineColor": "#3f6b54",
            "mainBkg": "#0f1a14", "secondaryColor": "#12271d",
            "tertiaryColor": "#08120d",
            "activeFill": "#10b981", "activeStroke": "#6ee7b7",
        },
        "swatch": ["#34d399", "#a3e635", "#2dd4bf"],
    },
    "nebula": {
        "key": "nebula",
        "label": "Nebula",
        "description": "Deep violet space with magenta, pink and blue glow.",
        "base": {
            "ink": "#f6effe", "muted": "#b0a0c9", "panel": "#1a1130",
            "line": "rgba(216,180,254,.14)", "bg": "#0c0718",
            "grid": "rgba(192,132,252,.06)", "caption_bg": "rgba(12,7,24,.76)",
            "caption_text": "#e9d5ff", "diagram_bg": "#100a22", "dark": True,
        },
        "palettes": [
            {"a": "#e879f9", "b": "#d946ef", "glow": "#c026d3"},
            {"a": "#a78bfa", "b": "#8b5cf6", "glow": "#7c3aed"},
            {"a": "#f472b6", "b": "#ec4899", "glow": "#db2777"},
            {"a": "#818cf8", "b": "#6366f1", "glow": "#4f46e5"},
        ],
        "mermaid": {
            "primaryColor": "#221641", "primaryBorderColor": "#e879f9",
            "primaryTextColor": "#f6effe", "lineColor": "#6d5a8f",
            "mainBkg": "#1a1130", "secondaryColor": "#261849",
            "tertiaryColor": "#100a22",
            "activeFill": "#d946ef", "activeStroke": "#f0abfc",
        },
        "swatch": ["#e879f9", "#a78bfa", "#f472b6"],
    },
    "slate": {
        "key": "slate",
        "label": "Slate Mono",
        "description": "Minimal graphite palette with a single steel-blue accent.",
        "base": {
            "ink": "#f1f5f9", "muted": "#94a3b8", "panel": "#1e242e",
            "line": "rgba(148,163,184,.16)", "bg": "#0d1117",
            "grid": "rgba(148,163,184,.05)", "caption_bg": "rgba(13,17,23,.78)",
            "caption_text": "#cbd5e1", "diagram_bg": "#11161d", "dark": True,
        },
        "palettes": [
            {"a": "#7dd3fc", "b": "#38bdf8", "glow": "#0ea5e9"},
            {"a": "#cbd5e1", "b": "#94a3b8", "glow": "#64748b"},
            {"a": "#93c5fd", "b": "#60a5fa", "glow": "#3b82f6"},
        ],
        "mermaid": {
            "primaryColor": "#232a35", "primaryBorderColor": "#7dd3fc",
            "primaryTextColor": "#f1f5f9", "lineColor": "#4b5563",
            "mainBkg": "#1e242e", "secondaryColor": "#2a323e",
            "tertiaryColor": "#11161d",
            "activeFill": "#38bdf8", "activeStroke": "#bae6fd",
        },
        "swatch": ["#7dd3fc", "#94a3b8", "#60a5fa"],
    },
    "cyber": {
        "key": "cyber",
        "label": "Cyberpunk Neon",
        "description": "High-energy neon: hot pink, electric cyan and yellow.",
        "base": {
            "ink": "#f7f7ff", "muted": "#9aa0c4", "panel": "#140b1f",
            "line": "rgba(34,211,238,.18)", "bg": "#080611",
            "grid": "rgba(236,72,153,.06)", "caption_bg": "rgba(8,6,17,.78)",
            "caption_text": "#e5f9ff", "diagram_bg": "#0c0819", "dark": True,
        },
        "palettes": [
            {"a": "#f0abfc", "b": "#e879f9", "glow": "#d946ef"},
            {"a": "#22d3ee", "b": "#06b6d4", "glow": "#0891b2"},
            {"a": "#fde047", "b": "#facc15", "glow": "#eab308"},
            {"a": "#fb7185", "b": "#f43f5e", "glow": "#e11d48"},
        ],
        "mermaid": {
            "primaryColor": "#1c1130", "primaryBorderColor": "#22d3ee",
            "primaryTextColor": "#f7f7ff", "lineColor": "#5b5488",
            "mainBkg": "#140b1f", "secondaryColor": "#231541",
            "tertiaryColor": "#0c0819",
            "activeFill": "#e879f9", "activeStroke": "#67e8f9",
        },
        "swatch": ["#f0abfc", "#22d3ee", "#fde047"],
    },
    "mint": {
        "key": "mint",
        "label": "Mint Light",
        "description": "Airy light theme with fresh teal and green accents.",
        "base": {
            "ink": "#0f2b25", "muted": "#5b7c72", "panel": "#ffffff",
            "line": "rgba(15,43,37,.10)", "bg": "#f2fbf7",
            "grid": "rgba(16,185,129,.05)", "caption_bg": "rgba(255,255,255,.86)",
            "caption_text": "#134e4a", "diagram_bg": "#ffffff", "dark": False,
        },
        "palettes": [
            {"a": "#0d9488", "b": "#14b8a6", "glow": "#5eead4"},
            {"a": "#059669", "b": "#10b981", "glow": "#6ee7b7"},
            {"a": "#0891b2", "b": "#06b6d4", "glow": "#67e8f9"},
            {"a": "#65a30d", "b": "#84cc16", "glow": "#bef264"},
        ],
        "mermaid": {
            "primaryColor": "#e6fffb", "primaryBorderColor": "#0d9488",
            "primaryTextColor": "#0f2b25", "lineColor": "#94a3b8",
            "mainBkg": "#ffffff", "secondaryColor": "#f0fdfa",
            "tertiaryColor": "#e2e8f0",
            "activeFill": "#0d9488", "activeStroke": "#0f766e",
        },
        "swatch": ["#0d9488", "#059669", "#0891b2"],
    },
    "mono": {
        "key": "mono",
        "label": "High Contrast",
        "description": "Bold near-black canvas with a crisp white/amber accent.",
        "base": {
            "ink": "#ffffff", "muted": "#a3a3a3", "panel": "#161616",
            "line": "rgba(255,255,255,.14)", "bg": "#000000",
            "grid": "rgba(255,255,255,.05)", "caption_bg": "rgba(0,0,0,.82)",
            "caption_text": "#e5e5e5", "diagram_bg": "#0a0a0a", "dark": True,
        },
        "palettes": [
            {"a": "#fafafa", "b": "#d4d4d4", "glow": "#a3a3a3"},
            {"a": "#fbbf24", "b": "#f59e0b", "glow": "#d97706"},
            {"a": "#e5e5e5", "b": "#a3a3a3", "glow": "#737373"},
        ],
        "mermaid": {
            "primaryColor": "#1c1c1c", "primaryBorderColor": "#fafafa",
            "primaryTextColor": "#ffffff", "lineColor": "#525252",
            "mainBkg": "#161616", "secondaryColor": "#242424",
            "tertiaryColor": "#0a0a0a",
            "activeFill": "#fbbf24", "activeStroke": "#fde68a",
        },
        "swatch": ["#fafafa", "#fbbf24", "#a3a3a3"],
    },
    "snow": {
        "key": "snow",
        "label": "Snow (White)",
        "description": "Pure white canvas with graphite ink and coral accent.",
        "base": {
            "ink": "#0a0a0a", "muted": "#6b7280", "panel": "#ffffff",
            "line": "rgba(10,10,10,.09)", "bg": "#ffffff",
            "grid": "rgba(10,10,10,.04)", "caption_bg": "rgba(255,255,255,.9)",
            "caption_text": "#111827", "diagram_bg": "#ffffff", "dark": False,
        },
        "palettes": [
            {"a": "#ff5a3c", "b": "#ff7a5c", "glow": "#ffb4a2"},
            {"a": "#2563eb", "b": "#3b82f6", "glow": "#93c5fd"},
            {"a": "#7c3aed", "b": "#8b5cf6", "glow": "#c4b5fd"},
            {"a": "#0d9488", "b": "#14b8a6", "glow": "#5eead4"},
        ],
        "mermaid": {
            "primaryColor": "#f5f5f5", "primaryBorderColor": "#ff5a3c",
            "primaryTextColor": "#0a0a0a", "lineColor": "#9ca3af",
            "mainBkg": "#ffffff", "secondaryColor": "#f3f4f6",
            "tertiaryColor": "#e5e7eb",
            "activeFill": "#ff5a3c", "activeStroke": "#e11d48",
        },
        "swatch": ["#ff5a3c", "#2563eb", "#7c3aed"],
    },
    "ivory": {
        "key": "ivory",
        "label": "Ivory (Warm White)",
        "description": "Warm off-white paper with espresso ink and amber accent.",
        "base": {
            "ink": "#292524", "muted": "#78716c", "panel": "#fffdf8",
            "line": "rgba(41,37,36,.10)", "bg": "#faf7f0",
            "grid": "rgba(41,37,36,.04)", "caption_bg": "rgba(255,253,248,.9)",
            "caption_text": "#44403c", "diagram_bg": "#fffdf8", "dark": False,
        },
        "palettes": [
            {"a": "#c2410c", "b": "#ea580c", "glow": "#fdba74"},
            {"a": "#a16207", "b": "#ca8a04", "glow": "#fde047"},
            {"a": "#9f1239", "b": "#be123c", "glow": "#fda4af"},
            {"a": "#4d7c0f", "b": "#65a30d", "glow": "#bef264"},
        ],
        "mermaid": {
            "primaryColor": "#f5efe3", "primaryBorderColor": "#c2410c",
            "primaryTextColor": "#292524", "lineColor": "#a8a29e",
            "mainBkg": "#fffdf8", "secondaryColor": "#f5efe3",
            "tertiaryColor": "#ece5d6",
            "activeFill": "#c2410c", "activeStroke": "#9a3412",
        },
        "swatch": ["#c2410c", "#a16207", "#9f1239"],
    },
}



def _make_theme(key, label, desc, *, dark, bg, ink, muted, panel, accents):
    """Build a theme entry from a handful of colours (4 accent rotations)."""
    line = "rgba(255,255,255,.10)" if dark else "rgba(10,10,10,.10)"
    grid = "rgba(255,255,255,.045)" if dark else "rgba(10,10,10,.04)"
    cap_bg = "rgba(0,0,0,.62)" if dark else "rgba(255,255,255,.92)"
    return {
        "key": key,
        "label": label,
        "description": desc,
        "base": {
            "ink": ink, "muted": muted, "panel": panel, "line": line, "bg": bg,
            "grid": grid, "caption_bg": cap_bg, "caption_text": ink,
            "diagram_bg": bg, "dark": dark,
        },
        "palettes": [{"a": a, "b": b, "glow": g} for a, b, g in accents],
        "mermaid": {
            "primaryColor": panel, "primaryBorderColor": accents[0][0],
            "primaryTextColor": ink, "lineColor": muted, "mainBkg": panel,
            "secondaryColor": panel, "tertiaryColor": bg,
            "activeFill": accents[0][0], "activeStroke": accents[0][1],
        },
        "swatch": [accents[0][0], accents[1][0], accents[2][0]],
    }


# More colour choices. Every one is a full palette, usable with any template.
_NEW_THEMES = (
    ("ocean", "Ocean (Light)", "Cool white with deep-sea ink and teal, blue and cyan accents.",
     dict(dark=False, bg="#f4fbfd", ink="#08303f", muted="#4b7686", panel="#ffffff",
          accents=[("#0891b2", "#06b6d4", "#67e8f9"), ("#2563eb", "#3b82f6", "#93c5fd"),
                   ("#0d9488", "#14b8a6", "#5eead4"), ("#7c3aed", "#8b5cf6", "#c4b5fd")])),
    ("forest", "Forest (Dark)", "Deep green night with leaf, lime and amber accents.",
     dict(dark=True, bg="#08130d", ink="#ecfdf3", muted="#8fb7a1", panel="#10201a",
          accents=[("#34d399", "#10b981", "#059669"), ("#a3e635", "#84cc16", "#65a30d"),
                   ("#fbbf24", "#f59e0b", "#d97706"), ("#2dd4bf", "#14b8a6", "#0d9488")])),
    ("rose", "Rose (Blush)", "Soft blush paper with wine ink and rose, plum and gold accents.",
     dict(dark=False, bg="#fff5f6", ink="#3b0d1a", muted="#8a5563", panel="#ffffff",
          accents=[("#e11d48", "#f43f5e", "#fda4af"), ("#9333ea", "#a855f7", "#d8b4fe"),
                   ("#d97706", "#f59e0b", "#fcd34d"), ("#be185d", "#db2777", "#f9a8d4")])),
    ("citrus", "Citrus (Bright)", "Sunny cream with charcoal ink and lime, orange and sky accents.",
     dict(dark=False, bg="#fffdf0", ink="#1c1917", muted="#6b6558", panel="#ffffff",
          accents=[("#ea580c", "#f97316", "#fdba74"), ("#65a30d", "#84cc16", "#bef264"),
                   ("#0284c7", "#0ea5e9", "#7dd3fc"), ("#ca8a04", "#eab308", "#fde047")])),
    ("grape", "Grape (Dark)", "Deep violet night with orchid, pink and cyan accents.",
     dict(dark=True, bg="#0f0a1f", ink="#f5f0ff", muted="#a99bd1", panel="#191230",
          accents=[("#c084fc", "#a855f7", "#7e22ce"), ("#f472b6", "#ec4899", "#be185d"),
                   ("#22d3ee", "#06b6d4", "#0e7490"), ("#facc15", "#eab308", "#a16207")])),
    ("graphite", "Graphite (Dark)", "Neutral charcoal with a single hot orange and cool blue accents.",
     dict(dark=True, bg="#141414", ink="#f5f5f5", muted="#a3a3a3", panel="#1f1f1f",
          accents=[("#fb923c", "#f97316", "#c2410c"), ("#60a5fa", "#3b82f6", "#1d4ed8"),
                   ("#f87171", "#ef4444", "#b91c1c"), ("#a3e635", "#84cc16", "#4d7c0f")])),
    ("sand", "Sand (Warm)", "Desert paper with brown ink and terracotta, olive and teal accents.",
     dict(dark=False, bg="#f6eddc", ink="#3a2a17", muted="#7d6a50", panel="#fffaf0",
          accents=[("#b45309", "#d97706", "#fcd34d"), ("#4d7c0f", "#65a30d", "#bef264"),
                   ("#0f766e", "#14b8a6", "#5eead4"), ("#9f1239", "#be123c", "#fda4af")])),
    ("sky", "Sky (Light)", "Airy pale blue with navy ink and blue, orange and green accents.",
     dict(dark=False, bg="#eef6ff", ink="#0b1f3a", muted="#52698a", panel="#ffffff",
          accents=[("#1d4ed8", "#2563eb", "#93c5fd"), ("#ea580c", "#f97316", "#fdba74"),
                   ("#059669", "#10b981", "#6ee7b7"), ("#7c3aed", "#8b5cf6", "#c4b5fd")])),
)
for _k, _l, _d, _kw in _NEW_THEMES:
    VIDEO_THEMES.setdefault(_k, _make_theme(_k, _l, _d, **_kw))

DEFAULT_VIDEO_THEME = "aurora"


# ---------------------------------------------------------------------------
#  VIDEO STYLES  (a sub-theme axis, orthogonal to color)
#
#  A "style" controls the *visual language* of a deck independent of its color
#  theme: typography scale, card shape, border/shadow emphasis, and spacing.
#  This lets a user pick, say, an Aurora color theme in a "Bold" style or a
#  "Minimal" style. Styles are injected as CSS custom properties consumed by
#  the slide template, so adding a new one here needs no other code changes.
#  Every token is a plain CSS value.
# ---------------------------------------------------------------------------
# Default story arc injected into the slide LLM prompt when a style omits one.
DEFAULT_STORY_ARC = (
    "1) hook or cover → 2) define the thing (hub/panel/bullets with analogy) "
    "→ 3) compare alternatives (compare/bars) → 4) how it works (flow/steps) "
    "→ 5) catch / limits / edge cases (quote or bullets) → 6) key takeaways."
)

# Visual style families shown in Studio / Admin filters.
STYLE_CATEGORIES: dict[str, str] = {
    "teach": "Teach",
    "motion": "Motion",
    "hyper": "HyperFrames",
    "decks": "Decks",
    "story": "Story",
    "data": "Data",
    "systems": "Code",
}

# Default category for legacy styles that omit an explicit field.
_STYLE_CATEGORY_DEFAULTS: dict[str, str] = {
    "hybrid": "hybrid",
    "modern": "decks", "minimal": "decks", "cards": "decks", "glass": "decks",
    "bold": "motion",
    "pitch": "ppt", "corporate": "ppt", "saas": "ppt",
    "gamma": "ppt", "keynote": "ppt", "slides": "ppt", "notion": "ppt",
    "geo_navy": "modern_ppt", "coral_split": "modern_ppt", "blush_soft": "modern_ppt",
    "mosaic": "modern_ppt", "process": "modern_ppt", "agenda": "modern_ppt",
    "rainbow_bar": "modern_ppt", "circle_stack": "modern_ppt",
    "hex_grid": "modern_ppt", "wave_soft": "modern_ppt",
    "swiss_pulse": "hyper", "velvet_std": "hyper", "deconstructed": "hyper",
    "maximalist": "hyper", "data_drift": "hyper", "soft_signal": "hyper",
    "folk_freq": "hyper", "shadow_cut": "hyper",
    "kinetic_center": "motion", "lower_third": "motion", "promo_sprint": "motion",
    "caption_pop": "motion", "chart_race": "motion", "logo_intro": "motion",
    "bento": "content", "big_stat": "content", "quote_pull": "content",
    "timeline_rail": "content", "split_media": "content",
    "proof_duo": "content", "kpi_strip": "content", "stack_cards": "content",
    "explainer": "teach", "tutorial": "teach", "whiteboard": "teach",
    "teardown": "teach", "playful": "teach",
    "documentary": "story", "editorial": "story", "cinematic": "story",
    "neon": "tech", "blueprint": "tech", "terminal": "tech", "dataviz": "tech",
}


VIDEO_STYLES: dict[str, dict] = {
    "modern": {
        "key": "modern",
        "label": "Modern",
        "description": "Balanced default — rounded cards, soft shadows, clean sans.",
        "example": "Tech explainer · product demo",
        "template": "Title → 3 bullets → diagram",
        "story_arc": DEFAULT_STORY_ARC,
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1", "h2_spacing": "-.02em",
            "card_radius": "16px", "card_border": "1px",
            "card_shadow": "0 16px 40px rgba(0,0,0,.4)",
            "panel_alpha": "1", "grid_opacity": ".6", "blob_opacity": ".22",
            "uppercase_kicker": "uppercase",
        },
    },
    "minimal": {
        "key": "minimal",
        "label": "Minimal",
        "description": "Flat, quiet and spacious — hairline borders, no glow, light weight.",
        "example": "Research summary · whitepaper",
        "template": "Headline → sparse text → quote",
        "story_arc": (
            "1) quiet cover/title → 2) one big idea (quote or hub) → 3) 3–4 sparse "
            "bullets with breathing room → 4) single compare or flow → 5) one "
            "memorable closing line. Prefer fewer items per slide; never crowd."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "600", "h2_scale": "1", "h2_spacing": "-.01em",
            "card_radius": "10px", "card_border": "1px",
            "card_shadow": "none",
            "panel_alpha": ".55", "grid_opacity": ".25", "blob_opacity": ".08",
            "uppercase_kicker": "none",
        },
    },
    "editorial": {
        "key": "editorial",
        "label": "Editorial",
        "description": "Magazine feel — serif headings, generous tracking, refined cards.",
        "example": "Essay · long-form narrative",
        "template": "Kicker → serif title → pull-quote",
        "story_arc": (
            "1) magazine kicker + title → 2) pull-quote that frames the thesis → "
            "3) scene-setting bullets → 4) deep dive (panel/flow) → 5) counterpoint "
            "(compare) → 6) elegant closing takeaway. Narration may be slightly "
            "more literary; on-screen text stays sparse and typographic."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Georgia,"Times New Roman",serif',
            "h2_weight": "700", "h2_scale": "1.04", "h2_spacing": "-.015em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 20px 50px rgba(0,0,0,.35)",
            "panel_alpha": ".9", "grid_opacity": ".4", "blob_opacity": ".16",
            "uppercase_kicker": "uppercase",
        },
    },
    "bold": {
        "key": "bold",
        "label": "Bold",
        "description": "High-impact — heavy headings, chunky cards, strong glow.",
        "example": "Hook video · social clip",
        "template": "Big stat → punch line → CTA",
        "story_arc": (
            "1) huge hook number/stat → 2) punchline quote → 3) 2–3 rapid bars or "
            "bullets → 4) one flow of the method → 5) hard CTA / takeaway. Short "
            "sentences; maximum visual weight; almost no dense text."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "900", "h2_scale": "1.12", "h2_spacing": "-.03em",
            "card_radius": "20px", "card_border": "2px",
            "card_shadow": "0 24px 60px rgba(0,0,0,.5)",
            "panel_alpha": "1", "grid_opacity": ".7", "blob_opacity": ".32",
            "uppercase_kicker": "uppercase",
        },
    },
    "explainer": {
        "key": "explainer",
        "label": "Explainer",
        "description": "Tech YouTube style — kinetic hook numbers, compare bars, system-design pacing.",
        "example": "System design · product teardown",
        "template": "Hook → define → compare → flow → catch → verdict",
        "story_arc": DEFAULT_STORY_ARC,
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.06", "h2_spacing": "-.025em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 18px 48px rgba(0,0,0,.45)",
            "panel_alpha": "1", "grid_opacity": ".55", "blob_opacity": ".2",
            "uppercase_kicker": "uppercase",
        },
    },
    "documentary": {
        "key": "documentary",
        "label": "Documentary",
        "description": "Story-led teaching — context, characters (ideas), evidence, resolution.",
        "example": "Research paper walkthrough · history of an idea",
        "template": "Scene → stakes → evidence → mechanism → resolution",
        "story_arc": (
            "1) cover/scene-setting hook (why this matters now) → 2) cast of concepts "
            "(hub) → 3) the problem world (compare before/after or myth/reality) → "
            "4) evidence trail (stat + bullets with concrete examples) → 5) mechanism "
            "revealed (flow/steps/diagram) → 6) what changed / what to watch next "
            "(quote + takeaways). Lean on narrative bridges in narration."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Georgia,"Times New Roman",serif',
            "h2_weight": "700", "h2_scale": "1.02", "h2_spacing": "-.01em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 14px 36px rgba(0,0,0,.38)",
            "panel_alpha": ".95", "grid_opacity": ".35", "blob_opacity": ".14",
            "uppercase_kicker": "uppercase",
        },
    },
    "teardown": {
        "key": "teardown",
        "label": "Teardown",
        "description": "Product / system teardown — surface → guts → trade-offs → verdict.",
        "example": "Architecture review · model/API teardown",
        "template": "Promise → anatomy → guts → trade-offs → score",
        "story_arc": (
            "1) hook with the bold claim or price/perf number → 2) what it is "
            "(hub/panel of surface API) → 3) anatomy / how the pieces connect (flow) "
            "→ 4) deep guts (steps or diagram of internals) → 5) trade-offs "
            "(compare / bars) → 6) scored verdict + when to use it (bullets)."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.08", "h2_spacing": "-.028em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 20px 52px rgba(0,0,0,.48)",
            "panel_alpha": "1", "grid_opacity": ".6", "blob_opacity": ".24",
            "uppercase_kicker": "uppercase",
        },
    },
    "tutorial": {
        "key": "tutorial",
        "label": "Tutorial",
        "description": "Do-this-now teaching — goals, steps, pitfalls, checklist.",
        "example": "How-to · lab walkthrough",
        "template": "Goal → steps → pitfall → checklist",
        "story_arc": (
            "1) goal hook (what you'll be able to do) → 2) prerequisites / setup "
            "(panel or bullets) → 3–5) numbered how-to (prefer steps/flow layouts; "
            "one major action per slide) → 6) common pitfalls (compare do/don't) → "
            "7) checklist takeaways. Narration should sound like a patient coach."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1", "h2_spacing": "-.02em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 16px 40px rgba(0,0,0,.4)",
            "panel_alpha": "1", "grid_opacity": ".5", "blob_opacity": ".18",
            "uppercase_kicker": "uppercase",
        },
    },
    "whiteboard": {
        "key": "whiteboard",
        "label": "Teach · board",
        "description": "Sketch-first — marker strokes, grid board, hubs and progressive builds.",
        "example": "System design interview · concept map",
        "template": "Board → build → connect → annotate → recap",
        "story_arc": (
            "1) blank-board hook stating the question → 2) place the core node (hub) "
            "→ 3) grow connections (flow/diagram with active_node) → 4) annotate "
            "constraints (short bullets) → 5) alternate design (compare) → 6) recap "
            "as takeaways. Prefer diagram/flow/hub/transform; labels only — never "
            "dense paragraphs on the board."
        ),
        "tokens": {
            "font": '"Caveat","DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Caveat","DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.2", "h2_spacing": "-.01em",
            "card_radius": "8px", "card_border": "2px",
            "card_shadow": "3px 3px 0 rgba(15,23,42,.12)",
            "panel_alpha": ".94", "grid_opacity": ".5", "blob_opacity": ".06",
            "uppercase_kicker": "none",
        },
    },
    "cinematic": {
        "key": "cinematic",
        "label": "Cinematic",
        "description": "High-drama pacing — big visuals, short titles, emotional beats.",
        "example": "Launch film · vision piece",
        "template": "Cold open → world → turn → reveal → close",
        "story_arc": (
            "1) cold-open image/number with almost no text → 2) establish the world "
            "(quote or sparse bullets) → 3) rising tension / problem (bars or compare) "
            "→ 4) the reveal (transform or flow) → 5) emotional close + one line CTA. "
            "Max 3 on-screen items per slide; narration carries the story."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.14", "h2_spacing": "-.035em",
            "card_radius": "18px", "card_border": "0px",
            "card_shadow": "0 28px 70px rgba(0,0,0,.55)",
            "panel_alpha": ".85", "grid_opacity": ".2", "blob_opacity": ".28",
            "uppercase_kicker": "uppercase",
        },
    },
    "neon": {
        "key": "neon",
        "label": "Neon",
        "description": "Retro-futuristic glassmorphism — glowing edges, gradient accents, night-mode energy.",
        "example": "AI launch · hype trailer",
        "template": "Glow hook → gradient stat → neon flow → CTA",
        "story_arc": (
            "1) glowing hook number/line on dark glass → 2) one gradient stat → "
            "3) 2–3 neon cards (define/compare) → 4) a luminous flow of the method "
            "→ 5) bright CTA close. Keep text tight; let the glow carry the mood."
        ),
        "tokens": {
            "font": '"Space Grotesk","DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.1", "h2_spacing": "-.03em",
            "card_radius": "18px", "card_border": "1px",
            "card_shadow": "0 0 48px rgba(99,102,241,.45)",
            "panel_alpha": ".7", "grid_opacity": ".5", "blob_opacity": ".4",
            "uppercase_kicker": "uppercase",
        },
    },
    "blueprint": {
        "key": "blueprint",
        "label": "Blueprint",
        "description": "Technical schematic — grid paper, hairline drawings, engineering annotations.",
        "example": "Architecture spec · system diagram",
        "template": "Spec → schematic → callouts → dimensions → sign-off",
        "story_arc": (
            "1) title block hook (project name + one-line spec) → 2) place the core "
            "schematic (hub/diagram on grid) → 3) label parts with callouts (bullets "
            "beside the drawing) → 4) dimensions / trade-offs (compare or bars) → "
            "5) revision-note takeaways. Prefer diagram/flow/hub; text reads like "
            "engineering annotations."
        ),
        "tokens": {
            "font": '"IBM Plex Mono","DM Mono",ui-monospace,monospace',
            "h2_weight": "600", "h2_scale": "1", "h2_spacing": "0",
            "card_radius": "4px", "card_border": "1px",
            "card_shadow": "none",
            "panel_alpha": ".6", "grid_opacity": ".9", "blob_opacity": ".06",
            "uppercase_kicker": "uppercase",
        },
    },
    "playful": {
        "key": "playful",
        "label": "Playful",
        "description": "Friendly and rounded — chunky shapes, bouncy accents, approachable teaching.",
        "example": "Beginner explainer · fun how-to",
        "template": "Big friendly hook → sticker cards → steps → cheerful close",
        "story_arc": (
            "1) warm, friendly hook (a question or fun number) → 2) 3 sticker-style "
            "idea cards → 3) simple numbered steps → 4) a light compare (this vs that) "
            "→ 5) upbeat takeaway with an emoji-free but cheerful CTA. Keep language "
            "plain and encouraging; one idea per card."
        ),
        "tokens": {
            "font": '"Baloo 2","Quicksand",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.05", "h2_spacing": "-.01em",
            "card_radius": "24px", "card_border": "2px",
            "card_shadow": "0 14px 34px rgba(0,0,0,.28)",
            "panel_alpha": "1", "grid_opacity": ".35", "blob_opacity": ".3",
            "uppercase_kicker": "none",
        },
    },
    "terminal": {
        "key": "terminal",
        "label": "Terminal",
        "description": "Developer console — monospace, command prompts, code panels, dark IDE feel.",
        "example": "Coding tutorial · CLI walkthrough",
        "template": "Prompt → command → output → diff → recap",
        "story_arc": (
            "1) shell-prompt hook (the goal as a command) → 2) what we're building "
            "(panel/hub) → 3) run the commands (steps as terminal lines) → 4) show "
            "output / a diff (panel or compare) → 5) recap as a checklist of commands. "
            "Prefer panel/steps layouts; text reads like a terminal session."
        ),
        "tokens": {
            "font": '"JetBrains Mono","Fira Code",ui-monospace,monospace',
            "h2_weight": "700", "h2_scale": "1", "h2_spacing": "-.01em",
            "card_radius": "8px", "card_border": "1px",
            "card_shadow": "0 16px 40px rgba(0,0,0,.5)",
            "panel_alpha": ".92", "grid_opacity": ".3", "blob_opacity": ".12",
            "uppercase_kicker": "none",
        },
    },
    "hybrid": {
        "key": "hybrid",
        "label": "Hybrid",
        "description": "Mix of all templates — rotate hook, teach, teardown, and close beats by content type.",
        "example": "Long-form channel video · mixed lesson",
        "template": (
            "Content-format mix: hook/stat → define (hub/panel) → compare/bars → "
            "teach (steps/flow) → evidence (matrix/timeline) → code (panel) → "
            "transform → quote → cinematic close"
        ),
        "story_arc": (
            "HYBRID (content-format pack — deliberately rotate skins; never stay "
            "in one layout family for more than 1–2 slides):\n"
            "CONTENT FORMAT → LAYOUT VARIETIES (pick what the source supports):\n"
            "  • Hook / cold open → hook, stat, or bold quote\n"
            "  • Definition / concept → hub, panel, or 3-card bullets\n"
            "  • Comparison / trade-offs → compare, bars, or scorecard-style matrix\n"
            "  • Process / how-to → steps, flow (linked pipeline), or diagram\n"
            "  • Evidence / facets → matrix (2×2–2×3), timeline-ish steps, or hub\n"
            "  • Code / config / API → panel (terminal mock)\n"
            "  • Before/after or cleanup → transform\n"
            "  • Insight beat → quote (one pivotal line)\n"
            "  • Close → sparse cinematic line + light CTA\n"
            "ARC SHAPE: 1) Bold/cinematic hook → 2) Explainer define → 3) Teardown "
            "compare → 4) Tutorial teach → 5) Documentary/evidence catch → "
            "6) Minimal/cinematic land. "
            "Vary layout every slide when possible; blend dense teaching frames "
            "with sparse emotional beats so the video feels like a full channel "
            "pack — not one repeated skin."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Georgia,"Times New Roman",serif',
            "h2_weight": "800", "h2_scale": "1.06", "h2_spacing": "-.025em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 18px 48px rgba(0,0,0,.42)",
            "panel_alpha": ".95", "grid_opacity": ".5", "blob_opacity": ".2",
            "uppercase_kicker": "uppercase",
        },
    },
    # ---- Hybrid varieties ----
    "hybrid_kinetic": {
        "key": "hybrid_kinetic",
        "label": "Hybrid Kinetic",
        "category": "hybrid",
        "description": "Hybrid pack biased to Remotion-style kinetic type — big words, short beats, motion-first teaching.",
        "example": "Kinetic explainer · channel opener",
        "template": "Word slam → define → compare → type build → close",
        "story_arc": (
            "HYBRID KINETIC: rotate skins but prefer text-forward layouts.\n"
            "1) kinetic hook (one huge word/number) → 2) define with 3 short cards → "
            "3) compare/bars in punchy lines → 4) steps as type builds → 5) sparse "
            "cinematic close. Max 6–8 words per title; narration carries detail."
        ),
        "tokens": {
            "font": '"Space Grotesk","DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "900", "h2_scale": "1.16", "h2_spacing": "-.04em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 20px 50px rgba(0,0,0,.48)",
            "panel_alpha": ".9", "grid_opacity": ".35", "blob_opacity": ".26",
            "uppercase_kicker": "uppercase",
        },
    },
    "hybrid_data": {
        "key": "hybrid_data",
        "label": "Hybrid Data",
        "category": "hybrid",
        "description": "Hybrid pack for metrics — scorecards, bars, gauges, and evidence-heavy slides.",
        "example": "Benchmark video · KPI review",
        "template": "KPI hook → scorecard → bars → method → verdict",
        "story_arc": (
            "HYBRID DATA: rotate layouts but favor numbers and charts.\n"
            "1) big KPI hook → 2) scorecard / matrix of facets → 3) bars or compare → "
            "4) short method flow → 5) evidence catch → 6) numeric verdict. Every "
            "other slide should carry a concrete figure."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.04", "h2_spacing": "-.02em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 16px 42px rgba(0,0,0,.4)",
            "panel_alpha": "1", "grid_opacity": ".55", "blob_opacity": ".18",
            "uppercase_kicker": "uppercase",
        },
    },
    "hybrid_story": {
        "key": "hybrid_story",
        "label": "Hybrid Story",
        "category": "hybrid",
        "description": "Hybrid pack with documentary pacing — scene, stakes, evidence, teach, land.",
        "example": "Paper story · idea history",
        "template": "Scene → stakes → evidence → teach → land",
        "story_arc": (
            "HYBRID STORY: blend documentary beats with explainer teaching.\n"
            "1) scene-setting cover → 2) stakes / cast (hub) → 3) evidence trail → "
            "4) mechanism teach (flow/steps) → 5) trade-offs → 6) quiet close. "
            "Alternate sparse emotional slides with denser teaching frames."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,system-ui,sans-serif',
            "h2_font": 'Georgia,"Times New Roman",serif',
            "h2_weight": "750", "h2_scale": "1.05", "h2_spacing": "-.015em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 18px 46px rgba(0,0,0,.4)",
            "panel_alpha": ".92", "grid_opacity": ".4", "blob_opacity": ".16",
            "uppercase_kicker": "uppercase",
        },
    },
    # ---- Motion · Remotion / Hyperframes ----
    "kinetic": {
        "key": "kinetic",
        "label": "Kinetic",
        "category": "motion",
        "description": "Remotion-style kinetic typography — slamming words, typewriter builds, short punchy frames.",
        "example": "Social opener · trailer text",
        "template": "Slam → type → stack → pulse → cut",
        "story_arc": (
            "1) one-word slam hook → 2) typewriter line that completes the thought → "
            "3) stacked phrase cards (3 max) → 4) pulse a key number → 5) hard cut "
            "CTA. Almost no paragraphs; titles do the work."
        ),
        "tokens": {
            "font": '"Space Grotesk","DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "900", "h2_scale": "1.2", "h2_spacing": "-.045em",
            "card_radius": "10px", "card_border": "0px",
            "card_shadow": "0 24px 60px rgba(0,0,0,.55)",
            "panel_alpha": ".75", "grid_opacity": ".2", "blob_opacity": ".3",
            "uppercase_kicker": "uppercase",
        },
    },
    "dataviz": {
        "key": "dataviz",
        "label": "Data Viz",
        "category": "motion",
        "description": "Animated data scenes — gauges, bars, KPI tiles, Remotion chart energy.",
        "example": "Metrics reel · research results",
        "template": "KPI → bars → gauge → callout → takeaway",
        "story_arc": (
            "1) hero KPI → 2) bar/compare set → 3) gauge or scorecard → 4) annotated "
            "callouts → 5) one-line takeaway. Prefer numbers over prose; caption the "
            "chart, don't restate the paper."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.02", "h2_spacing": "-.02em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 14px 36px rgba(0,0,0,.38)",
            "panel_alpha": "1", "grid_opacity": ".5", "blob_opacity": ".14",
            "uppercase_kicker": "uppercase",
        },
    },
    "device": {
        "key": "device",
        "label": "Device UI",
        "category": "motion",
        "description": "Hyperframes / Remotion product UI — device frames, UI chrome, feature zoom.",
        "example": "App demo · SaaS walkthrough",
        "template": "Device hero → feature zoom → UI stack → flow → CTA",
        "story_arc": (
            "1) device/hero product frame → 2) zoom one UI feature → 3) stacked UI "
            "cards → 4) user flow (steps) → 5) CTA. Prefer panel/hub layouts that "
            "feel like product screenshots with captions."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1", "h2_spacing": "-.02em",
            "card_radius": "18px", "card_border": "1px",
            "card_shadow": "0 22px 55px rgba(0,0,0,.45)",
            "panel_alpha": "1", "grid_opacity": ".3", "blob_opacity": ".2",
            "uppercase_kicker": "none",
        },
    },
    "broadcast": {
        "key": "broadcast",
        "label": "Broadcast",
        "category": "motion",
        "description": "News / lower-third pack — tickers, badges, split desk layouts.",
        "example": "AI news brief · weekly roundup",
        "template": "Lower-third → desk split → ticker → recap",
        "story_arc": (
            "1) lower-third cold open → 2) desk split (headline + bullets) → "
            "3) ticker of facts → 4) one deep beat → 5) recap badges. Keep kickers "
            "and timestamps; feel like a news package."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.08", "h2_spacing": "-.025em",
            "card_radius": "6px", "card_border": "1px",
            "card_shadow": "0 12px 32px rgba(0,0,0,.42)",
            "panel_alpha": "1", "grid_opacity": ".25", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    # ---- Decks · Gamma / PPT ----
    "cards": {
        "key": "cards",
        "label": "Cards",
        "category": "decks",
        "description": "Gamma-style card stack — one idea per card, smart layouts, airy spacing.",
        "example": "AI deck · briefing",
        "template": "Cover card → idea cards → split → summary",
        "story_arc": (
            "1) cover card with title + one line → 2–4) one idea per card (bullets "
            "or hub) → 5) split compare → 6) summary card. Prefer card/panel layouts; "
            "never dense paragraphs — Gamma density."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1.02", "h2_spacing": "-.02em",
            "card_radius": "20px", "card_border": "1px",
            "card_shadow": "0 18px 44px rgba(0,0,0,.32)",
            "panel_alpha": "1", "grid_opacity": ".2", "blob_opacity": ".12",
            "uppercase_kicker": "none",
        },
    },
    "pitch": {
        "key": "pitch",
        "label": "Pitch",
        "category": "ppt",
        "description": "Startup pitch deck — problem, solution, market, traction, ask.",
        "example": "Investor deck · launch pitch",
        "template": "Problem → solution → why now → traction → ask",
        "story_arc": (
            "1) problem hook → 2) solution in one line + 3 pillars → 3) why-now "
            "market beat → 4) traction / proof (bars or scorecard) → 5) ask / CTA. "
            "Investor pacing: short titles, proof over fluff."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.06", "h2_spacing": "-.025em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 16px 40px rgba(0,0,0,.36)",
            "panel_alpha": "1", "grid_opacity": ".35", "blob_opacity": ".16",
            "uppercase_kicker": "uppercase",
        },
    },
    "corporate": {
        "key": "corporate",
        "label": "Corporate",
        "category": "ppt",
        "description": "Classic PPT boardroom — agenda, section dividers, tidy bullets, footer feel.",
        "example": "QBR · executive update",
        "template": "Agenda → section → bullets → chart → next steps",
        "story_arc": (
            "1) title + agenda → 2) section divider → 3) tidy bullet slides → "
            "4) one chart/scorecard → 5) next steps. Conservative layouts; clear "
            "hierarchy; suitable for exec audiences."
        ),
        "tokens": {
            "font": 'Calibri,Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.04", "h2_spacing": "-.01em",
            "card_radius": "8px", "card_border": "1px",
            "card_shadow": "0 8px 24px rgba(0,0,0,.22)",
            "panel_alpha": "1", "grid_opacity": ".15", "blob_opacity": ".06",
            "uppercase_kicker": "uppercase",
        },
    },
    "glass": {
        "key": "glass",
        "label": "Glass",
        "category": "decks",
        "description": "Gamma / web glassmorphism — frosted panels, soft blurs, airy marketing decks.",
        "example": "Product site deck · brand story",
        "template": "Frost hero → glass cards → feature → CTA",
        "story_arc": (
            "1) frosted hero → 2) 3 glass cards → 3) feature focus → 4) soft compare "
            "→ 5) airy CTA. Prefer translucent panels and generous whitespace."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1.04", "h2_spacing": "-.02em",
            "card_radius": "22px", "card_border": "1px",
            "card_shadow": "0 20px 50px rgba(0,0,0,.28)",
            "panel_alpha": ".55", "grid_opacity": ".25", "blob_opacity": ".35",
            "uppercase_kicker": "none",
        },
    },
    "saas": {
        "key": "saas",
        "label": "SaaS",
        "category": "ppt",
        "description": "SaaS marketing deck — hero, features, social proof, pricing energy.",
        "example": "Product launch · feature tour",
        "template": "Hero → features → proof → pricing → CTA",
        "story_arc": (
            "1) product hero → 2) 3 feature cards → 3) social proof / logos feel → "
            "4) comparison or pricing beat → 5) strong CTA. Marketing clarity; "
            "benefit-led titles."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.05", "h2_spacing": "-.025em",
            "card_radius": "16px", "card_border": "1px",
            "card_shadow": "0 18px 48px rgba(0,0,0,.34)",
            "panel_alpha": "1", "grid_opacity": ".3", "blob_opacity": ".18",
            "uppercase_kicker": "none",
        },
    },
    # ---- PPT · Gamma look (presentation-native varieties) ----
    "gamma": {
        "key": "gamma",
        "label": "Gamma",
        "category": "ppt",
        "description": "Gamma.app energy — soft pastel cards, smart auto-layouts, one idea per frame.",
        "example": "AI briefing · client deck",
        "template": "Soft cover → idea cards → split → proof → close",
        "story_arc": (
            "GAMMA DECK: airy, modern presentation feel.\n"
            "1) soft cover with short title → 2–4) one idea per card (never dense "
            "paragraphs) → 5) split or 2×2 matrix → 6) proof / quote → 7) calm close. "
            "Prefer cards/hub/compare; generous whitespace; titles under 8 words."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1.04", "h2_spacing": "-.02em",
            "card_radius": "24px", "card_border": "0px",
            "card_shadow": "0 16px 40px rgba(15,23,42,.14)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".22",
            "uppercase_kicker": "none",
        },
    },
    "keynote": {
        "key": "keynote",
        "label": "Keynote",
        "category": "ppt",
        "description": "Apple Keynote sparse — giant type, few words, cinematic whitespace.",
        "example": "Keynote talk · product unveil",
        "template": "Giant title → one line → image beat → close",
        "story_arc": (
            "KEYNOTE: extreme sparsity. Max 6 words on most slides.\n"
            "1) huge title on open space → 2) one supporting line → 3) single "
            "stat or image beat → 4) three short pillars max → 5) quiet close. "
            "Prefer hook/quote/stat; narration carries the story."
        ),
        "tokens": {
            "font": 'Inter,"SF Pro Display",Segoe UI,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.2", "h2_spacing": "-.04em",
            "card_radius": "12px", "card_border": "0px",
            "card_shadow": "0 10px 30px rgba(0,0,0,.18)",
            "panel_alpha": ".0", "grid_opacity": ".08", "blob_opacity": ".1",
            "uppercase_kicker": "none",
        },
    },
    "slides": {
        "key": "slides",
        "label": "Slides",
        "category": "ppt",
        "description": "Classic PowerPoint — title + bullets, section rails, footer rhythm.",
        "example": "Training deck · status update",
        "template": "Title → section → bullets → chart → next",
        "story_arc": (
            "CLASSIC SLIDES / PPT:\n"
            "1) title slide → 2) agenda / section divider → 3–5) title + 4–6 "
            "bullets → 6) one chart or compare → 7) next steps. Familiar boardroom "
            "pacing; clear hierarchy; no kinetic gimmicks."
        ),
        "tokens": {
            "font": 'Calibri,Arial,Segoe UI,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1", "h2_spacing": "-.01em",
            "card_radius": "4px", "card_border": "1px",
            "card_shadow": "0 4px 14px rgba(0,0,0,.16)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".04",
            "uppercase_kicker": "none",
        },
    },
    "notion": {
        "key": "notion",
        "label": "Notion",
        "category": "ppt",
        "description": "Notion wiki slides — clean pages, callouts, toggles-as-bullets, calm docs feel.",
        "example": "Internal wiki · process brief",
        "template": "Page title → callout → list → database feel → recap",
        "story_arc": (
            "NOTION-STYLE DECK: documentation clarity.\n"
            "1) page title + emoji-light kicker → 2) callout/panel insight → "
            "3) clean bullet list → 4) simple table/matrix → 5) checklist recap. "
            "Prefer panel/bullets/matrix; muted chrome; readable over flashy."
        ),
        "tokens": {
            "font": 'Inter,"Segoe UI",system-ui,sans-serif',
            "h2_weight": "650", "h2_scale": "1.02", "h2_spacing": "-.015em",
            "card_radius": "10px", "card_border": "1px",
            "card_shadow": "0 6px 18px rgba(0,0,0,.1)",
            "panel_alpha": "1", "grid_opacity": ".18", "blob_opacity": ".08",
            "uppercase_kicker": "none",
        },
    },
    # ---- Modern · PPT (GraphicMama / Slidesgo-style layout varieties) ----
    "geo_navy": {
        "key": "geo_navy",
        "label": "Geo Navy",
        "category": "modern_ppt",
        "description": "Modern geometric PPT — navy + cyan corner triangles, bold sans titles, airy boardroom frames.",
        "example": "Architecture brief · system overview",
        "template": "Title frame → agenda → 2×2 cards → SWOT → close",
        "motif": "corner_triangles",
        "font_label": "Montserrat",
        "story_arc": (
            "GEOMETRIC NAVY PPT: clean corporate modern.\n"
            "1) framed title with corner accents → 2) numbered agenda → 3) 2×2 "
            "icon cards → 4) vertical process or compare → 5) SWOT / matrix → "
            "6) closing takeaway. Prefer hub/compare/matrix; generous whitespace."
        ),
        "tokens": {
            "font": '"Montserrat",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Montserrat",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.06", "h2_spacing": "-.03em",
            "card_radius": "14px", "card_border": "1px",
            "card_shadow": "0 14px 36px rgba(15,23,42,.18)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    "coral_split": {
        "key": "coral_split",
        "label": "Coral Split",
        "category": "modern_ppt",
        "description": "Coral / orange gradient splits — diagonal energy, photo+copy halves, marketing CTA decks.",
        "example": "Creative pitch · brand story",
        "template": "Split hero → donut stats → bar compare → process → mosaic",
        "motif": "diagonal_split",
        "font_label": "Poppins",
        "story_arc": (
            "CORAL SPLIT PPT: bold marketing geometry.\n"
            "1) split hero (title vs color block) → 2) big stat / donut → "
            "3) horizontal bar compare → 4) 4-step process → 5) mosaic / gallery "
            "→ 6) CTA close. Prefer compare/stat/steps; punchy short titles."
        ),
        "tokens": {
            "font": '"Poppins",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Poppins",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.08", "h2_spacing": "-.025em",
            "card_radius": "18px", "card_border": "0px",
            "card_shadow": "0 18px 44px rgba(234,88,12,.22)",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".28",
            "uppercase_kicker": "none",
        },
    },
    "blush_soft": {
        "key": "blush_soft",
        "label": "Blush Soft",
        "category": "modern_ppt",
        "description": "Dusty-rose soft PPT — thin-line icons, blush bands, calm mission/agenda grids.",
        "example": "Brand story · wellness · team intro",
        "template": "Mission list → feature grid → pie → agenda numbers → photo split",
        "motif": "blush_bands",
        "font_label": "Outfit",
        "story_arc": (
            "BLUSH SOFT PPT: airy minimalist branding.\n"
            "1) soft title + short mission → 2) alternating list bands → "
            "3) 2×2 feature grid → 4) donut / chart → 5) numbered agenda → "
            "6) photo+copy close. Prefer bullets/hub/matrix; quiet motion."
        ),
        "tokens": {
            "font": '"Outfit",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Outfit",Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.04", "h2_spacing": "-.02em",
            "card_radius": "16px", "card_border": "0px",
            "card_shadow": "0 12px 32px rgba(244,114,182,.14)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".16",
            "uppercase_kicker": "none",
        },
    },
    "mosaic": {
        "key": "mosaic",
        "label": "Mosaic",
        "category": "modern_ppt",
        "description": "Gallery mosaic PPT — mixed image/color tiles, media grids, contact columns.",
        "example": "Portfolio · case study · product collage",
        "template": "Mood board → client hex → process pills → map → contact",
        "motif": "tile_mosaic",
        "font_label": "Manrope",
        "story_arc": (
            "MOSAIC GALLERY PPT: visual storytelling.\n"
            "1) mood / title collage → 2) logo / client grid → 3) process pills → "
            "4) map or regional callouts → 5) media grid → 6) contact columns. "
            "Prefer hub/matrix/steps; short labels on tiles."
        ),
        "tokens": {
            "font": '"Manrope",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Manrope",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.02", "h2_spacing": "-.02em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 10px 28px rgba(0,0,0,.2)",
            "panel_alpha": "1", "grid_opacity": ".2", "blob_opacity": ".12",
            "uppercase_kicker": "uppercase",
        },
    },
    "process": {
        "key": "process",
        "label": "Process",
        "category": "modern_ppt",
        "description": "Process / timeline PPT — overlapping circles, pill steps, START→END flows.",
        "example": "Roadmap · onboarding · methodology",
        "template": "Title → overlapping steps → horizontal pills → tree → close",
        "motif": "process_pills",
        "font_label": "DM Sans",
        "story_arc": (
            "PROCESS PPT: methodology clarity.\n"
            "1) title → 2) 4 overlapping numbered circles → 3) horizontal pill "
            "timeline → 4) tree / relationship → 5) checklist recap. "
            "Prefer flow/steps/hub; numbered beats."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1.03", "h2_spacing": "-.02em",
            "card_radius": "999px", "card_border": "1px",
            "card_shadow": "0 12px 30px rgba(37,99,235,.16)",
            "panel_alpha": "1", "grid_opacity": ".14", "blob_opacity": ".14",
            "uppercase_kicker": "uppercase",
        },
    },
    "agenda": {
        "key": "agenda",
        "label": "Agenda Grid",
        "category": "modern_ppt",
        "description": "Numbered agenda PPT — giant 01–09 numerals, pink accent rails, map callouts.",
        "example": "Workshop agenda · conference track",
        "template": "Cover → 3×3 agenda → circular steps → map → contact",
        "motif": "giant_numbers",
        "font_label": "Space Grotesk",
        "story_arc": (
            "AGENDA GRID PPT: workshop / conference pacing.\n"
            "1) bold cover → 2) giant numbered agenda grid → 3) circular 3-step "
            "focus → 4) map / regional → 5) contact / next. Prefer matrix/steps/"
            "stat; big numerals as design."
        ),
        "tokens": {
            "font": '"Space Grotesk","DM Sans",Inter,system-ui,sans-serif',
            "h2_font": '"Space Grotesk",Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.1", "h2_spacing": "-.035em",
            "card_radius": "16px", "card_border": "1px",
            "card_shadow": "0 14px 36px rgba(236,72,153,.14)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".12",
            "uppercase_kicker": "none",
        },
    },
    "rainbow_bar": {
        "key": "rainbow_bar",
        "label": "Rainbow Bar",
        "category": "modern_ppt",
        "description": "Bright multipurpose PPT — multicolor hairline bars, overlapping circles, cloud/category clusters.",
        "example": "Startup intro · colorful pitch",
        "template": "Title + bar → tree orbit → circle steps → media grid → flow",
        "motif": "rainbow_divider",
        "font_label": "Nunito",
        "story_arc": (
            "RAINBOW BAR PPT: bright modern multipurpose.\n"
            "1) centered title with multicolor hairline → 2) tree / orbit "
            "relationships → 3) overlapping numbered circles → 4) photo+color "
            "grid → 5) horizontal process pills → 6) cloud/category close. "
            "Prefer hub/flow/matrix; playful but clean."
        ),
        "tokens": {
            "font": '"Nunito",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Nunito",Inter,system-ui,sans-serif',
            "h2_weight": "800", "h2_scale": "1.05", "h2_spacing": "-.02em",
            "card_radius": "14px", "card_border": "0px",
            "card_shadow": "0 12px 30px rgba(66,133,244,.16)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".2",
            "uppercase_kicker": "uppercase",
        },
    },
    "circle_stack": {
        "key": "circle_stack",
        "label": "Circle Stack",
        "category": "modern_ppt",
        "description": "Overlapping translucent circles — process sequences, vertical pill columns, pink accent focus.",
        "example": "Method steps · comparison columns",
        "template": "Cover → 3 circles → overlapping 4 → pill columns → map",
        "motif": "overlap_circles",
        "font_label": "Rubik",
        "story_arc": (
            "CIRCLE STACK PPT: geometric process focus.\n"
            "1) airy title → 2) three horizontal circles (center highlighted) → "
            "3) overlapping translucent sequence → 4) vertical pill columns → "
            "5) map / regional → 6) contact. Prefer flow/compare/stat."
        ),
        "tokens": {
            "font": '"Rubik",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Rubik",Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.04", "h2_spacing": "-.02em",
            "card_radius": "999px", "card_border": "1px",
            "card_shadow": "0 14px 34px rgba(236,72,153,.18)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".14",
            "uppercase_kicker": "none",
        },
    },
    "hex_grid": {
        "key": "hex_grid",
        "label": "Hex Grid",
        "category": "modern_ppt",
        "description": "Hexagon client/logo grids — thin-line icons in geometric cells, coral accent highlights.",
        "example": "Partners · ecosystem · logo wall",
        "template": "Title → hex logo wall → content+photo → process → contact",
        "motif": "hex_cells",
        "font_label": "Work Sans",
        "story_arc": (
            "HEX GRID PPT: partner / ecosystem storytelling.\n"
            "1) title with hex motif → 2) hexagonal logo / icon wall → "
            "3) content + photo split → 4) process rail → 5) contact columns. "
            "Prefer hub/matrix; short labels inside cells."
        ),
        "tokens": {
            "font": '"Work Sans",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Work Sans",Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.03", "h2_spacing": "-.02em",
            "card_radius": "10px", "card_border": "1px",
            "card_shadow": "0 10px 26px rgba(244,63,94,.14)",
            "panel_alpha": "1", "grid_opacity": ".16", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    "wave_soft": {
        "key": "wave_soft",
        "label": "Wave Soft",
        "category": "modern_ppt",
        "description": "Soft wavy corporate PPT — rounded rectangles, gentle bands, fresh flat marketing layouts.",
        "example": "Team values · portfolio · social proof",
        "template": "Wavy title → values → portfolio → growth arrows → contact",
        "motif": "soft_waves",
        "font_label": "Figtree",
        "story_arc": (
            "WAVE SOFT PPT: sleek flat corporate.\n"
            "1) soft title with wave band → 2) core values cards → "
            "3) portfolio / image+text → 4) growth arrows → 5) social proof → "
            "6) contact. Prefer hub/bullets/stat; rounded everything."
        ),
        "tokens": {
            "font": '"Figtree",Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": '"Figtree",Inter,system-ui,sans-serif',
            "h2_weight": "750", "h2_scale": "1.05", "h2_spacing": "-.025em",
            "card_radius": "20px", "card_border": "0px",
            "card_shadow": "0 16px 40px rgba(14,165,233,.14)",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".22",
            "uppercase_kicker": "none",
        },
    },

    # ---- Hyper · design (HyperFrames visual identities) ----
    "swiss_pulse": {
        "key": "swiss_pulse",
        "label": "Swiss Pulse",
        "category": "hyper",
        "description": "HyperFrames Swiss Pulse — clinical 12-col grid, giant metrics, Helvetica precision.",
        "example": "SaaS metrics · API briefing",
        "template": "Registration marks → giant stat → grid compare → close",
        "motif": "swiss_grid",
        "font_label": "Helvetica Neue",
        "story_arc": (
            "SWISS PULSE: grid-locked clinical deck.\n"
            "1) sparse title with registration marks → 2) giant animated stat → "
            "3) 3-up metric cards → 4) matrix/compare → 5) hard-cut takeaway. "
            "Prefer stat/compare/matrix; snap geometry, no fluff."
        ),
        "tokens": {
            "font": '"Helvetica Neue",Inter,Arial,sans-serif',
            "h2_font": '"Helvetica Neue",Inter,Arial,sans-serif',
            "h2_weight": "700", "h2_scale": "1.12", "h2_spacing": "-.04em",
            "card_radius": "2px", "card_border": "1px",
            "card_shadow": "none",
            "panel_alpha": "1", "grid_opacity": ".55", "blob_opacity": ".04",
            "uppercase_kicker": "uppercase",
        },
    },
    "velvet_std": {
        "key": "velvet_std",
        "label": "Velvet Standard",
        "category": "hyper",
        "description": "HyperFrames Velvet — premium wide-tracked caps, hairline rules, luxury calm.",
        "example": "Enterprise keynote · investor close",
        "template": "Wide title → hairline → sparse proof → glide CTA",
        "motif": "velvet_rules",
        "font_label": "Inter",
        "story_arc": (
            "VELVET STANDARD: premium Vignelli calm.\n"
            "1) centered wide-tracked title → 2) one proof quote → 3) sparse "
            "bullets with huge margins → 4) symmetrical compare → 6) quiet CTA. "
            "Prefer quote/minimal bullets; long holds, glide not snap."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Inter,system-ui,sans-serif',
            "h2_weight": "300", "h2_scale": "1.08", "h2_spacing": ".12em",
            "card_radius": "2px", "card_border": "1px",
            "card_shadow": "none",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".06",
            "uppercase_kicker": "uppercase",
        },
    },
    "deconstructed": {
        "key": "deconstructed",
        "label": "Deconstructed",
        "category": "hyper",
        "description": "HyperFrames Deconstructed — industrial angles, scan lines, Space Grotesk slam.",
        "example": "Security launch · tech teardown",
        "template": "Offset title → glitch chips → angled compare → snap close",
        "motif": "deconstruct",
        "font_label": "Space Grotesk",
        "story_arc": (
            "DECONSTRUCTED: industrial Brody energy.\n"
            "1) angled title escaping frame → 2) raw chips/labels → 3) "
            "overlapping cards → 4) sharp compare → 5) slam takeaway. "
            "Prefer teardown/compare; intentional irregularity."
        ),
        "tokens": {
            "font": '"Space Grotesk","Space Mono",Inter,monospace',
            "h2_font": '"Space Grotesk",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.14", "h2_spacing": "-.03em",
            "card_radius": "0px", "card_border": "2px",
            "card_shadow": "6px 6px 0 rgba(212,80,30,.35)",
            "panel_alpha": "1", "grid_opacity": ".35", "blob_opacity": ".18",
            "uppercase_kicker": "uppercase",
        },
    },
    "maximalist": {
        "key": "maximalist",
        "label": "Maximalist Type",
        "category": "hyper",
        "description": "HyperFrames Maximalist — Anton megatype fills the frame, color-block energy.",
        "example": "Launch hype · milestone reveal",
        "template": "Giant word → color block → 2-beat proof → hard stop",
        "motif": "type_layers",
        "font_label": "Anton",
        "story_arc": (
            "MAXIMALIST TYPE: text IS the visual.\n"
            "1) oversized claim fills frame → 2) stacked type layers → "
            "3) one proof number → 4) rapid close. Prefer hook/stat; 2–3s beats."
        ),
        "tokens": {
            "font": '"Anton","Space Grotesk",Impact,sans-serif',
            "h2_font": '"Anton",Impact,sans-serif',
            "h2_weight": "400", "h2_scale": "1.35", "h2_spacing": "-.02em",
            "card_radius": "0px", "card_border": "0px",
            "card_shadow": "none",
            "panel_alpha": "1", "grid_opacity": ".05", "blob_opacity": ".4",
            "uppercase_kicker": "uppercase",
        },
    },
    "data_drift": {
        "key": "data_drift",
        "label": "Data Drift",
        "category": "hyper",
        "description": "HyperFrames Data Drift — weightless Inter, particle glow, AI/ML immersion.",
        "example": "AI platform · research teaser",
        "template": "Thin title → morph hub → path flow → particle close",
        "motif": "particle_field",
        "font_label": "Inter",
        "story_arc": (
            "DATA DRIFT: futuristic Anadol mood.\n"
            "1) thin floating title → 2) hub/node graph → 3) flow paths → "
            "4) soft stats → 5) ambient close. Prefer hub/flow/stat; organic motion."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Inter,system-ui,sans-serif',
            "h2_weight": "200", "h2_scale": "1.05", "h2_spacing": ".05em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 20px 60px rgba(124,58,237,.25)",
            "panel_alpha": ".85", "grid_opacity": ".2", "blob_opacity": ".45",
            "uppercase_kicker": "none",
        },
    },
    "soft_signal": {
        "key": "soft_signal",
        "label": "Soft Signal",
        "category": "hyper",
        "description": "HyperFrames Soft Signal — Playfair italic warmth, intimate wellness frames.",
        "example": "Brand story · wellness · lifestyle",
        "template": "Italic title → soft band list → photo split → warm close",
        "motif": "warm_grain",
        "font_label": "Playfair Display",
        "story_arc": (
            "SOFT SIGNAL: intimate Sagmeister warmth.\n"
            "1) italic serif title → 2) soft list bands → 3) photo+copy → "
            "4) quiet quote → 5) gentle CTA. Prefer bullets/quote; slow drifts."
        ),
        "tokens": {
            "font": '"Playfair Display",Georgia,serif',
            "h2_font": '"Playfair Display",Georgia,serif',
            "h2_weight": "400", "h2_scale": "1.1", "h2_spacing": "-.01em",
            "card_radius": "16px", "card_border": "0px",
            "card_shadow": "0 12px 36px rgba(197,163,163,.2)",
            "panel_alpha": "1", "grid_opacity": ".06", "blob_opacity": ".22",
            "uppercase_kicker": "none",
        },
    },
    "folk_freq": {
        "key": "folk_freq",
        "label": "Folk Frequency",
        "category": "hyper",
        "description": "HyperFrames Folk Frequency — Fredoka joy, pattern tiles, festive consumer energy.",
        "example": "Consumer app · community launch",
        "template": "Bold cover → pattern grid → bounce steps → confetti close",
        "motif": "folk_tiles",
        "font_label": "Fredoka",
        "story_arc": (
            "FOLK FREQUENCY: vivid Terrazas rhythm.\n"
            "1) rounded bold title → 2) patterned hub → 3) bounce process → "
            "4) colorful compare → 5) celebratory CTA. Prefer hub/steps; playful."
        ),
        "tokens": {
            "font": '"Fredoka",Nunito,system-ui,sans-serif',
            "h2_font": '"Fredoka",Nunito,sans-serif',
            "h2_weight": "500", "h2_scale": "1.12", "h2_spacing": "-.01em",
            "card_radius": "20px", "card_border": "0px",
            "card_shadow": "0 10px 0 rgba(255,20,147,.2)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".35",
            "uppercase_kicker": "none",
        },
    },
    "shadow_cut": {
        "key": "shadow_cut",
        "label": "Shadow Cut",
        "category": "hyper",
        "description": "HyperFrames Shadow Cut — noir Oswald titles, vignette, blood accent drama.",
        "example": "Security exposé · dramatic reveal",
        "template": "Dark cover → creeping reveal → stark proof → cut to black",
        "motif": "noir_cut",
        "font_label": "Oswald",
        "story_arc": (
            "SHADOW CUT: Hillmann noir drama.\n"
            "1) deep black title card → 2) slow reveal claim → 3) stark evidence → "
            "4) sharp compare → 5) cut-to-black close. Prefer cinematic/quote."
        ),
        "tokens": {
            "font": '"Oswald",Inter,system-ui,sans-serif',
            "h2_font": '"Oswald",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.18", "h2_spacing": ".04em",
            "card_radius": "2px", "card_border": "1px",
            "card_shadow": "0 24px 48px rgba(0,0,0,.55)",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".08",
            "uppercase_kicker": "uppercase",
        },
    },
    # ---- Motion · Remotion ----
    "kinetic_center": {
        "key": "kinetic_center",
        "label": "Kinetic Center",
        "category": "motion",
        "description": "Remotion-style center-build type — words push in until the phrase locks.",
        "example": "Short claim · trailer beat",
        "template": "Word build → lock center → emphasis slam → hold",
        "motif": "center_build",
        "font_label": "Space Grotesk",
        "story_arc": (
            "KINETIC CENTER: Remotion center-build.\n"
            "1) empty center → 2) words push in sequence → 3) locked phrase → "
            "4) one support line → 5) hard cut. Prefer hook/quote; short titles."
        ),
        "tokens": {
            "font": '"Space Grotesk",Inter,system-ui,sans-serif',
            "h2_font": '"Space Grotesk",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.2", "h2_spacing": "-.04em",
            "card_radius": "8px", "card_border": "0px",
            "card_shadow": "0 12px 40px rgba(232,121,249,.25)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".3",
            "uppercase_kicker": "none",
        },
    },
    "lower_third": {
        "key": "lower_third",
        "label": "Lower Third",
        "category": "motion",
        "description": "Remotion / broadcast lower-third plates — name plate, ticker, news energy.",
        "example": "Talking head · news brief",
        "template": "Plate in → claim → ticker chips → plate out",
        "motif": "lower_third",
        "font_label": "Oswald",
        "story_arc": (
            "LOWER THIRD: broadcast Remotion plate.\n"
            "1) lower-third plate → 2) short claim → 3) chip ticker → "
            "4) one proof → 5) plate exit. Prefer broadcast/hook; tight copy."
        ),
        "tokens": {
            "font": '"Oswald",Inter,system-ui,sans-serif',
            "h2_font": '"Oswald",Inter,sans-serif',
            "h2_weight": "600", "h2_scale": ".95", "h2_spacing": ".02em",
            "card_radius": "4px", "card_border": "0px",
            "card_shadow": "0 8px 24px rgba(0,0,0,.35)",
            "panel_alpha": "1", "grid_opacity": ".15", "blob_opacity": ".12",
            "uppercase_kicker": "uppercase",
        },
    },
    "promo_sprint": {
        "key": "promo_sprint",
        "label": "Promo Sprint",
        "category": "motion",
        "description": "Remotion product promo — feature sprint, screenshot beats, CTA sting.",
        "example": "Product launch · feature tour",
        "template": "Logo sting → features → proof → CTA",
        "motif": "promo_sprint",
        "font_label": "Poppins",
        "story_arc": (
            "PROMO SPRINT: Remotion product promo.\n"
            "1) logo/title sting → 2) 3 feature cards → 3) proof/stat → "
            "4) CTA pill. Prefer device/stat/cards; punchy short lines."
        ),
        "tokens": {
            "font": '"Poppins",Inter,system-ui,sans-serif',
            "h2_font": '"Poppins",Inter,sans-serif',
            "h2_weight": "800", "h2_scale": "1.06", "h2_spacing": "-.03em",
            "card_radius": "14px", "card_border": "0px",
            "card_shadow": "0 16px 40px rgba(99,102,241,.28)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".28",
            "uppercase_kicker": "none",
        },
    },
    # ---- Content · layouts (logical deck varieties) ----
    "bento": {
        "key": "bento",
        "label": "Bento Grid",
        "category": "content",
        "description": "Apple-style bento mosaic — mixed tile sizes for features and proof.",
        "example": "Feature overview · product map",
        "template": "Hero tile → 2×2 mix → wide proof → CTA tile",
        "motif": "bento",
        "font_label": "Manrope",
        "story_arc": (
            "BENTO GRID: modular content layout.\n"
            "1) large hero tile → 2) mixed feature tiles → 3) wide proof → "
            "4) CTA tile. Prefer hub/matrix/cards; short labels."
        ),
        "tokens": {
            "font": '"Manrope",Inter,system-ui,sans-serif',
            "h2_font": '"Manrope",Inter,sans-serif',
            "h2_weight": "800", "h2_scale": "1.04", "h2_spacing": "-.03em",
            "card_radius": "18px", "card_border": "0px",
            "card_shadow": "0 12px 32px rgba(0,0,0,.18)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".12",
            "uppercase_kicker": "none",
        },
    },
    "big_stat": {
        "key": "big_stat",
        "label": "Big Stat",
        "category": "content",
        "description": "One giant KPI per beat — Beautiful.ai-style smart stat slides.",
        "example": "Results deck · benchmark",
        "template": "Giant number → label → caveat → next KPI",
        "motif": "big_stat",
        "font_label": "Montserrat",
        "story_arc": (
            "BIG STAT: one KPI owns the frame.\n"
            "1) huge number → 2) short label → 3) one caveat → 4) next KPI. "
            "Prefer stat/stat; never crowd with bullets."
        ),
        "tokens": {
            "font": '"Montserrat",Inter,system-ui,sans-serif',
            "h2_font": '"Montserrat",Inter,sans-serif',
            "h2_weight": "800", "h2_scale": "1.4", "h2_spacing": "-.05em",
            "card_radius": "12px", "card_border": "0px",
            "card_shadow": "0 10px 28px rgba(15,23,42,.15)",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    "quote_pull": {
        "key": "quote_pull",
        "label": "Quote Pull",
        "category": "content",
        "description": "Magazine pull-quote layout — oversized mark, attribution, airy margins.",
        "example": "Testimony · thesis beat",
        "template": "Mark → quote → attribution → context",
        "motif": "pull_quote",
        "font_label": "Playfair Display",
        "story_arc": (
            "QUOTE PULL: editorial pull-quote.\n"
            "1) oversized quote → 2) attribution → 3) one context line → "
            "4) soft close. Prefer quote/editorial; sparse."
        ),
        "tokens": {
            "font": '"Playfair Display",Georgia,serif',
            "h2_font": '"Playfair Display",Georgia,serif',
            "h2_weight": "500", "h2_scale": "1.15", "h2_spacing": "-.015em",
            "card_radius": "8px", "card_border": "0px",
            "card_shadow": "none",
            "panel_alpha": "1", "grid_opacity": ".05", "blob_opacity": ".08",
            "uppercase_kicker": "none",
        },
    },
    "timeline_rail": {
        "key": "timeline_rail",
        "label": "Timeline Rail",
        "category": "content",
        "description": "Horizontal/vertical timeline rail — roadmap, history, release trains.",
        "example": "Roadmap · release plan",
        "template": "Rail → milestones → focus beat → next",
        "motif": "timeline_rail",
        "font_label": "DM Sans",
        "story_arc": (
            "TIMELINE RAIL: roadmap clarity.\n"
            "1) rail overview → 2) milestone stops → 3) focus beat → "
            "4) next stop CTA. Prefer flow/steps; numbered beats."
        ),
        "tokens": {
            "font": '"DM Sans",Inter,system-ui,sans-serif',
            "h2_font": '"DM Sans",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.05", "h2_spacing": "-.02em",
            "card_radius": "999px", "card_border": "1px",
            "card_shadow": "0 10px 28px rgba(37,99,235,.16)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".12",
            "uppercase_kicker": "uppercase",
        },
    },
    "split_media": {
        "key": "split_media",
        "label": "Split Media",
        "category": "content",
        "description": "50/50 media+copy splits — Pitch/Beautiful.ai photo-left content-right.",
        "example": "Case study · product story",
        "template": "Media | copy → invert → proof → CTA",
        "motif": "split_media",
        "font_label": "Outfit",
        "story_arc": (
            "SPLIT MEDIA: media+copy halves.\n"
            "1) photo|title → 2) invert sides → 3) proof bullets → 4) CTA. "
            "Prefer compare/hub; balanced halves."
        ),
        "tokens": {
            "font": '"Outfit",Inter,system-ui,sans-serif',
            "h2_font": '"Outfit",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.06", "h2_spacing": "-.025em",
            "card_radius": "14px", "card_border": "0px",
            "card_shadow": "0 14px 36px rgba(0,0,0,.16)",
            "panel_alpha": "1", "grid_opacity": ".1", "blob_opacity": ".14",
            "uppercase_kicker": "none",
        },
    },
    "caption_pop": {
        "key": "caption_pop",
        "label": "Caption Pop",
        "category": "motion",
        "description": "Remotion caption themes — karaoke highlight, word pop, short-form retention.",
        "example": "Shorts · Reels · TikTok",
        "template": "Hook word → karaoke line → punch → CTA",
        "motif": "caption_pop",
        "font_label": "Poppins",
        "story_arc": (
            "CAPTION POP: Remotion caption energy.\n"
            "1) giant hook word → 2) karaoke highlight line → 3) punch phrase → "
            "4) CTA chip. Prefer hook/quote/stat; 2–5 words on screen."
        ),
        "tokens": {
            "font": '"Poppins",Inter,system-ui,sans-serif',
            "h2_font": '"Poppins",Inter,sans-serif',
            "h2_weight": "800", "h2_scale": "1.18", "h2_spacing": "-.03em",
            "card_radius": "12px", "card_border": "0px",
            "card_shadow": "0 12px 28px rgba(234,179,8,.22)",
            "panel_alpha": ".92", "grid_opacity": ".06", "blob_opacity": ".16",
            "uppercase_kicker": "none",
        },
    },
    "chart_race": {
        "key": "chart_race",
        "label": "Chart Race",
        "category": "motion",
        "description": "Remotion bar/line race — competing series, animated ranks, data storytelling.",
        "example": "Benchmarks · market share",
        "template": "Title → race bars → leader callout → takeaway",
        "motif": "chart_race",
        "font_label": "IBM Plex Mono",
        "story_arc": (
            "CHART RACE: Remotion data motion.\n"
            "1) metric title → 2) racing bars/series → 3) leader callout → "
            "4) one-line takeaway. Prefer bars/stat/compare; numbers dominate."
        ),
        "tokens": {
            "font": '"IBM Plex Mono",Inter,monospace',
            "h2_font": '"IBM Plex Mono",Inter,monospace',
            "h2_weight": "600", "h2_scale": "1.04", "h2_spacing": "-.01em",
            "card_radius": "6px", "card_border": "1px",
            "card_shadow": "0 8px 22px rgba(16,185,129,.18)",
            "panel_alpha": "1", "grid_opacity": ".28", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    "logo_intro": {
        "key": "logo_intro",
        "label": "Logo Intro",
        "category": "motion",
        "description": "Remotion logo intro — brand mark burst, particle settle, title lockup.",
        "example": "Cold open · brand sting",
        "template": "Mark burst → title lock → promise → cut",
        "motif": "logo_intro",
        "font_label": "Montserrat",
        "story_arc": (
            "LOGO INTRO: Remotion brand sting.\n"
            "1) mark/particle burst → 2) title lockup → 3) one-line promise → "
            "4) hard cut into content. Prefer hook/stat; short hold."
        ),
        "tokens": {
            "font": '"Montserrat",Inter,system-ui,sans-serif',
            "h2_font": '"Montserrat",Inter,sans-serif',
            "h2_weight": "800", "h2_scale": "1.1", "h2_spacing": "-.03em",
            "card_radius": "16px", "card_border": "0px",
            "card_shadow": "0 18px 40px rgba(99,102,241,.22)",
            "panel_alpha": ".9", "grid_opacity": ".1", "blob_opacity": ".28",
            "uppercase_kicker": "uppercase",
        },
    },
    "proof_duo": {
        "key": "proof_duo",
        "label": "Proof Duo",
        "category": "content",
        "description": "Two-column proof — claim vs evidence, before/after, Myth vs Fact.",
        "example": "Case study · myth bust",
        "template": "Claim | evidence → invert → verdict",
        "motif": "proof_duo",
        "font_label": "Manrope",
        "story_arc": (
            "PROOF DUO: logical two-column groups.\n"
            "1) claim|evidence → 2) before|after → 3) verdict bar → 4) CTA. "
            "Prefer compare/transform; balanced columns."
        ),
        "tokens": {
            "font": '"Manrope",Inter,system-ui,sans-serif',
            "h2_font": '"Manrope",Inter,sans-serif',
            "h2_weight": "700", "h2_scale": "1.05", "h2_spacing": "-.02em",
            "card_radius": "12px", "card_border": "1px",
            "card_shadow": "0 12px 30px rgba(37,99,235,.14)",
            "panel_alpha": "1", "grid_opacity": ".12", "blob_opacity": ".12",
            "uppercase_kicker": "uppercase",
        },
    },
    "kpi_strip": {
        "key": "kpi_strip",
        "label": "KPI Strip",
        "category": "content",
        "description": "Horizontal KPI strip — 3–4 metrics in one row, executive dashboard beat.",
        "example": "Board update · OKRs",
        "template": "Strip → zoom one KPI → context → action",
        "motif": "kpi_strip",
        "font_label": "Inter",
        "story_arc": (
            "KPI STRIP: executive metric row.\n"
            "1) 3–4 KPI strip → 2) zoom one number → 3) context bullets → "
            "4) action. Prefer bars/stat/matrix; scannable labels."
        ),
        "tokens": {
            "font": 'Inter,Segoe UI,system-ui,sans-serif',
            "h2_font": 'Inter,system-ui,sans-serif',
            "h2_weight": "700", "h2_scale": "1.08", "h2_spacing": "-.03em",
            "card_radius": "10px", "card_border": "1px",
            "card_shadow": "0 10px 26px rgba(14,165,233,.14)",
            "panel_alpha": "1", "grid_opacity": ".18", "blob_opacity": ".1",
            "uppercase_kicker": "uppercase",
        },
    },
    "stack_cards": {
        "key": "stack_cards",
        "label": "Stack Cards",
        "category": "content",
        "description": "Layered card stack — Notion/Linear depth, peeking edges, sequential reveal.",
        "example": "Feature stack · roadmap layers",
        "template": "Stack peek → fan out → focus card → close",
        "motif": "stack_cards",
        "font_label": "Figtree",
        "story_arc": (
            "STACK CARDS: layered card groups.\n"
            "1) stacked peek → 2) fan to 3 cards → 3) focus one → 4) close. "
            "Prefer hub/cards/steps; depth via offset shadows."
        ),
        "tokens": {
            "font": '"Figtree",Inter,system-ui,sans-serif',
            "h2_font": '"Figtree",Inter,sans-serif',
            "h2_weight": "750", "h2_scale": "1.05", "h2_spacing": "-.02em",
            "card_radius": "16px", "card_border": "1px",
            "card_shadow": "0 18px 40px rgba(15,23,42,.16)",
            "panel_alpha": "1", "grid_opacity": ".08", "blob_opacity": ".14",
            "uppercase_kicker": "none",
        },
    },

}


from .visual_layouts import (
    CURATED_THEME_KEYS,
    EXISTING_LAYOUT_MODES,
    EXTRA_THEME_HINTS,
    EXTRA_VIDEO_STYLES,
    FEATURED_LAYOUT_KEYS,
    THEME_ALIASES,
    alias_theme,
    assign_group_fonts,
    chrome_for,
    generated_compose_css,
    remap_category,
    uniquify_layout_modes,
)

CORE_STYLE_KEYS = frozenset(VIDEO_STYLES.keys())
for _ek, _ev in EXTRA_VIDEO_STYLES.items():
    if _ek not in VIDEO_STYLES:
        VIDEO_STYLES[_ek] = _ev


def _font_label_from_tokens(tokens: dict) -> str:
    """Human label for the primary face in a style's CSS font stack."""
    raw = str((tokens or {}).get("h2_font") or (tokens or {}).get("font") or "")
    # First quoted family or first bare token before a comma.
    m = re.search(r'"([^"]+)"', raw)
    if m:
        return m.group(1)
    first = raw.split(",")[0].strip().strip("'")
    return first or "Inter"


_chrome_used: set[tuple] = set()
for _sk, _sv in VIDEO_STYLES.items():
    if "category" not in _sv:
        _sv["category"] = _STYLE_CATEGORY_DEFAULTS.get(_sk, "teach")
    _sv["category"] = remap_category(_sk, _sv["category"])
    tok = _sv.get("tokens") or {}
    if not _sv.get("font_label"):
        _sv["font_label"] = _font_label_from_tokens(tok)
    if not _sv.get("motif"):
        _sv["motif"] = _sk
    if not _sv.get("layout_mode"):
        _sv["layout_mode"] = (
            EXISTING_LAYOUT_MODES.get(_sk)
            or tok.get("layout_mode")
            or "stack"
        )
    tok.setdefault("layout_mode", _sv["layout_mode"])
    tok.update(chrome_for(_sk, _chrome_used))
    tok.setdefault("motif", _sv["motif"])
    _sv["tokens"] = tok

# Each layout gets a globally unique HTML compose. Named frames keep their
# geometry; clones get a unique compose id instead of sharing audiogram/stack.
PICKER_HIDDEN: set[str] = set()


def _name_flagships() -> None:
    """Each template's flagship style carries the template's own name, so the
    twelve headline picks read Whiteboard, Notebook, Chalkboard, Editorial, Magazine,
    Broadcast, Glass, Bento, Poster, Pop, Cinema, Terminal everywhere (picker, job options, hints)."""
    from .pipeline.edu_theme import FAMILY_INFO

    for info in FAMILY_INFO.values():
        spec = VIDEO_STYLES.get(info["flagship"])
        if spec:
            spec["label"] = info["label"]


_name_flagships()
STYLE_ALIASES: dict[str, str] = {}
uniquify_layout_modes(VIDEO_STYLES)
assign_group_fonts(VIDEO_STYLES)
UNIQUE_COMPOSE_CSS = generated_compose_css(VIDEO_STYLES)


DEFAULT_VIDEO_STYLE = "hybrid"
AUTO_VIDEO_STYLE = "auto"
AUTO_VIDEO_THEME = "auto"

# Preferred styles per document class (highest first). Strong prior before
# text / format signals adjust the score.
_DOC_TYPE_STYLE_PRIORS: dict[str, tuple[str, ...]] = {
    "research paper": ("documentary", "editorial", "minimal", "explainer", "teardown"),
    "book": ("editorial", "documentary", "minimal", "explainer"),
    "tutorial": ("tutorial", "whiteboard", "explainer", "modern"),
    "slide deck": ("gamma", "swiss_pulse", "bento", "geo_navy", "velvet_std", "keynote", "coral_split", "pitch", "bento"),
    "manual": ("tutorial", "minimal", "modern", "whiteboard"),
    "article": ("editorial", "explainer", "modern", "documentary"),
    "plan": ("corporate", "modern", "whiteboard", "pitch"),
    "notes": ("whiteboard", "minimal", "tutorial", "cards"),
    "other": ("hybrid", "hybrid_kinetic", "explainer", "cards", "modern"),
}

# Soft prior weights — doc-type ranks still matter, but strong text cues can win.
_DOC_TYPE_PRIOR_WEIGHTS = (3.2, 2.4, 1.7, 1.1, 0.7)

# Keyword → style boosts (weight, style).
_STYLE_TEXT_SIGNALS: tuple[tuple[str, float, str], ...] = (
    (r"\b(exam|homework|worked example|theorem|proof|derive|derivation|formula)\b", 2.6, "worked_example"),
    (r"\b(top \d+|ranking|listicle|key takeaways?|\d+ (?:things|ways|tips|reasons|steps))\b", 2.4, "big_stat"),
    (r"\b(glass|frosted|apple[- ]style|futuristic ui|ui showcase)\b", 2.4, "glass"),
    (r"\b(how[\s-]?to|step[\s-]?by[\s-]?step|walkthrough|getting started|tutorial|lab)\b", 3.2, "tutorial"),
    (r"\b(checklist|prerequisites?|install(?:ation)?|setup guide)\b", 1.6, "tutorial"),
    (r"\b(architecture|teardown|internals?|under the hood|trade-?offs?|anatomy)\b", 3.0, "teardown"),
    (r"\b(benchmark|latency|throughput|scorecard|vs\.?|versus|comparison)\b", 1.8, "teardown"),
    (r"\b(system design|whiteboard|diagram|node graph|concept map)\b", 3.0, "whiteboard"),
    (r"\b(history of|the story|cold open|documentary|oral history|timeline of)\b", 2.8, "documentary"),
    (r"\b(essay|op-?ed|long[- ]form|magazine|pull[- ]quote|literary)\b", 2.6, "editorial"),
    (r"\b(whitepaper|abstract|arxiv|doi|methodology|related work)\b", 2.2, "documentary"),
    (r"\b(minimal|sparse|quiet|restraint)\b", 1.4, "minimal"),
    (r"\b(launch|vision|cinematic|trailer|keynote)\b", 2.8, "cinematic"),
    (r"\b(hook|viral|shorts?|scroll[- ]stop|punchy|10×|10x)\b", 2.4, "bold"),
    (r"\b(explainer|mechanism|transformer|attention|llm|rag)\b", 1.5, "explainer"),
    (r"\b(product demo|feature tour|changelog|release notes)\b", 1.8, "modern"),
    (r"\b(hybrid|mixed format|full lesson|deep dive|complete guide)\b", 2.6, "hybrid"),
    (r"\b(neon|glow|glassmorph|retro[- ]future|synthwave|hype)\b", 2.4, "neon"),
    (r"\b(blueprint|schematic|spec sheet|engineering|wiring|circuit|CAD)\b", 2.6, "blueprint"),
    (r"\b(for beginners|kids|fun|friendly|playful|easy intro|explain like)\b", 2.2, "playful"),
    (r"\b(terminal|command[- ]line|CLI|shell|bash|npm|git|docker|kubectl|coding)\b", 2.6, "terminal"),
    (r"\b(kinetic|typewriter|word slam|motion type|remotion)\b", 2.8, "kinetic"),
    (r"\b(kpi|metrics?|dashboard|gauge|chart|benchmark results?|dataviz)\b", 2.6, "dataviz"),
    (r"\b(app demo|ui mock|device frame|screenshot tour|product ui)\b", 2.6, "device"),
    (r"\b(news brief|roundup|lower[- ]third|breaking|broadcast)\b", 2.4, "broadcast"),
    (r"\b(pitch deck|investor|fundraising|traction|seed round)\b", 3.0, "pitch"),
    (r"\b(gamma\.app|gamma style|pastel deck|soft cards)\b", 3.0, "gamma"),
    (r"\b(keynote|apple keynote|sparse slides|giant type)\b", 2.8, "keynote"),
    (r"\b(powerpoint|ppt\b|classic slides|title and bullets|boardroom deck)\b", 2.8, "slides"),
    (r"\b(notion|wiki deck|docs?-style|callout block)\b", 2.6, "notion"),
    (r"\b(qbr|board deck|executive|agenda|quarterly review)\b", 2.6, "corporate"),
    (r"\b(saas|pricing page|feature tour|product marketing|landing)\b", 2.4, "saas"),
    (r"\b(card stack|one idea per card|smart layout)\b", 2.4, "cards"),
    (r"\b(frosted|glass panel|airy deck)\b", 2.2, "glass"),
    (r"\b(kinetic hybrid|motion[- ]first teach)\b", 2.4, "hybrid_kinetic"),
    (r"\b(data[- ]heavy|metrics hybrid|kpi pack)\b", 2.4, "hybrid_data"),
    (r"\b(story hybrid|narrative teach|paper story)\b", 2.2, "hybrid_story"),
    (r"\b(geometric|triangle|navy cyan|architecture deck)\b", 2.8, "geo_navy"),
    (r"\b(coral|orange gradient|split hero|marketing pitch)\b", 2.8, "coral_split"),
    (r"\b(blush|dusty rose|soft pink|wellness|mission vision)\b", 2.8, "blush_soft"),
    (r"\b(mosaic|mood board|portfolio collage|gallery grid)\b", 2.8, "mosaic"),
    (r"\b(process flow|roadmap|onboarding steps|methodology)\b", 2.6, "process"),
    (r"\b(workshop agenda|conference track|numbered agenda)\b", 2.6, "agenda"),
    (r"\b(rainbow|multicolou?r bar|bright multipurpose|colorful pitch)\b", 2.8, "rainbow_bar"),
    (r"\b(overlapping circles|circle stack|pill columns)\b", 2.6, "circle_stack"),
    (r"\b(hexagon|hex grid|logo wall|partner grid|ecosystem)\b", 2.6, "hex_grid"),
    (r"\b(soft wave|wavy corporate|flat marketing|values deck)\b", 2.6, "wave_soft"),
    (r"\b(swiss|m[uü]ller-brockmann|clinical grid|registration marks)\b", 2.8, "swiss_pulse"),
    (r"\b(velvet|vignelli|luxury keynote|wide tracking)\b", 2.8, "velvet_std"),
    (r"\b(deconstructed|industrial type|scan[- ]?lines|glitch deck)\b", 2.8, "deconstructed"),
    (r"\b(maximalist|megatype|anton type|type layers)\b", 2.8, "maximalist"),
    (r"\b(data drift|anadol|particle field|immersive ai)\b", 2.8, "data_drift"),
    (r"\b(soft signal|playfair|wellness deck|intimate brand)\b", 2.8, "soft_signal"),
    (r"\b(folk frequency|fredoka|festive|consumer brand)\b", 2.8, "folk_freq"),
    (r"\b(shadow cut|film noir|noir title|dramatic reveal)\b", 2.8, "shadow_cut"),
    (r"\b(kinetic center|center[- ]?build|word push)\b", 2.8, "kinetic_center"),
    (r"\b(lower[- ]?third|name plate|broadcast plate)\b", 2.8, "lower_third"),
    (r"\b(promo sprint|product promo|feature sprint)\b", 2.6, "promo_sprint"),
    (r"\b(bento|bento grid|feature mosaic)\b", 2.8, "bento"),
    (r"\b(big stat|giant kpi|one number)\b", 2.8, "big_stat"),
    (r"\b(pull[- ]?quote|quote pull|testimonial slide)\b", 2.6, "quote_pull"),
    (r"\b(timeline rail|roadmap rail|release train)\b", 2.6, "timeline_rail"),
    (r"\b(split media|photo split|media copy)\b", 2.6, "split_media"),
    (r"\b(caption pop|karaoke caption|word pop|shorts caption)\b", 2.8, "caption_pop"),
    (r"\b(chart race|bar race|racing bars|benchmark race)\b", 2.8, "chart_race"),
    (r"\b(logo intro|brand sting|logo burst|cold open brand)\b", 2.6, "logo_intro"),
    (r"\b(proof duo|myth vs fact|claim evidence|before after)\b", 2.6, "proof_duo"),
    (r"\b(kpi strip|metric strip|okr strip|board metrics)\b", 2.6, "kpi_strip"),
    (r"\b(stack cards|card stack|layered cards|peeking cards)\b", 2.6, "stack_cards"),
    (r"\b(biennale|museum catalogue|instrument serif)\b", 2.8, "hf_biennale"),
    (r"\b(blockframe|neobrutal|hard shadow poster)\b", 2.8, "hf_blockframe"),
    (r"\b(cobalt grid|risograph|graph paper)\b", 2.8, "hf_cobalt"),
    (r"\b(product launch video|feature sprint|launch video)\b", 2.6, "hf_product_launch"),
    (r"\b(faceless explainer|faceless youtube)\b", 2.6, "hf_faceless"),
    (r"\b(word slam|one word lockup)\b", 2.6, "word_slam"),
    (r"\b(title only|one line title slide)\b", 2.4, "title_only"),
)


def get_style_spec(video_style: str | None) -> dict:
    """Return a defensive copy of a known style (falls back to the default).

    ``auto`` resolves to the default until :func:`apply_auto_video_style` runs
    against document analysis — callers that need the pick should resolve first.
    """
    raw = (video_style or "").strip().lower()
    raw = STYLE_ALIASES.get(raw, raw)
    if raw in ("", AUTO_VIDEO_STYLE):
        key = DEFAULT_VIDEO_STYLE
    else:
        key = raw if raw in VIDEO_STYLES else DEFAULT_VIDEO_STYLE
    return deepcopy(VIDEO_STYLES[key])


def _look(style_key: str) -> dict:
    """What the picker shows for a style: the *real* design family it renders as.

    The renderer (``pipeline.edu_theme``) maps every style key to one of twelve
    families and one of four font pairs, so the UI reads the same tables.
    """
    from .pipeline.edu_theme import FAMILY_INFO, _FONTS, edu_family

    fam, var = edu_family(style_key)
    info = FAMILY_INFO[fam]
    hf, _hw, bf = _FONTS[fam][var]
    return {
        "category": fam,
        "category_label": info["label"],
        "family": fam,
        "family_blurb": info["blurb"],
        "layout_mode": fam,
        "font_label": f"{hf} + {bf}",
        "font_stack": f'"{hf}", system-ui, sans-serif',
        "uses": info["uses"],
        "flagship": info["flagship"] == style_key,
    }


def public_video_styles() -> list[dict]:
    """Compact representation safe to expose to the frontend.

    Prepends an ``auto`` option so the UI can defer the pick to content analysis.
    ``category`` is the design family (Whiteboard, Notebook, Editorial,
    Broadcast, Poster, Bento) the style actually renders as.
    """
    auto = {
        "key": AUTO_VIDEO_STYLE,
        "label": "Auto",
        "description": "Picks the best template from the document type, topic, and format.",
        "example": "Smart match · from content",
        "template": "Analyze → score styles → apply arc",
        "category": "auto",
        "category_label": "Auto",
    }
    out = [auto]
    for s in VIDEO_STYLES.values():
        if s["key"] in PICKER_HIDDEN:
            continue
        look = _look(s["key"])
        out.append({
            "key": s["key"],
            "label": s["label"],
            "description": look["family_blurb"],
            "example": s.get("example", ""),
            "template": s.get("template", ""),
            "category": look["category"],
            "category_label": look["category_label"],
            "family": look["family"],
            "font_label": look["font_label"],
            "font_stack": look["font_stack"],
            "motif": s.get("motif") or s["key"],
            "layout_mode": look["layout_mode"],
            "uses": look["uses"],
            "variety": s.get("template") or "",
        })
    return out


def public_style_categories() -> list[dict]:
    """Ordered chips for the style filters: the twelve real templates."""
    from .pipeline.edu_theme import FAMILY_INFO

    return [{"key": k, "label": v["label"], "blurb": v["blurb"]} for k, v in FAMILY_INFO.items()]


def recommend_video_style(
    *,
    analysis: dict | None = None,
    text: str = "",
    video_format: str | None = None,
) -> dict:
    """Score visual styles from doc analysis + text + format; return the winner.

    Returns ``{key, label, reason, scores}``. Always a known VIDEO_STYLES key.
    """
    scores = {k: 0.0 for k in VIDEO_STYLES}
    analysis = analysis or {}
    doc_type = str(analysis.get("doc_type") or "other").strip().lower()
    priors = _DOC_TYPE_STYLE_PRIORS.get(doc_type) or _DOC_TYPE_STYLE_PRIORS["other"]
    for i, key in enumerate(priors):
        if key in scores:
            w = _DOC_TYPE_PRIOR_WEIGHTS[i] if i < len(_DOC_TYPE_PRIOR_WEIGHTS) else 0.5
            scores[key] += w

    blob = " ".join(
        str(analysis.get(k) or "")
        for k in ("subject", "audience", "tone", "teaching_angle", "summary", "title")
    ).lower()
    if analysis.get("is_ml_topic") or re.search(r"\b(ml|llm|neural|transformer|model)\b", blob):
        scores["explainer"] += 1.4
        scores["teardown"] += 0.9
        scores["whiteboard"] += 0.6
    if re.search(r"\b(beginner|student|learn|coach|practical)\b", blob):
        scores["tutorial"] += 1.2
        scores["explainer"] += 0.6
    if re.search(r"\b(executive|board|investor|vision)\b", blob):
        scores["cinematic"] += 1.2
        scores["bold"] += 0.8
        scores["minimal"] += 0.5
    if re.search(r"\b(researcher|academic|scholarly)\b", blob):
        scores["documentary"] += 1.0
        scores["editorial"] += 0.8
        scores["minimal"] += 0.6

    try:
        spec = get_video_spec(video_format)
    except Exception:
        spec = get_video_spec(None)
    orient = spec.get("orientation") or "landscape"
    fmt_key = spec.get("key") or ""
    platform = (spec.get("platform") or "").lower()
    if orient in ("vertical", "square") or fmt_key in {
        "youtube_shorts", "instagram_reels", "tiktok", "instagram_square",
    }:
        scores["bold"] += 2.6
        scores["cinematic"] += 1.4
        scores["explainer"] += 1.0
        scores["editorial"] -= 0.8
        scores["documentary"] -= 0.4
    elif "linkedin" in platform or fmt_key == "linkedin_video":
        scores["modern"] += 1.8
        scores["editorial"] += 1.2
        scores["teardown"] += 1.0
        scores["bold"] -= 0.6
    else:
        scores["explainer"] += 0.8
        scores["documentary"] += 0.4
        scores["modern"] += 0.5

    sample = (text or "")[:10000].lower()
    # Drop VLM Figure: appearance notes so image chrome (colors, "whiteboard look",
    # brand UI) cannot bias Auto style when the user left style unlocked.
    sample = re.sub(r"(?im)^figure:.*$", " ", sample)
    sample = re.sub(
        r"\b(color(?:s|ed)?|palette|theme|brand(?:ing)?|font(?:s)?|"
        r"dark mode|light mode|neon glow|gradient background)\b",
        " ",
        sample,
    )
    matched_cue = False
    strong_hits = 0
    for pat, weight, style in _STYLE_TEXT_SIGNALS:
        if style in scores and re.search(pat, sample):
            scores[style] += weight
            if weight >= 2.4:
                matched_cue = True
                strong_hits += 1
                # Strong topic cues should beat soft format/doc priors.
                scores[style] += 2.4

    words = len(sample.split())
    # Mixed signals → Hybrid (channel-style rotation across templates).
    if "hybrid" in scores and (strong_hits >= 2 or words > 1800):
        scores["hybrid"] += 2.8 if strong_hits >= 2 else 1.6

    if words > 2500:
        scores["documentary"] += 0.8
        scores["editorial"] += 0.5
        scores["explainer"] += 0.4
        scores["bold"] -= 0.5
    elif words and words < 350:
        scores["bold"] += 0.6
        scores["minimal"] += 0.4
        scores["cinematic"] += 0.3

    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    # Only use doc-type prior as a tie-break when the race is close.
    if top - second < 0.45:
        near = {k for k, v in scores.items() if v >= top - 0.45}
        for key in priors:
            if key in near:
                best = key
                break

    label = VIDEO_STYLES[best]["label"]
    reason_bits: list[str] = []
    if doc_type and doc_type != "other":
        reason_bits.append(doc_type)
    if matched_cue:
        reason_bits.append("topic cues")
    if orient in ("vertical", "square"):
        reason_bits.append("short-form format")
    reason = (
        f"Matched {label} from "
        + (", ".join(reason_bits) if reason_bits else "content signals")
    )
    return {
        "key": best,
        "label": label,
        "reason": reason,
        "scores": {k: round(v, 2) for k, v in sorted(scores.items(), key=lambda kv: -kv[1])},
    }


def apply_auto_video_style(
    options: dict | None,
    *,
    analysis: dict | None = None,
    text: str = "",
) -> dict:
    """Resolve ``video_style=auto`` in-place using analysis + text + format.

    Explicit style keys are left untouched. Returns the (possibly mutated) options.
    """
    opts = options if options is not None else {}
    raw = str(opts.get("video_style") or "").strip().lower()
    if raw and raw != AUTO_VIDEO_STYLE:
        if not opts.get("video_style_label") and raw in VIDEO_STYLES:
            opts["video_style_label"] = VIDEO_STYLES[raw]["label"]
        # Explicit lock — drop stale Auto metadata from a prior run.
        opts["video_style_was_auto"] = False
        opts.pop("video_style_reason", None)
        return opts
    rec = recommend_video_style(
        analysis=analysis,
        text=text,
        video_format=opts.get("video_format"),
    )
    opts["video_style"] = rec["key"]
    opts["video_style_label"] = rec["label"]
    opts["video_style_reason"] = rec["reason"]
    opts["video_style_was_auto"] = True
    return opts


# Style → preferred color theme when video_theme is Auto.
_STYLE_THEME_HINTS: dict[str, str] = {
    "modern": "aurora",
    "minimal": "paper",
    "editorial": "ivory",
    "bold": "sunset",
    "explainer": "midnight",
    "documentary": "slate",
    "teardown": "cyber",
    "tutorial": "snow",
    "whiteboard": "snow",
    "cinematic": "nebula",
    "neon": "cyber",
    "blueprint": "midnight",
    "playful": "mint",
    "terminal": "slate",
    "hybrid": "aurora",
    "hybrid_kinetic": "cyber",
    "hybrid_data": "midnight",
    "hybrid_story": "slate",
    "kinetic": "nebula",
    "dataviz": "emerald",
    "device": "aurora",
    "broadcast": "sunset",
    "cards": "paper",
    "pitch": "midnight",
    "corporate": "slate",
    "glass": "snow",
    "saas": "aurora",
    "gamma": "mint",
    "keynote": "snow",
    "slides": "paper",
    "notion": "ivory",
    "geo_navy": "midnight",
    "coral_split": "sunset",
    "blush_soft": "mint",
    "mosaic": "paper",
    "process": "aurora",
    "agenda": "snow",
    "rainbow_bar": "paper",
    "circle_stack": "mint",
    "hex_grid": "paper",
    "wave_soft": "aurora",
    "swiss_pulse": "paper",
    "velvet_std": "slate",
    "deconstructed": "cyber",
    "maximalist": "sunset",
    "data_drift": "nebula",
    "soft_signal": "ivory",
    "folk_freq": "mint",
    "shadow_cut": "mono",
    "kinetic_center": "cyber",
    "lower_third": "midnight",
    "promo_sprint": "aurora",
    "bento": "snow",
    "big_stat": "midnight",
    "quote_pull": "ivory",
    "timeline_rail": "aurora",
    "split_media": "paper",
    "caption_pop": "sunset",
    "chart_race": "emerald",
    "logo_intro": "nebula",
    "proof_duo": "midnight",
    "kpi_strip": "paper",
    "stack_cards": "snow",
}
_STYLE_THEME_HINTS.update(EXTRA_THEME_HINTS)
_STYLE_THEME_HINTS.update({k: alias_theme(v) for k, v in _STYLE_THEME_HINTS.items()})

_DOC_TYPE_THEME_HINTS: dict[str, str] = {
    "research paper": "midnight",
    "book": "snow",
    "tutorial": "emerald",
    "manual": "snow",
    "article": "aurora",
    "slide deck": "cyber",
    "notes": "snow",
    "plan": "snow",
    "other": "aurora",
}


def get_theme_spec(video_theme: str | None) -> dict:
    """Return a defensive copy of a known theme (falls back to the default).

    ``auto`` resolves to the default until :func:`apply_auto_video_theme` runs.
    Retired palettes (paper, ivory, mint, nebula, slate, mono) alias onto the
    six curated themes so old jobs keep rendering.
    """
    raw = alias_theme((video_theme or "").strip().lower())
    if raw in ("", AUTO_VIDEO_THEME):
        key = DEFAULT_VIDEO_THEME
    else:
        key = raw if raw in VIDEO_THEMES else DEFAULT_VIDEO_THEME
    return deepcopy(VIDEO_THEMES[key])


# Preferred color themes per layout style (primary is _STYLE_THEME_HINTS).
# Remaining VIDEO_THEMES are still offered as full style×color permutations.
_STYLE_THEME_ALTS: dict[str, tuple[str, ...]] = {
    "modern": ("midnight", "paper", "nebula", "cyber", "emerald"),
    "minimal": ("mono", "snow", "slate", "midnight", "mint"),
    "editorial": ("slate", "aurora", "paper", "mono", "nebula"),
    "bold": ("cyber", "nebula", "midnight", "emerald", "mono"),
    "explainer": ("aurora", "emerald", "paper", "cyber", "mint"),
    "documentary": ("midnight", "ivory", "mono", "paper", "aurora"),
    "teardown": ("midnight", "mono", "nebula", "sunset", "slate"),
    "tutorial": ("mint", "paper", "aurora", "snow", "emerald"),
    "whiteboard": ("paper", "mint", "mono", "ivory", "snow"),
    "cinematic": ("sunset", "midnight", "cyber", "aurora", "mono"),
    "neon": ("nebula", "midnight", "sunset", "emerald", "mono"),
    "blueprint": ("slate", "mono", "cyber", "paper", "aurora"),
    "playful": ("sunset", "aurora", "snow", "paper", "nebula"),
    "terminal": ("midnight", "cyber", "mono", "emerald", "nebula"),
    "hybrid": ("midnight", "emerald", "paper", "cyber", "sunset"),
    "hybrid_kinetic": ("nebula", "midnight", "sunset", "aurora", "mono"),
    "hybrid_data": ("aurora", "cyber", "emerald", "paper", "mono"),
    "hybrid_story": ("ivory", "midnight", "aurora", "mono", "paper"),
    "kinetic": ("cyber", "sunset", "midnight", "aurora", "mono"),
    "dataviz": ("midnight", "cyber", "mint", "paper", "mono"),
    "device": ("midnight", "paper", "cyber", "mint", "snow"),
    "broadcast": ("midnight", "cyber", "mono", "aurora", "slate"),
    "cards": ("aurora", "snow", "mint", "midnight", "ivory"),
    "pitch": ("aurora", "cyber", "emerald", "paper", "sunset"),
    "corporate": ("midnight", "paper", "mono", "ivory", "aurora"),
    "glass": ("aurora", "mint", "midnight", "paper", "nebula"),
    "saas": ("midnight", "cyber", "mint", "paper", "emerald"),
    "gamma": ("snow", "paper", "aurora", "mint", "ivory"),
    "keynote": ("midnight", "mono", "paper", "ivory", "cyber"),
    "slides": ("midnight", "slate", "mono", "aurora", "snow"),
    "notion": ("snow", "paper", "mint", "mono", "aurora"),
    "geo_navy": ("paper", "slate", "mono", "cyber", "snow"),
    "coral_split": ("cyber", "nebula", "midnight", "emerald", "mono"),
    "blush_soft": ("snow", "paper", "ivory", "aurora", "mono"),
    "mosaic": ("midnight", "aurora", "mint", "snow", "ivory"),
    "process": ("midnight", "cyber", "emerald", "paper", "mint"),
    "agenda": ("paper", "mint", "aurora", "ivory", "mono"),
    "rainbow_bar": ("snow", "mint", "aurora", "sunset", "ivory"),
    "circle_stack": ("snow", "paper", "aurora", "ivory", "mono"),
    "hex_grid": ("snow", "mint", "aurora", "ivory", "sunset"),
    "wave_soft": ("snow", "mint", "paper", "ivory", "midnight"),
    "swiss_pulse": ("snow", "mono", "midnight", "slate", "paper"),
    "velvet_std": ("midnight", "ivory", "mono", "paper", "snow"),
    "deconstructed": ("midnight", "sunset", "mono", "nebula", "cyber"),
    "maximalist": ("cyber", "nebula", "midnight", "emerald", "mono"),
    "data_drift": ("midnight", "cyber", "aurora", "mono", "emerald"),
    "soft_signal": ("snow", "mint", "paper", "aurora", "mono"),
    "folk_freq": ("sunset", "aurora", "paper", "snow", "cyber"),
    "shadow_cut": ("midnight", "slate", "cyber", "sunset", "nebula"),
    "kinetic_center": ("nebula", "midnight", "sunset", "aurora", "mono"),
    "lower_third": ("cyber", "slate", "mono", "aurora", "sunset"),
    "promo_sprint": ("midnight", "cyber", "mint", "paper", "emerald"),
    "bento": ("midnight", "aurora", "mint", "ivory", "paper"),
    "big_stat": ("paper", "snow", "cyber", "emerald", "mono"),
    "quote_pull": ("snow", "paper", "slate", "mint", "mono"),
    "timeline_rail": ("midnight", "cyber", "paper", "mint", "snow"),
    "split_media": ("midnight", "aurora", "mint", "snow", "ivory"),
    "caption_pop": ("cyber", "nebula", "midnight", "mint", "mono"),
    "chart_race": ("midnight", "cyber", "paper", "aurora", "mono"),
    "logo_intro": ("midnight", "cyber", "aurora", "sunset", "mono"),
    "proof_duo": ("paper", "snow", "aurora", "emerald", "mono"),
    "kpi_strip": ("midnight", "snow", "aurora", "emerald", "mono"),
    "stack_cards": ("midnight", "aurora", "mint", "paper", "ivory"),
}


def _theme_keys_for_style(style_key: str) -> list[str]:
    """Ordered curated theme keys for a layout: preferred first, then the rest."""
    primary = alias_theme(_STYLE_THEME_HINTS.get(style_key, DEFAULT_VIDEO_THEME))
    ordered: list[str] = []
    for tk in (primary, *CURATED_THEME_KEYS):
        tk = alias_theme(tk)
        if tk in CURATED_THEME_KEYS and tk in VIDEO_THEMES and tk not in ordered:
            ordered.append(tk)
    return ordered


def public_visual_presets() -> list[dict]:
    """One card per layout. Colors live on the strip, not as duplicate cards.

    Studio and Admin share this list so names, geometry, and picks stay in sync.
    """
    presets: list[dict] = [{
        "key": "auto",
        "label": "Auto",
        "style": AUTO_VIDEO_STYLE,
        "theme": AUTO_VIDEO_THEME,
        "description": "Smart match — layout arc and colors from your document.",
        "swatch": ["#6366f1", "#22d3ee", "#34d399"],
        "style_label": "Auto",
        "theme_label": "Auto",
        "featured": True,
        "dark": True,
        "layout_mode": "auto",
        "category": "auto",
        "uses": "Smart match",
        "colors": {"bg": "#0a0a0c", "ink": "#f4f4f5", "accent": "#6366f1"},
    }]
    for sk, style in VIDEO_STYLES.items():
        if sk in PICKER_HIDDEN:
            continue
        tk = alias_theme(_STYLE_THEME_HINTS.get(sk, DEFAULT_VIDEO_THEME))
        if tk not in CURATED_THEME_KEYS or tk not in VIDEO_THEMES:
            tk = DEFAULT_VIDEO_THEME
        theme = VIDEO_THEMES[tk]
        base = theme.get("base") or {}
        swatch = list(theme.get("swatch") or [])
        look = _look(sk)
        cat = look["category"]
        layout_mode = look["layout_mode"]
        presets.append({
            "key": f"{sk}:{tk}",
            "label": style["label"],
            "style": sk,
            "theme": tk,
            "category": cat,
            "category_label": look["category_label"],
            "family": look["family"],
            "description": (
                f"{look['family_blurb']} Font: {look['font_label']}."
            ),
            "swatch": swatch,
            "style_label": style["label"],
            "theme_label": theme["label"],
            "font_label": look["font_label"],
            "font_stack": look["font_stack"],
            "motif": style.get("motif") or sk,
            "layout_mode": layout_mode,
            "example": style.get("example", ""),
            "template": style.get("template", ""),
            "variety": style.get("template", ""),
            "uses": look["uses"],
            "featured": look["flagship"],
            "dark": bool(base.get("dark")),
            "colors": {
                "bg": base.get("bg") or "#0a0a0c",
                "ink": base.get("ink") or "#f4f4f5",
                "accent": (swatch[0] if swatch else "#6366f1"),
            },
        })
    return presets


def resolve_visual_preset_key(style: str | None, theme: str | None) -> str:
    """Map separate style/theme picks back to a preset key for the UI."""
    s = (style or "").strip().lower()
    t = (theme or "").strip().lower()
    if s in ("", AUTO_VIDEO_STYLE) and t in ("", AUTO_VIDEO_THEME):
        return "auto"
    if s in ("", AUTO_VIDEO_STYLE):
        s = DEFAULT_VIDEO_STYLE
    if t in ("", AUTO_VIDEO_THEME):
        t = alias_theme(_STYLE_THEME_HINTS.get(s, DEFAULT_VIDEO_THEME))
    else:
        t = alias_theme(t)
    key = f"{s}:{t}"
    return key if s and t else "auto"


def public_video_themes() -> list[dict]:
    """Compact representation safe to expose to the frontend.

    Prepends an ``auto`` option so the UI can defer the pick to content analysis.
    """
    auto = {
        "key": AUTO_VIDEO_THEME,
        "label": "Auto",
        "description": "Picks a color theme from document type and visual style.",
        "swatch": ["#6366f1", "#22d3ee", "#34d399"],
        "dark": True,
    }
    return [auto] + [
        {
            "key": t["key"],
            "label": t["label"],
            "description": t["description"],
            "swatch": t["swatch"],
            "dark": bool(t["base"].get("dark", True)),
            "colors": {
                "bg": t["base"].get("bg") or "#0a0a0c",
                "ink": t["base"].get("ink") or "#f4f4f5",
                "accent": (t["swatch"] or ["#6366f1"])[0],
            },
        }
        for t in VIDEO_THEMES.values()
        if t["key"] in CURATED_THEME_KEYS
    ]


def recommend_video_theme(
    *,
    analysis: dict | None = None,
    video_style: str | None = None,
    video_format: str | None = None,
) -> dict:
    """Pick a color theme from doc type, resolved style, and format."""
    analysis = analysis or {}
    doc_type = str(analysis.get("doc_type") or "other").strip().lower()
    style = (video_style or "").strip().lower()
    if style in ("", AUTO_VIDEO_STYLE):
        style = DEFAULT_VIDEO_STYLE

    key = alias_theme(
        _STYLE_THEME_HINTS.get(style)
        or _DOC_TYPE_THEME_HINTS.get(doc_type)
        or DEFAULT_VIDEO_THEME
    )
    # Short-form prefers punchier palettes.
    try:
        spec = get_video_spec(video_format)
    except Exception:
        spec = get_video_spec(None)
    if (spec.get("orientation") or "") in ("vertical", "square"):
        key = {"aurora": "sunset", "midnight": "cyber", "snow": "sunset"}.get(key, key)
        if key not in ("sunset", "cyber"):
            key = "sunset" if "sunset" in VIDEO_THEMES else key
    # Light themes for editorial/minimal on long-form.
    if style in {"minimal", "editorial", "whiteboard"} and spec.get("orientation") == "landscape":
        key = alias_theme(_STYLE_THEME_HINTS.get(style, key))

    key = alias_theme(key)
    if key not in CURATED_THEME_KEYS or key not in VIDEO_THEMES:
        key = DEFAULT_VIDEO_THEME
    label = VIDEO_THEMES[key]["label"]
    reason = f"Matched {label} for {style or 'style'} · {doc_type or 'content'}"
    return {"key": key, "label": label, "reason": reason}


def apply_auto_video_theme(
    options: dict | None,
    *,
    analysis: dict | None = None,
) -> dict:
    """Resolve ``video_theme=auto`` in-place (after style is resolved)."""
    opts = options if options is not None else {}
    raw = str(opts.get("video_theme") or "").strip().lower()
    if raw and raw != AUTO_VIDEO_THEME:
        if not opts.get("video_theme_label") and raw in VIDEO_THEMES:
            opts["video_theme_label"] = VIDEO_THEMES[raw]["label"]
        # Explicit lock — drop stale Auto metadata from a prior run.
        opts["video_theme_was_auto"] = False
        opts.pop("video_theme_reason", None)
        return opts
    rec = recommend_video_theme(
        analysis=analysis,
        video_style=opts.get("video_style"),
        video_format=opts.get("video_format"),
    )
    opts["video_theme"] = rec["key"]
    opts["video_theme_label"] = rec["label"]
    opts["video_theme_reason"] = rec["reason"]
    opts["video_theme_was_auto"] = True
    return opts


def get_video_spec(video_format: str | None) -> dict:
    """Return a defensive copy of a known video format preset."""
    key = video_format if video_format in VIDEO_FORMATS else DEFAULT_VIDEO_FORMAT
    return deepcopy(VIDEO_FORMATS[key])


# Map a social channel to the video format that performs best there, so the UI
# and pipeline can pick the right aspect ratio / pacing automatically instead of
# forcing every platform into one landscape export.
PLATFORM_FORMAT_HINTS: dict[str, str] = {
    "youtube": "youtube_video",
    "youtube_shorts": "youtube_shorts",
    "shorts": "youtube_shorts",
    "instagram": "instagram_reels",
    "instagram_reels": "instagram_reels",
    "reels": "instagram_reels",
    "instagram_feed": "instagram_square",
    "tiktok": "tiktok",
    "linkedin": "linkedin_video",
    "x": "youtube_video",
    "twitter": "youtube_video",
    "facebook": "instagram_square",
}


def recommend_format_for_platform(platform: str | None) -> str:
    """Return the best video-format key for a given social channel.

    Falls back to the default landscape format for unknown platforms.
    """
    key = (platform or "").strip().lower().replace(" ", "_")
    return PLATFORM_FORMAT_HINTS.get(key, DEFAULT_VIDEO_FORMAT)


def public_video_formats() -> list[dict]:
    """Compact representation safe to expose to the frontend."""
    return [deepcopy(spec) for spec in VIDEO_FORMATS.values()]


def normalize_video_options(
    video_format: str | None = None,
    target_duration: int | str | None = None,
    youtube_video_url: str | None = "",
    video_theme: str | None = None,
    video_style: str | None = None,
) -> dict:
    """Normalize and clamp user-selectable video options.

    ``target_duration`` of 0 means auto. Otherwise values are clamped into the
    platform preset's accepted range so UI edits and API calls stay consistent.
    """
    spec = get_video_spec(video_format)
    raw_theme = (video_theme or "").strip().lower()
    if raw_theme in ("", AUTO_VIDEO_THEME):
        theme_key = AUTO_VIDEO_THEME
        theme_label = "Auto"
    else:
        theme = get_theme_spec(raw_theme)
        theme_key = theme["key"]
        theme_label = theme["label"]
    raw_style = (video_style or "").strip().lower()
    if raw_style in ("", AUTO_VIDEO_STYLE):
        style_key = AUTO_VIDEO_STYLE
        style_label = "Auto"
    else:
        style = get_style_spec(raw_style)
        style_key = style["key"]
        style_label = style["label"]
    try:
        td = int(target_duration or 0)
    except (TypeError, ValueError):
        td = 0

    if td:
        td = max(int(spec["min_duration"]), min(td, int(spec["max_duration"])))
    else:
        # Auto → format recommended length. Keeps slide planning, narration budget,
        # audio fit, and social copy on the same runtime target for every platform
        # (Shorts/Reels already required this; landscape Auto used to skip budgeting).
        td = int(spec.get("recommended_duration") or (60 if spec["orientation"] in ("vertical", "square") else 480))
        td = max(int(spec["min_duration"]), min(td, int(spec["max_duration"])))

    return {
        "video_format": spec["key"],
        "video_format_label": spec["label"],
        "platform": spec["platform"],
        "aspect_ratio": spec["aspect_ratio"],
        "orientation": spec["orientation"],
        "width": int(spec["width"]),
        "height": int(spec["height"]),
        "target_duration": td,
        "youtube_video_url": (youtube_video_url or "").strip(),
        "video_theme": theme_key,
        "video_theme_label": theme_label,
        "video_style": style_key,
        "video_style_label": style_label,
    }


def describe_duration(seconds: int | None) -> str:
    """Human-readable duration label used in stage details/prompts."""
    seconds = int(seconds or 0)
    if not seconds:
        return "Auto"
    m, s = divmod(seconds, 60)
    if m and s:
        return f"{m}m {s}s"
    if m:
        return f"{m}m"
    return f"{s}s"


def is_vertical_format(options: dict | None) -> bool:
    spec = get_video_spec((options or {}).get("video_format"))
    return spec["orientation"] == "vertical"


# Long-edge pixel size per quality tier. The short edge is derived from the
# format's aspect ratio so 16:9 -> e.g. 2560x1440 and 9:16 -> 1440x2560.
QUALITY_LONG_EDGE: dict[str, int] = {
    "720p": 1280,
    "1080p": 1920,
    "2k": 2560,
    "1440p": 2560,
    "qhd": 2560,
    "4k": 3840,
    "2160p": 3840,
    "uhd": 3840,
}


def resolve_output_dimensions(spec: dict, quality: str | None) -> tuple[int, int]:
    """Return (width, height) for the requested quality tier, preserving the
    format's aspect ratio. ``spec`` is a video format preset."""
    q = (quality or "1080p").strip().lower()
    long_edge = QUALITY_LONG_EDGE.get(q, 1920)
    base_w, base_h = int(spec["width"]), int(spec["height"])
    if base_w >= base_h:  # landscape: long edge is width
        w = long_edge
        h = round(long_edge * base_h / base_w)
    else:  # vertical: long edge is height
        h = long_edge
        w = round(long_edge * base_w / base_h)
    # Force even dimensions (required by yuv420p / libx264).
    return (w - (w % 2), h - (h % 2))