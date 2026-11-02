"""Review generated slides for duplicates and voice ↔ visual sync issues.

Deterministic (no LLM). Runs after generate and on demand so the user can
re-check after editing narration. Optional ``user_notes`` focuses which
checks to emphasize (duplicate slides vs voice sync) and which slide numbers.
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from typing import Any

from .sync import MIN_FOCUS_DWELL_SEC, SLIDE_OVERHEAD_SEC, min_visual_seconds, slide_focus_texts

_STOP = {
    "a", "an", "the", "of", "and", "or", "to", "in", "on", "for", "with",
    "is", "are", "be", "this", "that", "it", "as", "at", "by", "from",
}


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [w for w in words if w not in _STOP and len(w) > 1]


def _norm(text: str) -> str:
    return " ".join(_tokens(text))


def _ratio(a: str, b: str) -> float:
    na, nb = _norm(a), _norm(b)
    if not na or not nb:
        return 0.0
    return SequenceMatcher(None, na, nb).ratio()


def _heading(slide: dict) -> str:
    if not isinstance(slide, dict):
        return str(slide or "")[:120]
    return str(
        slide.get("heading")
        or slide.get("quote")
        or (slide.get("hook") or {}).get("punchline")
        or ""
    ).strip()


def _narration(slide: dict) -> str:
    if isinstance(slide, dict):
        return str(slide.get("narration") or "").strip()
    return str(slide or "").strip()


def _visual_fingerprint(slide: dict) -> str:
    layout = str((slide or {}).get("layout") or "bullets").lower()
    labels = [_norm(t) for t in slide_focus_texts(slide or {})]
    labels = [t for t in labels if t]
    return layout + "|" + "|".join(sorted(labels)[:8])


def _word_count(text: str) -> int:
    return len((text or "").split())


def _speech_seconds(words: int, *, vertical: bool) -> float:
    wpm = 125.0 if vertical else 135.0
    return (max(0, words) / wpm) * 60.0


def _parse_user_notes(notes: str) -> dict[str, Any]:
    raw = (notes or "").strip()
    low = raw.lower()
    want_dup = True
    want_sync = True
    if raw:
        mentions_dup = any(
            w in low
            for w in (
                "duplicate", "duplicat", "same slide", "repeated", "repeat",
                "copy", "identical", "overlap",
            )
        )
        mentions_sync = any(
            w in low
            for w in (
                "sync", "voice", "timing", "narration", "audio", "highlight",
                "out of sync", "mismatch",
            )
        )
        if mentions_dup and not mentions_sync:
            want_sync = False
        elif mentions_sync and not mentions_dup:
            want_dup = False
    nums = [int(n) for n in re.findall(r"slide\s*(\d{1,2})\b", low)]
    # Treat 1-based slide numbers; drop implausible 0.
    focus = [n for n in nums if 1 <= n <= 80]
    return {
        "duplicates": want_dup,
        "voice_sync": want_sync,
        "slides": focus,
        "notes": raw,
    }


def _in_focus(idx: int, focus: list[int]) -> bool:
    if not focus:
        return True
    return (idx + 1) in focus


def review_slides(
    slides: list | None,
    *,
    options: dict | None = None,
    narration: str | None = None,
    user_notes: str = "",
) -> dict[str, Any]:
    """Return a review dict: issues, counts, and a short summary."""
    deck = [s if isinstance(s, dict) else {"narration": str(s), "heading": ""} for s in (slides or [])]
    n = len(deck)
    focus = _parse_user_notes(user_notes)
    opts = options if isinstance(options, dict) else {}
    spec_orient = str(opts.get("orientation") or "").lower()
    vertical = spec_orient in {"vertical", "square"}
    if not spec_orient:
        fmt = str(opts.get("video_format") or "")
        vertical = any(k in fmt for k in ("short", "reel", "tiktok", "vertical"))

    # Honor a user-edited joined narration when paragraph count matches.
    edited = (narration or "").strip()
    if edited:
        parts = [p.strip() for p in re.split(r"\n\s*\n", edited) if p.strip()]
        if len(parts) == n:
            for i, p in enumerate(parts):
                deck[i] = dict(deck[i])
                deck[i]["narration"] = p

    issues: list[dict[str, Any]] = []

    def add(
        kind: str,
        severity: str,
        message: str,
        *,
        slide: int | None = None,
        other: int | None = None,
        extra: dict | None = None,
    ) -> None:
        rec: dict[str, Any] = {
            "kind": kind,
            "severity": severity,
            "message": message,
        }
        if slide is not None:
            rec["slide"] = slide
        if other is not None:
            rec["other_slide"] = other
        if extra:
            rec.update(extra)
        issues.append(rec)

    if n == 0:
        add("empty", "error", "No slides to review yet — generate content first.")
        return _pack(issues, n, focus)

    if focus["duplicates"]:
        seen_head: list[tuple[int, str]] = []
        seen_fp: list[tuple[int, str]] = []
        seen_nar: list[tuple[int, str]] = []
        for i, sl in enumerate(deck):
            if not _in_focus(i, focus["slides"]):
                continue
            head = _heading(sl)
            fp = _visual_fingerprint(sl)
            nar = _narration(sl)
            for j, prev in seen_head:
                if head and _ratio(head, prev) >= 0.82:
                    add(
                        "duplicate_heading",
                        "warning",
                        f"Slide {i + 1} heading is almost the same as slide {j + 1}: “{_heading(deck[j])[:80]}”.",
                        slide=i + 1,
                        other=j + 1,
                    )
                    break
            for j, prev in seen_fp:
                if fp and fp == prev and "|" in fp:
                    labels = fp.split("|", 1)[-1]
                    if labels:
                        add(
                            "duplicate_visual",
                            "error" if i == j + 1 else "warning",
                            f"Slide {i + 1} repeats the same layout and on-screen points as slide {j + 1}.",
                            slide=i + 1,
                            other=j + 1,
                        )
                        break
            for j, prev in seen_nar:
                if nar and _word_count(nar) >= 12 and _ratio(nar, prev) >= 0.85:
                    add(
                        "duplicate_narration",
                        "warning",
                        f"Slide {i + 1} narration closely restates slide {j + 1}.",
                        slide=i + 1,
                        other=j + 1,
                    )
                    break
            if head:
                seen_head.append((i, head))
            if fp:
                seen_fp.append((i, fp))
            if nar:
                seen_nar.append((i, nar))

            layout = str(sl.get("layout") or "").lower()
            if i > 0 and layout and layout == str(deck[i - 1].get("layout") or "").lower():
                if layout not in {"cover", "hook"} and _in_focus(i - 1, focus["slides"]):
                    add(
                        "repeat_layout",
                        "info",
                        f"Slides {i} and {i + 1} use the same “{layout}” layout back-to-back — variety helps engagement.",
                        slide=i + 1,
                        other=i,
                    )

    if focus["voice_sync"]:
        for i, sl in enumerate(deck):
            if not _in_focus(i, focus["slides"]):
                continue
            nar = _narration(sl)
            layout = str(sl.get("layout") or "bullets").lower()
            words = _word_count(nar)
            texts = slide_focus_texts(sl)
            if not nar:
                add(
                    "empty_narration",
                    "error",
                    f"Slide {i + 1} has no narration — voiceover and highlights cannot sync.",
                    slide=i + 1,
                )
                continue
            if layout not in {"cover", "hook"} and words < 8:
                add(
                    "narration_too_short",
                    "warning",
                    f"Slide {i + 1} narration is only {words} words — too thin to cover the visual.",
                    slide=i + 1,
                )
            if words > 110:
                add(
                    "narration_too_long",
                    "warning",
                    f"Slide {i + 1} narration is {words} words — likely to overshoot the visual and drift sync.",
                    slide=i + 1,
                )
            if len(texts) >= 2:
                spoken = _norm(nar)
                missing = []
                for t in texts:
                    toks = _tokens(t)
                    distinctive = [w for w in toks if len(w) >= 4][:3]
                    if not distinctive:
                        continue
                    if not any(w in spoken for w in distinctive):
                        missing.append(t[:60])
                if missing and len(missing) >= max(1, len(texts) // 2):
                    add(
                        "voice_visual_mismatch",
                        "warning",
                        f"Slide {i + 1} voiceover never mentions on-screen beats: "
                        + "; ".join(f"“{m}”" for m in missing[:3])
                        + ". Highlights will feel out of sync.",
                        slide=i + 1,
                    )
                need = min_visual_seconds(sl, motion_seconds=1.8)
                speech = _speech_seconds(words, vertical=vertical)
                if speech + 0.15 < need and len(texts) >= 3:
                    add(
                        "voice_too_fast_for_highlights",
                        "warning",
                        f"Slide {i + 1} speech is ~{speech:.1f}s but {len(texts)} highlight "
                        f"items need ~{need:.1f}s ({MIN_FOCUS_DWELL_SEC:.2f}s each). "
                        "The walk will rush or skip.",
                        slide=i + 1,
                    )
            # Order check: first visual token should appear before later ones in narration.
            if len(texts) >= 3:
                positions: list[tuple[int, int]] = []
                low_nar = nar.lower()
                for ti, t in enumerate(texts):
                    toks = [w for w in _tokens(t) if len(w) >= 4]
                    if not toks:
                        continue
                    pos = low_nar.find(toks[0])
                    if pos >= 0:
                        positions.append((pos, ti))
                if len(positions) >= 3:
                    order = [ti for _, ti in sorted(positions)]
                    if order != sorted(order):
                        add(
                            "voice_order",
                            "info",
                            f"Slide {i + 1} explains on-screen items out of visual order — "
                            "highlights will fire against the wrong sentence.",
                            slide=i + 1,
                        )

    # Pad note (informational): overhead vs last slide.
    if n >= 2 and focus["voice_sync"]:
        total_words = sum(_word_count(_narration(s)) for s in deck)
        if total_words and n * float(SLIDE_OVERHEAD_SEC) > 8:
            pass  # not an issue by itself

    return _pack(issues, n, focus)


def _pack(issues: list[dict], n: int, focus: dict) -> dict[str, Any]:
    errors = sum(1 for i in issues if i.get("severity") == "error")
    warnings = sum(1 for i in issues if i.get("severity") == "warning")
    infos = sum(1 for i in issues if i.get("severity") == "info")
    dups = sum(1 for i in issues if str(i.get("kind", "")).startswith("duplicate") or i.get("kind") == "repeat_layout")
    syncs = sum(1 for i in issues if "voice" in str(i.get("kind", "")) or i.get("kind") in {
        "empty_narration", "narration_too_short", "narration_too_long",
    })
    if n == 0:
        summary = "No slides yet."
        ok = False
    elif errors:
        summary = f"{errors} blocking issue{'s' if errors != 1 else ''} across {n} slides."
        ok = False
    elif warnings:
        summary = f"{warnings} sync/duplicate warning{'s' if warnings != 1 else ''} on {n} slides — worth a look before narrating."
        ok = False
    elif infos:
        summary = f"{n} slides look solid. {infos} optional variety note{'s' if infos != 1 else ''}."
        ok = True
    else:
        summary = f"{n} slides look unique and voice-sync ready."
        ok = True
    if focus.get("notes"):
        summary = f"Checked against your notes. {summary}"
    score = max(0, 100 - errors * 28 - warnings * 10 - infos * 3)
    return {
        "ok": ok,
        "score": score,
        "slide_count": n,
        "counts": {
            "errors": errors,
            "warnings": warnings,
            "info": infos,
            "duplicates": dups,
            "voice_sync": syncs,
        },
        "focus": {
            "duplicates": bool(focus.get("duplicates")),
            "voice_sync": bool(focus.get("voice_sync")),
            "slides": focus.get("slides") or [],
            "notes": focus.get("notes") or "",
        },
        "summary": summary,
        "issues": issues,
    }
