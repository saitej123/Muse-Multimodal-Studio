"""Shared audio ↔ visual sync constants and helpers.

Industry pattern (seek-safe Remotion/GSAP-style): the HTML slide owns a
normalized timeline ``t ∈ [0, 1]``. After TTS, audio duration maps linearly onto
that timeline via ``__seekFrame(frame, totalFrames)``. Python capture and the
in-page JS **must** use the same lead-in and focus weighting so sparse
keyframes land on the same highlight transitions the viewer sees.
"""
from __future__ import annotations

import re
from typing import Any

# Lead-in before the highlight walk (fraction of slide + hard cap in seconds).
FOCUS_LEAD_FRAC = 0.22
FOCUS_LEAD_MAX_SEC = 0.9
# Nudge highlights slightly ahead of the voice so they don't trail.
FOCUS_ANTICIPATION = 0.02
# Per-slide pad used when budgeting / fitting total duration.
SLIDE_OVERHEAD_SEC = 0.5
# Minimum dwell per focus item when padding short TTS to cover the visual walk.
MIN_FOCUS_DWELL_SEC = 0.75


def focus_lead_frames(total_frames: int, fps: float) -> int:
    """Same formula as the JS ``seekSlide`` lead-in."""
    fps = max(1.0, float(fps))
    total_frames = max(1, int(total_frames))
    lead = min(total_frames * FOCUS_LEAD_FRAC, FOCUS_LEAD_MAX_SEC * fps)
    return int(lead)


def focus_weights_from_texts(texts: list[str]) -> list[float]:
    """Weight dwell by on-screen text length (matches JS ``__focusCum``)."""
    weights = [float(max(6, len((t or "").strip()))) for t in texts]
    return weights or [1.0]


def focus_cumulative(weights: list[float]) -> list[float]:
    total = sum(weights) or 1.0
    acc = 0.0
    out: list[float] = []
    for w in weights:
        acc += w
        out.append(acc / total)
    return out


def focus_transition_frames(
    seek_total: int,
    fps: float,
    weights: list[float],
) -> list[int]:
    """Frame indices where the active highlight changes (incl. lead + end)."""
    seek_total = max(1, int(seek_total))
    lead = focus_lead_frames(seek_total, fps)
    if seek_total <= lead + 1 or len(weights) < 2:
        return [0, seek_total - 1]
    cum = focus_cumulative(weights)
    span = seek_total - lead
    frames = {0, lead, seek_total - 1}
    # Sample the start of each focus band (with anticipation, like JS).
    for c in cum[:-1]:
        # Invert: prog = raw + anticipation => raw = c - anticipation
        raw = max(0.0, min(0.999, c - FOCUS_ANTICIPATION))
        fi = lead + int(raw * span)
        frames.add(max(0, min(seek_total - 1, fi)))
        frames.add(max(0, min(seek_total - 1, fi + 1)))
    return sorted(frames)


def slide_focus_texts(slide: dict[str, Any]) -> list[str]:
    """Plain-text labels for each highlightable item on a slide (mirrors JS)."""
    if not isinstance(slide, dict):
        return []
    layout = str(slide.get("layout") or "").lower()
    if layout in {"cover", "hook"}:
        return []  # entrance only
    if layout == "steps":
        return [str(t) for t in (slide.get("steps") or []) if str(t).strip()]
    if layout == "stat":
        return [
            f"{(st.get('value', '') if isinstance(st, dict) else '')} {(st.get('label', '') if isinstance(st, dict) else '')}".strip()
            for st in (slide.get("stats") or [])
            if st
        ]
    if layout == "compare" and isinstance(slide.get("compare"), dict):
        cmp = slide["compare"]
        left = " ".join(str(x) for x in (cmp.get("left") or []))
        right = " ".join(str(x) for x in (cmp.get("right") or []))
        return [left or "A", right or "B"]
    if layout == "bars":
        bars = slide.get("bars")
        items = bars.get("items") if isinstance(bars, dict) else []
        return [
            str(it.get("label") or it.get("name") or "") if isinstance(it, dict) else str(it)
            for it in (items or [])
        ]
    if layout == "flow":
        flow = slide.get("flow")
        steps = flow.get("steps") if isinstance(flow, dict) else []
        return [
            str(st.get("label") or st.get("title") or st) if isinstance(st, dict) else str(st)
            for st in (steps or [])
        ]
    if layout == "hub":
        hub = slide.get("hub")
        nodes = hub.get("nodes") if isinstance(hub, dict) else []
        return [
            str(n.get("label") or "") if isinstance(n, dict) else str(n)
            for n in (nodes or [])
        ]
    if layout == "panel":
        panel = slide.get("panel")
        lines = panel.get("lines") if isinstance(panel, dict) else []
        return [str(ln) for ln in (lines or []) if str(ln).strip()]
    if layout == "transform":
        tr = slide.get("transform")
        nodes = tr.get("to_nodes") if isinstance(tr, dict) else []
        return [
            str(n.get("label") or n) if isinstance(n, dict) else str(n)
            for n in (nodes or [])
        ]
    if layout == "matrix":
        matrix = slide.get("matrix")
        items = matrix.get("items") if isinstance(matrix, dict) else []
        return [
            (
                f"{(it.get('label') or '')} {(it.get('detail') or '')}".strip()
                if isinstance(it, dict)
                else str(it)
            )
            for it in (items or [])
            if (isinstance(it, dict) and (it.get("label") or it.get("detail")))
            or (not isinstance(it, dict) and str(it).strip())
        ]
    texts = [str(b) for b in (slide.get("bullets") or []) if str(b).strip()]
    if not texts and layout in ("", "bullets") and not slide.get("image"):
        # The layout synthesizer derives items from narration when a slide has
        # no bullets; mirror it so the highlight walk and captured frames agree.
        from .. import layout_engine

        texts = layout_engine.derive_items(str(slide.get("narration") or ""))
        if len(texts) < 2:
            return []
    return texts


def focus_weights_for_slide(slide: dict[str, Any]) -> list[float]:
    """Dwell follows the spoken narration when the slide has one.

    On-screen labels are often much shorter than the sentence that explains
    them. Weighting by those labels makes the highlight finish early and sit
    on the last item while the voice is still on an earlier point.
    """
    texts = slide_focus_texts(slide)
    narration = str((slide or {}).get("narration") or "").strip() if isinstance(slide, dict) else ""
    words = narration.split()
    if len(texts) >= 2 and words:
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", narration) if s.strip()]
        if len(sentences) == len(texts):
            return [float(max(4, len(part.split()))) for part in sentences]
        return [
            float(max(4, int((i + 1) * len(words) / len(texts)) - int(i * len(words) / len(texts))))
            for i in range(len(texts))
        ]
    return focus_weights_from_texts(texts)


def min_visual_seconds(slide: dict[str, Any], motion_seconds: float = 1.8) -> float:
    """Minimum seconds the visual timeline needs before a settled hold is OK."""
    texts = slide_focus_texts(slide)
    n = len(texts)
    if n >= 2:
        return max(motion_seconds, FOCUS_LEAD_MAX_SEC + n * MIN_FOCUS_DWELL_SEC)
    return max(1.2, float(motion_seconds) + 0.35)


def js_sync_constants(fps: int) -> str:
    """Emit a small JS object so the HTML never drifts from Python."""
    return (
        f"const SYNC = {{ leadFrac: {FOCUS_LEAD_FRAC}, leadMaxSec: {FOCUS_LEAD_MAX_SEC}, "
        f"anticipation: {FOCUS_ANTICIPATION}, fps: {int(fps)} }};"
    )
