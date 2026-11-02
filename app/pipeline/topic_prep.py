"""Prepare rich, citable topic briefs for slide/video generation.

Uses Muse Spark (reasoning effort low) plus optional web research so
automation / Studio can author slides from a trending topic instead of a PDF.
"""
from __future__ import annotations

import json
import re
import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..logging_setup import log
from . import llm_client, llm_parse, topic_research
from .llm_client import normalize_muse_model

_LOG = log.bind(task="topic-prep")

# Topic briefs stay on Muse Spark, then Wonder if that id is rejected.
DEFAULT_LITE_MODEL = "muse-spark-1.3"
LITE_MODEL_FALLBACKS: tuple[str, ...] = (
    "muse-spark-1.3",
    "muse-wonder-1.0",
)


class Citation(BaseModel):
    title: str = ""
    url: str = ""
    source: str = ""
    snippet: str = ""


class Claim(BaseModel):
    text: str = ""
    confidence: str = "medium"  # high | medium | low | disputed
    evidence: str = ""
    citation_urls: list[str] = Field(default_factory=list)


class TopicPrepResult(BaseModel):
    model_config = {"extra": "ignore"}

    topic: str = ""
    title: str = ""
    summary: str = ""
    outline: list[str] = Field(default_factory=list)
    key_points: list[str] = Field(default_factory=list)
    narrative: str = ""
    citations: list[Citation] = Field(default_factory=list)
    claims: list[Claim] = Field(default_factory=list)
    truthfulness: str = "medium"  # overall: high | medium | low | mixed
    truthfulness_notes: str = ""
    caveats: list[str] = Field(default_factory=list)
    model: str = ""
    prepared_at: float = 0.0
    research_backends: list[str] = Field(default_factory=list)

    @field_validator("claims", mode="before")
    @classmethod
    def _coerce_claims(cls, v: Any) -> Any:
        if isinstance(v, list):
            coerced = []
            for item in v:
                if isinstance(item, str):
                    coerced.append({"text": item, "confidence": "high"})
                elif isinstance(item, dict):
                    coerced.append(item)
            return coerced
        return v

    @field_validator("citations", mode="before")
    @classmethod
    def _coerce_citations(cls, v: Any) -> Any:
        if isinstance(v, list):
            coerced = []
            for item in v:
                if isinstance(item, str):
                    coerced.append({"title": item, "url": item})
                elif isinstance(item, dict):
                    coerced.append(item)
            return coerced
        return v


def lite_model() -> str:
    s = get_settings()
    raw = (getattr(s, "muse_lite_model", None) or DEFAULT_LITE_MODEL).strip() or DEFAULT_LITE_MODEL
    return normalize_muse_model(raw)


def lite_model_candidates(primary: str | None = None) -> list[str]:
    """Ordered text-model ids to try (primary first, then fallbacks)."""
    candidates: list[str] = []
    for mid in ((primary or lite_model()).strip(), *LITE_MODEL_FALLBACKS):
        mid = normalize_muse_model((mid or "").strip())
        if mid and mid not in candidates:
            candidates.append(mid)
    return candidates


def generate_structured_lite(
    prompt: str,
    model_cls: type,
    *,
    task: str,
    want_json: bool = True,
    model: str | None = None,
    max_output_tokens: int | None = None,
):
    """Run structured generation on Muse Spark, then Muse Wonder if that id fails."""
    last_err: Exception | None = None
    primary = (model or lite_model()).strip()
    for mid in lite_model_candidates(primary):
        try:
            parsed = llm_parse.generate_structured(
                prompt,
                model_cls,
                task=task,
                want_json=want_json,
                model_name=mid,
                max_output_tokens=max_output_tokens,
            )
            if mid != primary:
                _LOG.warning(f"{task}: fell back to {mid} (primary={primary})")
            return parsed, mid
        except Exception as e:  # noqa: BLE001
            last_err = e
            msg = str(e).upper()
            retired = "404" in msg or "NOT_FOUND" in msg or "NO LONGER AVAILABLE" in msg
            if retired:
                _LOG.warning(f"{task}: lite model {mid} unavailable ({e}); trying next")
                continue
            raise
    raise last_err or RuntimeError(f"{task} failed")


def _overall_truthfulness(claims: list[Claim], notes: str) -> str:
    if not claims:
        return "medium"
    ranks = {"high": 3, "medium": 2, "low": 1, "disputed": 0}
    scores = [ranks.get((c.confidence or "medium").lower(), 2) for c in claims]
    avg = sum(scores) / max(1, len(scores))
    if any((c.confidence or "").lower() == "disputed" for c in claims):
        return "mixed"
    if avg >= 2.6:
        return "high"
    if avg >= 1.7:
        return "medium"
    return "low"


def prepare_topic(topic: str, *, model: str | None = None) -> dict[str, Any]:
    """Research + structure a topic into slide-ready content with citations."""
    topic = re.sub(r"\s+", " ", (topic or "").strip())
    if len(topic) < 3:
        raise ValueError("Topic is too short")

    model_id = (model or lite_model()).strip()
    research_block = ""
    research_meta: dict = {}
    try:
        research_block, research_meta = topic_research.research_topics(
            topic, context="Trending AI / ML explainer video for a technical YouTube audience."
        )
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"web research soft-fail for {topic!r}: {e}")
        research_block = ""
        research_meta = {"error": str(e)}

    # Supplement with a Muse web_search synthesis when MODEL_API_KEY is set.
    s = get_settings()
    if (s.model_api_key or "").strip():
        try:
            from . import llm_client
            muse_synth = llm_client.generate_text(
                f"Search the web for the AI/ML topic: '{topic}'. "
                "Synthesize a highly detailed, paper-grade research summary including exact system "
                "architecture, core mathematical formulas/algorithms, benchmarks, paper title/authors, "
                "release dates, and hardware trade-offs. Cite real URLs.",
                want_json=False,
                use_search=True,
                model=lite_model(),
            )
            if muse_synth and len(muse_synth) > 100:
                research_block = f"{research_block}\n\n### Muse web search research:\n{muse_synth}".strip()
                if isinstance(research_meta, dict):
                    backends = research_meta.setdefault("backends", [])
                    if "muse_search" not in backends:
                        backends.append("muse_search")
        except Exception as e:
            _LOG.warning(f"Muse search synthesis soft-fail for {topic!r}: {e}")

    prompt = f"""You are preparing COMPREHENSIVE PAPER-GRADE SOURCE MATERIAL for an educational AI/ML video.
Topic: {topic}

Write like a top researcher, AI engineer, and educator — concrete, highly technical, specific, with zero AI marketing fluff.
Ban terms: delve, landscape, leverage, unlock, game-changer, furthermore, robust solution, cutting-edge, embark, tapestry, "in today's world".

Use the live web research notes below. Prefer verifiable technical facts, exact architecture components, pseudocode/equations when applicable, hardware costs, and empirical metrics.
Do NOT invent papers, metrics, dates, or URLs. If unsure, mark confidence low / disputed.

Research notes:
{(research_block or "(no live research — use careful general knowledge and flag uncertainty)")[:24000]}

Return JSON matching the schema with:
- title: catchy, precise, research-grade title (e.g., "Meta Coconut: Chain of Continuous Thought via Hidden State Reasoning")
- summary: 2-3 sentence technical overview explaining the problem, core mechanism, and primary result
- outline: 8-12 slide-worthy section headings reflecting a full technical paper breakdown
- key_points: 6-10 concrete, technical bullet points (numbers, trade-offs, architectures)
- narrative: dense, paper-grade source text (1500-2500 words) formatted with clear subheadings (e.g. ## Core Motivation, ## System Architecture & Mechanics, ## Key Algorithms & Equations, ## Empirical Benchmarks & Comparisons, ## Practical Implementation & Hardware Trade-offs). Include named concepts, mathematical formulations, step-by-step algorithms, hardware/memory scaling, and concrete trade-offs with Karpathy-adjacent technical clarity.
- citations: list of citation objects: [{{"title": "title", "url": "https://...", "source": "arxiv/blog", "snippet": "snippet"}}]
- claims: list of claim objects: [{{"text": "claim text", "confidence": "high|medium|low|disputed", "evidence": "evidence text", "citation_urls": ["https://..."]}}]
- truthfulness_notes: how an editor should treat this brief (what is solid vs speculative)
- caveats: list of specific things the video must NOT overclaim
"""

    parsed, used_model = generate_structured_lite(
        prompt,
        TopicPrepResult,
        task="topic-prep",
        want_json=True,
        model=model_id,
    )

    review_prompt = f"""You are an expert AI editor and senior engineering reviewer.
Review the following prepared topic content for '{topic}' to ensure it is top-notch, highly technical, and strictly accurate.
Many recent AI topics are GitHub repos, models, or blog posts, NOT academic papers. If the draft assumes it is a paper when it is actually a repo or product, correct the framing. Ensure there is zero generic AI marketing fluff (e.g., "delve", "unlock", "game-changer").

Original Draft:
{json.dumps(parsed.dict(), indent=2)}

Return an IMPROVED version of the JSON matching the exact same schema. Fix any fluff, correct the tone to be highly technical, ensure accurate framing (e.g. repo vs paper), and enrich the narrative depth. Keep all valid citations and claims."""

    reviewed_parsed, reviewed_model = generate_structured_lite(
        review_prompt,
        TopicPrepResult,
        task="topic-prep-review",
        want_json=True,
        model=model_id,
    )
    
    parsed = reviewed_parsed
    used_model = f"{used_model} + {reviewed_model} (Review)"

    parsed.topic = topic
    parsed.model = used_model
    parsed.prepared_at = time.time()
    backends: list[str] = []
    if isinstance(research_meta, dict):
        backends.extend(research_meta.get("backends") or [])
        for b in research_meta.get("topics") or []:
            if isinstance(b, dict):
                backends.extend(b.get("backends_used") or [])
    parsed.research_backends = sorted({*backends})[:12]
    parsed.truthfulness = _overall_truthfulness(parsed.claims, parsed.truthfulness_notes)

    # Prefer research hit URLs if the model returned none.
    if not parsed.citations and isinstance(research_meta, dict):
        for brief in research_meta.get("topics") or []:
            if not isinstance(brief, dict):
                continue
            for hit in brief.get("hits") or []:
                if not isinstance(hit, dict) or not hit.get("url"):
                    continue
                parsed.citations.append(
                    Citation(
                        title=str(hit.get("title") or "")[:200],
                        url=str(hit.get("url") or ""),
                        source=str(hit.get("source") or ""),
                        snippet=str(hit.get("snippet") or "")[:280],
                    )
                )
                if len(parsed.citations) >= 8:
                    break
            if len(parsed.citations) >= 8:
                break

    return parsed.model_dump()


def brief_to_source_text(prep: dict[str, Any]) -> str:
    """Flatten a prep dict into ``extracted_text`` suitable for slide generation."""
    title = prep.get("title") or prep.get("topic") or "Topic"
    lines = [
        f"# {title}",
        "",
        prep.get("summary") or "",
        "",
        "## Outline",
    ]
    for i, item in enumerate(prep.get("outline") or [], 1):
        lines.append(f"{i}. {item}")
    lines += ["", "## Key points"]
    for kp in prep.get("key_points") or []:
        lines.append(f"- {kp}")
    lines += ["", "## Narrative", prep.get("narrative") or ""]
    claims = prep.get("claims") or []
    if claims:
        lines += ["", "## Verified claims"]
        for c in claims:
            conf = (c.get("confidence") or "medium").upper()
            lines.append(f"- [{conf}] {c.get('text') or ''}")
            if c.get("evidence"):
                lines.append(f"  Evidence: {c['evidence']}")
    cites = prep.get("citations") or []
    if cites:
        lines += ["", "## Citations"]
        for c in cites:
            lines.append(f"- {c.get('title') or c.get('url')}: {c.get('url') or ''}")
    caveats = prep.get("caveats") or []
    if caveats:
        lines += ["", "## Caveats (do not overclaim)"]
        for c in caveats:
            lines.append(f"- {c}")
    tf = prep.get("truthfulness") or "medium"
    notes = prep.get("truthfulness_notes") or ""
    lines += ["", f"## Truthfulness: {tf}", notes]
    return "\n".join(lines).strip() + "\n"


def dump_prep(path_or_text: Any) -> str:
    """Helper for debugging / API responses."""
    if isinstance(path_or_text, dict):
        return json.dumps(path_or_text, indent=2, ensure_ascii=False)
    return str(path_or_text)
