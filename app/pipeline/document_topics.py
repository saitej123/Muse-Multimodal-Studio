"""Intelligent topic / section classification for large Studio uploads.

Turns a long book/paper/deck into a selectable topic map so the user can
produce one combined video or one video per topic — with web grounding later.
"""
from __future__ import annotations

import re
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..logging_setup import log
from .topic_prep import generate_structured_lite, lite_model

_LOG = log.bind(task="document-topics")

# Soft thresholds: above these we auto-suggest planning instead of one giant video.
PLAN_WORD_HINT = 2500
PLAN_CHAR_HINT = 18_000


class DocTopic(BaseModel):
    model_config = {"extra": "ignore"}

    id: str = ""
    name: str = ""
    summary: str = ""
    level: int = 1  # 1=major chapter/arc, 2=section, 3=subtopic
    char_start: int = 0
    char_end: int = 0
    estimated_minutes: int = 8
    recommended: bool = True
    tags: list[str] = Field(default_factory=list)
    focus: list[str] = Field(default_factory=list)

    @field_validator("focus", "tags", mode="before")
    @classmethod
    def _listish(cls, v: object) -> list[str]:
        if v is None:
            return []
        if isinstance(v, str):
            return [v] if v.strip() else []
        if isinstance(v, list):
            return [str(x).strip() for x in v if str(x).strip()]
        return []


class DocumentTopicBreakdown(BaseModel):
    model_config = {"extra": "ignore"}

    title: str = ""
    doc_type: str = ""  # book | paper | slides | notes | other
    summary: str = ""
    topics: list[DocTopic] = Field(default_factory=list)
    recommended_ids: list[str] = Field(default_factory=list)
    recommended_video_count: int = 1
    grouping_note: str = ""
    model: str = ""
    at: float = 0.0


def should_plan_topics(text: str) -> bool:
    """Heuristic: long / book-like sources benefit from topic planning."""
    t = text or ""
    words = len(t.split())
    if words >= PLAN_WORD_HINT or len(t) >= PLAN_CHAR_HINT:
        return True
    low = t[:8000].lower()
    markers = (
        "table of contents",
        "chapter 1",
        "chapter i",
        "\n## ",
        "part i",
        "part 1",
        "isbn",
    )
    hits = sum(1 for m in markers if m in low)
    return hits >= 2 and words >= 800


def _heading_candidates(text: str, *, limit: int = 120) -> list[dict[str, Any]]:
    """Cheap structural pass — markdown / Chapter N / numbered headings."""
    out: list[dict[str, Any]] = []
    patterns = (
        re.compile(r"^(#{1,3})\s+(.+)$", re.M),
        re.compile(r"^(chapter\s+\d+[.:\s].+)$", re.I | re.M),
        re.compile(r"^(part\s+[ivx\d]+[.:\s].+)$", re.I | re.M),
        re.compile(r"^(\d{1,2}(?:\.\d{1,2}){0,2})\s+([A-Z][^\n]{8,80})$", re.M),
    )
    seen: set[str] = set()
    for pat in patterns:
        for m in pat.finditer(text or ""):
            if len(out) >= limit:
                return out
            if pat.pattern.startswith("^(#{1,3})"):
                hashes, title = m.group(1), m.group(2).strip()
                level = min(3, len(hashes))
                name = title
                start = m.start()
            elif pat.pattern.startswith(r"^(\d"):
                name = f"{m.group(1)} {m.group(2).strip()}"
                level = 2 if "." in m.group(1) else 1
                start = m.start()
            else:
                name = m.group(1).strip()
                level = 1
                start = m.start()
            key = re.sub(r"\s+", " ", name.lower())[:80]
            if key in seen or len(name) < 4:
                continue
            seen.add(key)
            out.append({"name": name[:120], "level": level, "char_start": start})
    # Estimate ends from next start
    for i, row in enumerate(out):
        nxt = out[i + 1]["char_start"] if i + 1 < len(out) else len(text or "")
        row["char_end"] = max(row["char_start"] + 80, nxt)
    return out


def _assign_ids(topics: list[dict]) -> list[dict]:
    used: set[str] = set()
    for i, t in enumerate(topics):
        base = re.sub(r"[^a-z0-9]+", "-", (t.get("name") or f"topic-{i}").lower()).strip("-")
        base = (base[:40] or f"topic-{i}")
        tid = f"t{i:03d}-{base}"
        n = 2
        while tid in used:
            tid = f"t{i:03d}-{base}-{n}"
            n += 1
        used.add(tid)
        t["id"] = tid
    return topics


def classify_document_topics(
    text: str,
    *,
    filename: str = "",
    max_topics: int = 80,
) -> dict[str, Any]:
    """LLM + heading heuristics → DocumentTopicBreakdown for the Studio UI."""
    raw = (text or "").strip()
    if len(raw) < 200:
        raise ValueError("Document is too short to classify into topics")

    heads = _heading_candidates(raw, limit=min(120, max_topics + 20))
    head_block = "\n".join(
        f"- [{h['char_start']}-{h['char_end']}] L{h['level']}: {h['name']}"
        for h in heads[:80]
    ) or "(no clear headings — invent teachable topics from the prose)"

    # Cap prompt size; keep start + middle + end for long books.
    if len(raw) > 28000:
        third = len(raw) // 3
        sample = (
            raw[:10000]
            + "\n\n…[middle]…\n\n"
            + raw[third : third + 8000]
            + "\n\n…[end]…\n\n"
            + raw[-8000:]
        )
    else:
        sample = raw

    n = max(6, min(int(max_topics or 80), 100))
    prompt = f"""You are a senior curriculum designer for educational YouTube videos.
Classify this source into teachable TOPICS / SECTIONS a creator can select.

Filename hint: {filename or '(unknown)'}
Source length: {len(raw)} chars, ~{len(raw.split())} words

Detected headings (use as anchors; merge trivia; split monster chapters):
{head_block}

Source excerpt:
{sample[:26000]}

Return JSON DocumentTopicBreakdown:
- title: document title
- doc_type: book|paper|slides|notes|other
- summary: 2 sentences
- topics: 8–{n} items. Each:
  id: leave "" (server assigns)
  name: short teachable title (not "Chapter 3")
  summary: 1–2 sentences what a video on this topic covers
  level: 1 major arc | 2 section | 3 optional deep-dive
  char_start / char_end: best-effort offsets into the FULL source (use heading anchors)
  estimated_minutes: 5–18 for a focused explainer
  recommended: true if this should be in a first video pack (aim ~6–16 recommended)
  tags: 0–4 short tags
  focus: 2–4 concrete teaching angles (mechanisms, examples, pitfalls)
- recommended_ids: leave [] (server fills from recommended flags)
- recommended_video_count: how many separate videos you'd ship for a first pass
- grouping_note: one sentence advising single vs multi-video

Rules:
- Prefer VIDEO-SIZED topics (a viewer can finish one sitting), not 200 micro-headings.
- If the book truly has many distinct chapters, keep them — but mark only the best as recommended.
- Never invent content outside the source; names/summaries must reflect the document.
- Cover the whole arc (intro → core → advanced / conclusion), not just chapter 1.
"""
    parsed, used = generate_structured_lite(
        prompt,
        DocumentTopicBreakdown,
        task="document-topics",
        model=lite_model(),
    )
    data = parsed.model_dump()
    topics = [t if isinstance(t, dict) else t.model_dump() for t in (data.get("topics") or [])]
    # Clamp ranges + fill missing ends from heuristics
    length = len(raw)
    for t in topics:
        try:
            t["char_start"] = max(0, min(int(t.get("char_start") or 0), length))
            end = int(t.get("char_end") or 0)
            if end <= t["char_start"]:
                end = min(length, t["char_start"] + max(1200, length // max(8, len(topics))))
            t["char_end"] = max(t["char_start"] + 40, min(end, length))
        except Exception:
            t["char_start"] = 0
            t["char_end"] = min(length, 4000)
        t["estimated_minutes"] = max(4, min(20, int(t.get("estimated_minutes") or 8)))
    topics = _assign_ids(topics)[:n]
    if not any(t.get("recommended") for t in topics) and topics:
        for t in topics[: min(12, len(topics))]:
            t["recommended"] = True
    rec_ids = [t["id"] for t in topics if t.get("recommended")]
    data["topics"] = topics
    data["recommended_ids"] = rec_ids
    data["recommended_video_count"] = max(
        1, int(data.get("recommended_video_count") or len(rec_ids) or 1)
    )
    data["model"] = used
    data["at"] = time.time()
    data["chars"] = length
    data["words"] = len(raw.split())
    data["heading_hints"] = len(heads)
    _LOG.info(
        f"classified {len(topics)} topics ({len(rec_ids)} recommended) "
        f"doc_type={data.get('doc_type')} model={used}"
    )
    return data


def slice_topic_text(full_text: str, topic: dict[str, Any], *, pad: int = 400) -> str:
    """Extract the source slice for one topic, with a light pad for context."""
    text = full_text or ""
    if not text:
        return ""
    try:
        start = max(0, int(topic.get("char_start") or 0) - pad)
        end = min(len(text), int(topic.get("char_end") or len(text)) + pad)
    except Exception:
        start, end = 0, min(len(text), 8000)
    if end <= start:
        end = min(len(text), start + 6000)
    chunk = text[start:end].strip()
    name = (topic.get("name") or "Topic").strip()
    summary = (topic.get("summary") or "").strip()
    focus = topic.get("focus") or []
    focus_line = ", ".join(str(f) for f in focus[:4]) if focus else ""
    header = f"# {name}\n\n"
    if summary:
        header += f"{summary}\n\n"
    if focus_line:
        header += f"Teaching focus: {focus_line}\n\n"
    header += "---\n\nSource excerpt:\n\n"
    return header + (chunk or text[:8000])
