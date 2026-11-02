"""Generate publish + per-platform social metadata via the LLM.

Best-effort: if the LLM is unavailable or returns something unparseable we fall
back to a simple title/description derived from the lesson so the flow never
stalls before upload.

Publish metadata respects the selected ``video_format`` (Shorts vs long YouTube
vs LinkedIn vs Reels/TikTok) so title length, tone, and seed tags match the
export — not always a generic YouTube SEO block.
"""
from __future__ import annotations

import json
import re

from ..logging_setup import log
from ..video_options import get_video_spec
from .humanify import HUMAN_VOICE, KARPATHY_BLOG, with_human_voice

# Map video-format keys → social platforms that should get auto-generated copy.
FORMAT_SOCIAL_PLATFORMS: dict[str, list[str]] = {
    "youtube_video": ["youtube"],
    "youtube_shorts": ["youtube"],
    "instagram_reels": ["instagram"],
    "instagram_square": ["instagram"],
    "tiktok": ["tiktok"],
    "linkedin_video": ["linkedin"],
}


def platforms_for_format(video_format: str | None) -> list[str]:
    """Primary social channel(s) for a video format."""
    spec = get_video_spec(video_format)
    return list(FORMAT_SOCIAL_PLATFORMS.get(spec["key"], ["youtube"]))


def _publish_prompt_for(spec: dict) -> tuple[str, int, int, int]:
    """Return (style_blurb, title_max, desc_max, tag_count) for publish_meta."""
    key = spec.get("key") or ""
    if key == "youtube_shorts":
        return (
            "a YouTube Shorts creator writing your own caption. Punchy honest hook title; "
            "include #Shorts. Description: 1–3 human lines + a light CTA + a few tags.",
            70, 400, 10,
        )
    if key == "instagram_reels":
        return (
            "an Instagram Reels creator. Short hook title; caption with 2–5 emojis that "
            "earn their place; end with a tight hashtag block (specific > generic).",
            80, 1800, 15,
        )
    if key == "tiktok":
        return (
            "a TikTok creator. Scroll-stopping first line; casual and specific; "
            "2–4 emojis max; 4–6 real hashtags.",
            80, 300, 6,
        )
    if key == "instagram_square":
        return (
            "an Instagram feed creator. Hook + one concrete takeaway; light emoji; "
            "hashtag block at the end.",
            80, 1800, 12,
        )
    if key == "linkedin_video":
        return (
            "a LinkedIn operator posting from experience. First-person insight in line 1; "
            "0–2 emojis; 3–5 niche hashtags; no corporate fluff.",
            120, 1300, 5,
        )
    # Default: long-form YouTube
    return (
        "a YouTube educator writing your own upload page. Specific searchable title; "
        "description that sounds like you typed it — hook, 3 learn bullets, soft close, "
        "a few hashtags at the end.",
        90, 1500, 12,
    )


def _meta_prompt(title: str, script: str, spec: dict) -> str:
    style, title_max, desc_max, n_tags = _publish_prompt_for(spec)
    seed = ", ".join(str(t) for t in (spec.get("tags") or [])[:8])
    return with_human_voice(
        f"""You are {style}

Platform / format: {spec.get('label')} ({spec.get('platform')}, {spec.get('aspect_ratio')}).
Seed tags to prefer when relevant: {seed or 'education, tutorial'}.

Return ONLY a JSON object of this exact shape (no markdown, no code fences):
{{
  "title": "click-worthy but honest title, <= {title_max} characters",
  "description": "platform-appropriate description/caption, <= {desc_max} characters",
  "tags": ["{n_tags} short lowercase search tags / hashtag words WITHOUT #"]
}}

Lesson title: {title or 'Lesson'}

Narration script:
---
{(script or '')[:6000]}
---
"""
    )


def _fallback(title: str, script: str, spec: dict | None = None) -> dict:
    spec = spec or get_video_spec(None)
    _, title_max, desc_max, _ = _publish_prompt_for(spec)
    title = (title or "Automated Lesson").strip()
    first = (script or "").strip().split("\n\n")[0][: min(280, desc_max)]
    tags = [str(t).lstrip("#").lower() for t in (spec.get("tags") or []) if str(t).strip()]
    if not tags:
        tags = ["education", "tutorial", "learning", "explainer"]
    desc = first.strip()
    if spec.get("key") == "youtube_shorts" and "#Shorts" not in desc:
        desc = (desc + "\n\n#Shorts").strip()
    return {
        "title": title[:title_max],
        "description": desc[:desc_max],
        "tags": tags[:15],
    }


def _coerce(data: dict, title: str, script: str, spec: dict) -> dict:
    _, title_max, desc_max, _ = _publish_prompt_for(spec)
    fb = _fallback(title, script, spec)
    out = {
        "title": str(data.get("title") or fb["title"]).strip()[:title_max] or fb["title"],
        "description": str(data.get("description") or fb["description"]).strip()[:desc_max]
        or fb["description"],
    }
    if spec.get("key") == "youtube_shorts":
        if "#Shorts" not in out["title"]:
            base = out["title"].rstrip()
            suffix = " #Shorts"
            out["title"] = (base[: max(0, title_max - len(suffix))] + suffix).strip()
        if "#Shorts" not in out["description"]:
            out["description"] = (out["description"].rstrip() + "\n\n#Shorts")[:desc_max]

    tags = data.get("tags")
    seed = [str(t).lstrip("#").lower()[:30] for t in (spec.get("tags") or []) if str(t).strip()]
    if isinstance(tags, list):
        clean = [str(t).lstrip("#").strip().lower()[:30] for t in tags if str(t).strip()]
        # Prefer LLM tags, then seed format tags, deduped.
        merged: list[str] = []
        for t in clean + seed + fb["tags"]:
            if t and t not in merged:
                merged.append(t)
        out["tags"] = merged[:15] or fb["tags"]
    else:
        out["tags"] = (seed + fb["tags"])[:15] or fb["tags"]
    return out


def generate_metadata(
    title: str, script: str, video_format: str | None = None
) -> tuple[dict, str]:
    """Return ``(metadata, message)``. Never raises.

    ``metadata`` always has title/description/tags (LLM-authored or fallback).
    ``message`` explains what happened (for surfacing in the UI).
    """
    from ..capabilities import llm_available

    spec = get_video_spec(video_format)
    if not llm_available():
        log.bind(task="publish-meta").warning("no LLM; using fallback metadata")
        return _fallback(title, script, spec), "LLM unavailable — used basic metadata."

    prompt = _meta_prompt(title, script, spec)
    try:
        from .llm_parse import generate_structured
        from .llm_schemas import PublishMetaLLM

        parsed = generate_structured(prompt, PublishMetaLLM, task="publish-meta")
        meta = _coerce(parsed.model_dump(), title, script, spec)
        log.bind(task="publish-meta").success(
            f"metadata ({spec['key']}): {meta['title']!r}"
        )
        return meta, f"Metadata generated for {spec['label']}."
    except Exception as last_err:  # noqa: BLE001 - never propagate
        log.bind(task="publish-meta").warning(f"metadata LLM failed: {last_err}")
        return (
            _fallback(title, script, spec),
            f"Metadata generation failed ({last_err}); used basic metadata.",
        )


def _parse_json_object(text: str) -> dict:
    """Parse the first JSON object from LLM output (tolerates trailing junk).

    Models often emit trailing prose or a second object; brace-balance to the
    first complete ``{...}`` and strip trailing commas before parsing.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("empty metadata response")
    # Drop markdown fences if present.
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.I)
    if fenced:
        text = fenced.group(1).strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except Exception:
        pass

    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object in metadata response")
    depth = 0
    in_str = False
    esc = False
    end = -1
    for i, ch in enumerate(text[start:], start):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        raise ValueError("unterminated JSON object in metadata response")
    candidate = text[start : end + 1]
    try:
        data = json.loads(candidate)
    except Exception:
        repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
        data = json.loads(repaired)
    if not isinstance(data, dict):
        raise ValueError("metadata JSON was not an object")
    return data


# ------------------------------------------------------ per-platform social copy --
# Each supported platform has its own tone, length ceiling, and hashtag style.
SOCIAL_PLATFORMS: dict[str, dict] = {
    "youtube": {
        "label": "YouTube",
        "title_max": 90,
        "desc_max": 1500,
        "tags": 12,
        "style": (
            "your own YouTube upload notes — specific title, human description with a "
            "hook + learn bullets, 0–3 emojis, hashtags only at the end"
        ),
        "kind": "video",
    },
    "linkedin": {
        "label": "LinkedIn",
        "title_max": 120,
        "desc_max": 1300,
        "tags": 5,
        "style": (
            "a practitioner posting on LinkedIn — first-person insight, line breaks, "
            "0–2 emojis, 3–5 niche hashtags, zero corporate speak"
        ),
        "kind": "social",
    },
    "instagram": {
        "label": "Instagram",
        "title_max": 80,
        "desc_max": 2200,
        "tags": 15,
        "style": (
            "an Instagram creator — punchy caption, 3–6 earned emojis, then a block of "
            "10–15 real niche hashtags (specific first)"
        ),
        "kind": "social",
    },
    "tiktok": {
        "label": "TikTok",
        "title_max": 80,
        "desc_max": 300,
        "tags": 6,
        "style": (
            "a TikTok creator — hook in line 1, casual and specific, 2–4 emojis, "
            "4–6 short real hashtags"
        ),
        "kind": "social",
    },
    "x": {
        "label": "X / Twitter",
        "title_max": 80,
        "desc_max": 260,
        "tags": 4,
        "style": (
            "a sharp X poster — high-signal single post, optional 1 emoji, "
            "2–4 hashtags woven or at the end"
        ),
        "kind": "social",
    },
    "substack": {
        "label": "Substack",
        "title_max": 120,
        "desc_max": 12000,
        "tags": 8,
        "style": (
            "writing your Substack newsletter. Subject line = title. Body = FULL newsletter "
            "in Markdown (## sections, short paragraphs). Karpathy-style: curious, precise, "
            "first-person teacher; hook → 3–5 taught ideas → closing question."
        ),
        "kind": "blog",
    },
    "medium": {
        "label": "Medium",
        "title_max": 100,
        "desc_max": 12000,
        "tags": 5,
        "style": (
            "writing a Medium essay. Headline = title. Body = FULL article in Markdown "
            "(## sections, optional > pull-quotes). Karpathy-style technical narrative: "
            "concrete examples, trade-offs, scannable sections, no clickbait."
        ),
        "kind": "blog",
    },
}

_SOCIAL_PROMPT = """You are writing publish-ready copy for {platform} as if YOU are posting it.
Style: {style}. Keep the title <= {title_max} chars and the body/description
<= {desc_max} chars.
Video format context: {format_hint}
Prefer these seed tags/topics when relevant: {seed_tags}
{extra_context}

{human_voice}
{blog_voice}

Return ONLY this JSON (no markdown fences around the JSON itself):
{{
  "title": "platform-appropriate title/headline/subject",
  "description": "full body — caption, post, or article (Markdown ok for blogs; may include line breaks and emojis where appropriate)",
  "hashtags": ["{n} relevant tags WITHOUT the # symbol, lowercase, no spaces"]
}}

Lesson title: {title}

Source material (reuse this context; do not invent facts not grounded here):
---
{script}
---
"""


def _norm_hashtags(items, limit: int) -> list[str]:
    out: list[str] = []
    for t in items or []:
        tag = re.sub(r"[^0-9a-zA-Z]", "", str(t)).lower()
        if tag and tag not in out:
            out.append(tag)
    return out[:limit]


def _social_fallback(platform: str, title: str, script: str, tags: list[str] | None) -> dict:
    spec = SOCIAL_PLATFORMS.get(platform, SOCIAL_PLATFORMS["youtube"])
    first = (script or "").strip().split("\n\n")[0][: min(spec["desc_max"] - 60, 2000)]
    hashtags = _norm_hashtags(tags or ["education", "learning", "ai", "tutorial"], spec["tags"])
    return {
        "title": (title or "Lesson").strip()[: spec["title_max"]],
        "description": first.strip(),
        "hashtags": hashtags,
    }


def _format_hint(video_format: str | None, platform: str) -> str:
    spec = get_video_spec(video_format)
    key = spec.get("key") or ""
    bits = [f"{spec.get('label')} · {spec.get('aspect_ratio')} · ~{spec.get('recommended_duration')}s sweet spot"]
    if key == "youtube_shorts" and platform == "youtube":
        bits.append("Treat as Shorts: hooky title, include Shorts cue, short caption.")
    elif key in ("instagram_reels", "instagram_square") and platform == "instagram":
        bits.append("Write for Reels/feed: caption-first, hashtag block at end.")
    elif key == "tiktok" and platform == "tiktok":
        bits.append("Write for TikTok: first line is the scroll-stopper.")
    elif key == "linkedin_video" and platform == "linkedin":
        bits.append("Write for LinkedIn professionals; lead with the insight.")
    elif platform in ("substack", "medium"):
        bits.append("Long-form written piece for readers who may not watch the video.")
    return " ".join(bits)


def generate_social_metadata(
    title: str,
    script: str,
    platforms: list[str],
    base_tags: list[str] | None = None,
    video_format: str | None = None,
    *,
    extra_context: str = "",
) -> tuple[dict, str]:
    """Generate per-platform title/description/hashtags for ``platforms``.

    Returns ``({platform: {title, description, hashtags}}, message)``. Never
    raises; unknown platforms are ignored and failures fall back per-platform.
    When ``platforms`` is empty, uses the channels that match ``video_format``.
    """
    from ..capabilities import llm_available
    from . import llm_client

    fmt_spec = get_video_spec(video_format)
    seed = list(base_tags or []) + [
        str(t).lstrip("#") for t in (fmt_spec.get("tags") or []) if str(t).strip()
    ]
    wanted = [p for p in (platforms or []) if p in SOCIAL_PLATFORMS]
    if not wanted:
        wanted = [p for p in platforms_for_format(video_format) if p in SOCIAL_PLATFORMS] or ["youtube"]
    out: dict[str, dict] = {}
    if not llm_available():
        for p in wanted:
            out[p] = _social_fallback(p, title, script, seed)
        return out, "LLM unavailable — used basic social copy."

    ok = 0
    ctx_block = ""
    if (extra_context or "").strip():
        ctx_block = "Additional stored context (reuse; do not contradict):\n" + extra_context.strip()[:4000]

    def _one(p: str) -> tuple[str, dict, bool]:
        spec = SOCIAL_PLATFORMS[p]
        # Shorts: tighter YouTube ceilings when the export is vertical Shorts.
        title_max = spec["title_max"]
        desc_max = spec["desc_max"]
        n_tags = spec["tags"]
        style = spec["style"]
        if p == "youtube" and (fmt_spec.get("key") == "youtube_shorts"):
            title_max, desc_max, n_tags = 70, 400, 10
            style = (
                "your own Shorts caption — punchy #Shorts title energy, "
                "1–3 human lines, light emoji, real tags"
            )

        # Blog platforms get more source material + Karpathy essay voice.
        is_blog = spec.get("kind") == "blog"
        script_cap = 9000 if is_blog else 5000
        prompt = _SOCIAL_PROMPT.format(
            platform=spec["label"], style=style,
            title_max=title_max, desc_max=desc_max,
            n=n_tags, title=title or "Lesson",
            script=(script or "")[:script_cap],
            format_hint=_format_hint(video_format, p),
            seed_tags=", ".join(_norm_hashtags(seed, 8)) or "education, tutorial",
            extra_context=ctx_block or "(none)",
            human_voice=HUMAN_VOICE,
            blog_voice=KARPATHY_BLOG if is_blog else "",
        )
        try:
            from .llm_parse import generate_structured
            from .llm_schemas import SocialPostLLM

            parsed = generate_structured(prompt, SocialPostLLM, task="social-meta")
            data = parsed.model_dump()
            fb = _social_fallback(p, title, script, seed)
            title_out = str(data.get("title") or title or "Lesson").strip()[:title_max]
            desc_out = str(data.get("description") or "").strip()[:desc_max] or fb["description"]
            tags_out = _norm_hashtags(
                list(data.get("hashtags") or []) + seed, n_tags
            ) or fb["hashtags"]
            if p == "youtube" and fmt_spec.get("key") == "youtube_shorts":
                if "shorts" not in title_out.lower():
                    suffix = " #Shorts"
                    title_out = (title_out[: max(0, title_max - len(suffix))] + suffix).strip()
            return p, {
                "title": title_out,
                "description": desc_out,
                "hashtags": tags_out,
            }, True
        except Exception as e:  # noqa: BLE001
            log.bind(task="social-meta").warning(f"{p} copy failed: {e}")
            return p, _social_fallback(p, title, script, seed), False

    # Platforms are independent LLM calls — fan them out (cloud) or run
    # sequentially (local) via the provider-aware parallel_map.
    for p, meta, success in llm_client.parallel_map(_one, wanted):
        out[p] = meta
        if success:
            ok += 1
    msg = f"Social copy generated for {ok}/{len(wanted)} platform(s)."
    return out, msg
