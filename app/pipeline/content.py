"""Stage 1 & 2: extract content, then build a per-slide lesson + HTML view.

Redesigned for tight audio/video sync:

* Content is modelled as a list of *slides*, each with its own ``narration``
  text, an optional flowchart, and the active step to highlight. This lets the
  media pipeline synthesize one audio clip per slide and time each video
  segment to that clip exactly (no global autoplay timer that drifts).
* A single self-contained HTML file renders ONE slide at a time, selected via
  ``?slide=N``. There is no autoplay; the capture worker drives navigation so a
  slide is only ever shown while its narration is playing.

The HTML is intentionally *designed* like a real lecture: rotating per-slide
color themes, a hero intro scene, animated numbered content cards, a device
framed diagram, a YouTube-style caption bar, and a top progress bar.
"""
from __future__ import annotations

import html
import os
import json
import re
from collections import Counter
from pathlib import Path

from . import muse_client
from ..config import get_settings
from ..logging_setup import log
from ..video_options import (
    get_video_spec, get_theme_spec, get_style_spec, DEFAULT_STORY_ARC,
    apply_auto_video_style, apply_auto_video_theme,
)


def _strip_code_fences(text: str) -> str:
    fenced = re.search(r"```(?:html|json)?\s*(.*?)```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        return fenced.group(1).strip()
    return text.strip()


def _loads_json_lenient(text: str) -> dict:
    """Parse a JSON object from a model reply, tolerating minor slop.

    Local models sometimes wrap JSON in prose or add a trailing comma. We try a
    strict parse first, then progressively repair: slice to the outermost
    ``{...}`` span and strip trailing commas. Raises ``ValueError`` only when no
    object can be recovered — the caller then retries or falls back.
    """
    if not text or not text.strip():
        raise ValueError("empty JSON response")
    try:
        return json.loads(text)
    except Exception:
        pass
    # Slice to the outermost braces (drops any leading/trailing prose).
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except Exception:
            # Remove trailing commas before } or ] which break strict JSON.
            repaired = re.sub(r",(\s*[}\]])", r"\1", candidate)
            try:
                return json.loads(repaired)
            except Exception:
                pass
    raise ValueError("no parseable JSON object in response")


def _generate_json(prompt: str, *, task: str, want_json: bool = True) -> dict:
    """Call the LLM and parse a JSON object, retrying the whole call on parse
    failures.

    ``generate_text`` already retries transport/empty errors, but a model can
    still return *non-JSON* prose (reasoning, apologies, half a fence). Those
    surface here as ``ValueError`` from :func:`_loads_json_lenient`. We retry the
    full generation a few times — on the later attempts we nudge the model to
    emit ONLY JSON — before letting the caller fall back.
    """
    attempts = max(1, int(get_settings().llm_max_retries))
    last_exc: Exception | None = None
    for i in range(attempts):
        p = prompt
        if i > 0:
            p = (
                prompt
                + "\n\nIMPORTANT: Your previous reply could not be parsed. Reply with"
                " ONLY a single valid JSON object — no markdown, no code fences, no"
                " commentary before or after."
            )
        try:
            text = _strip_code_fences(muse_client.generate_text(p, want_json=want_json))
            return _loads_json_lenient(text)
        except Exception as e:  # noqa: BLE001 - JSON parse or transport
            last_exc = e
            if i < attempts - 1:
                log.bind(task=task).warning(
                    f"JSON parse failed ({e}); retry {i + 1}/{attempts - 1}"
                )
    raise last_exc if last_exc else ValueError("no parseable JSON object in response")


# Hand-drawn title underline + corner doodles. Each path is ``pathLength=1`` so the
# frame timeline can "draw" it (stroke-dashoffset driven by --p).
_H_UNDER = (
    '<svg class="h-under" viewBox="0 0 360 18" preserveAspectRatio="none" aria-hidden="true">'
    '<path class="draw" pathLength="1" d="M3 11 C 50 3, 90 16, 140 8 S 230 4, 280 11 S 340 12, 357 6"/></svg>'
)
_COVER_ART = '<div class="cover-art" aria-hidden="true"></div>'
_DECOS = (
    '<div class="decos" aria-hidden="true">'
    '<svg class="deco d1" viewBox="0 0 100 100"><path class="draw" pathLength="1" '
    'd="M50 8 L60 38 L92 40 L66 58 L76 90 L50 72 L24 90 L34 58 L8 40 L40 38 Z"/></svg>'
    '<svg class="deco d2" viewBox="0 0 100 100"><path class="draw" pathLength="1" '
    'd="M10 72 C 20 10, 84 10, 82 50 C 80 84, 40 82, 46 56 C 50 40, 70 40, 72 52"/>'
    '<path class="draw" pathLength="1" d="M64 44 L72 54 L82 46"/></svg>'
    '<svg class="deco d3" viewBox="0 0 100 100"><path class="draw" pathLength="1" '
    'd="M50 8 C 85 6, 96 40, 88 66 C 78 94, 30 98, 14 70 C 2 48, 14 14, 52 12 C 70 10, 84 22, 86 30"/></svg>'
    '</div>'
)

# Design families live in edu_theme (shared with the style picker).
from .edu_theme import (  # noqa: E402
    EDU_FAMILIES as _EDU_FAMILIES,
    EDU_FAMILY_MAP as _EDU_FAMILY_MAP,
    edu_family as _edu_family,
)


def _accent_heading(heading: str) -> str:
    """Wrap the last word (or two, if the last is short) of a heading in an
    accent span so it renders tinted with the slide's accent color — matching
    the reference style ("Alternatives exist. They're islands.")."""
    if not heading:
        return heading
    parts = heading.split()
    if len(parts) <= 1:
        return f'<span class="accent">{heading}</span>'
    # Tint the last word; if it's very short, include the word before it too.
    n = 2 if len(parts) >= 3 and len(parts[-1]) <= 4 else 1
    head = " ".join(parts[:-n])
    tail = " ".join(parts[-n:])
    return f'{head} <span class="accent">{tail}</span>'


# --------------------------------------------------------------- slide model ----

SLIDES_PROMPT = """You are an expert instructional designer and explainer-video director.
Turn the educational content below into a RICH, concept-first narrated slideshow
as JSON. Viewers should understand WHY each idea matters, HOW it works, and
WHERE it fits — not skim a bullet dump.

Return ONLY a JSON object (no markdown, no code fences) of this exact shape:
{{
  "title": "Video title",
  "flowchart": "flowchart TD\\n  A[Start] --> B[Step 1]\\n  B --> C[Step 2]\\n  C --> D[Done]",
  "slides": [
    {{
      "layout": "bullets",
      "heading": "Short slide heading",
      "bullets": ["concise point", "another point"],
      "narration": "Spoken lines for THIS slide only (~{words_per_slide} words). A person explaining it, with pauses and a change of pace. Not a lesson and not a promo.",
      "equations": [{{"label": "Energy", "tex": "E = mc^2"}}],
      "show_flowchart": true,
      "active_node": "B",
      "stats": [{{"value": "98%", "label": "accuracy"}}],
      "compare": {{"left_title": "Before", "left": ["..."], "right_title": "After", "right": ["..."]}},
      "steps": ["first do this", "then this", "finally this"],
      "quote": "A single memorable sentence to emphasise.",
      "hub": {{"center": "your work", "subtitle": "survives any model", "footer": "one line takeaway", "nodes": [{{"label": "a standard", "sub": "CLAUDE.md"}}, {{"label": "a roadmap", "sub": "ranked plan"}}]}},
      "panel": {{"title": "Project · your-business", "subtitle": "PROJECT INSTRUCTIONS", "badge": "Opus 4.8", "lines": ["# heading line", "a plain code/config line", "another line"]}},
      "transform": {{"from_title": "A 40-PAGE REPORT", "from_note": "read once · buried", "to_center": "niche", "to_nodes": ["ICP", "churn", "pricing", "gaps", "offers"], "footer": "the vault becomes the context"}},
      "flow": {{"orientation": "horizontal", "steps": [{{"label": "Ingest", "sub": "raw docs"}}, {{"label": "Embed", "sub": "vectors"}}, {{"label": "Retrieve", "sub": "top-k"}}, {{"label": "Answer", "sub": "grounded"}}]}},
      "hook": {{"value": "$121K", "label": "weekend bill", "punchline": "There's a backend that structurally can't do that to you."}},
      "bars": {{"title": "What you pay for", "items": [{{"label": "Metered cloud", "value": "92", "note": "reads · writes · seats"}}, {{"label": "Flat VPS", "value": "18", "note": "$5 / month"}}]}},
      "matrix": {{"items": [{{"label": "Claim", "detail": "what it asserts"}}, {{"label": "Evidence", "detail": "how we know"}}, {{"label": "Trade-off", "detail": "cost or limit"}}, {{"label": "Takeaway", "detail": "what to do"}}]}}
    }}
  ]
}}

HOW TO WRITE (every slide):
- FILL THE CARD. The layout you pick must contain real words from the source.
  A heading with an empty body is a failed slide. matrix items need both a
  short label AND a detail clause of 8–16 words. flow steps need a label AND
  a sub clause. stat cards need a number AND a label that says what it measures.
  compare sides need 2–3 concrete points each. If you cannot fill a field,
  do not use that layout — use bullets and fill every bullet.
- Use Muse's strength: read the source, keep the facts, and say the mechanism
  in plain language. Do not invent numbers. Do not leave placeholder text
  ("...", "TBD", "detail here").
- Not a lesson plan and not a content-marketing deck. No "today we will learn",
  no "key takeaways", no "let's dive in", no classroom voice.
- Say the thing. A concrete case, the mechanism, the catch. Short labels on
  screen. The narration is one person talking to one person, not a teacher
  to a class and not a brand video.
- On-screen lines stay short enough to fit the card (about 8 words). Depth
  goes in the narration. 3–5 items when the layout has room, never a wall of text.
- Narration has a pulse: a pause, a question, a change of pace. No textbook
  cadence and no hype.
- ANIMATION-READY: multi-item layouts (flow, steps, hub, bars, compare, stat)
  animate item-by-item in sync with the voice. Put items in the SAME ORDER the
  narration explains them so highlights feel intentional.
- FAITHFUL: invent no results, numbers, or citations. Use only what the source
  supports (or clearly mark as general intuition when teaching).

LAYOUT MENU — pick the BEST layout per slide from the full variety pack (up to
~20 distinct visual beats across a long video). Do NOT reuse the same layout on
consecutive slides. Prefer rich animated layouts over a string of bullets.
Only include the field that matches the chosen layout:
  * "hook"      -> kinetic cold-open number. Fill "hook" with
    {{value, label, punchline}}. Prefer slide 1 when there is a striking cost,
    scale, risk, or result.
  * "bars"      -> animated magnitude bars. Fill "bars" with
    {{title, items:[{{label, value (0-100), note}}]}} (2-5 items). Pricing,
    scale, effort, share-of-attention.
  * "bullets"   -> 3-4 short takeaways (each a concrete fact/mechanism/example).
  * "stat"      -> 1-3 big metrics {{value,label}} (results, benchmarks, sizes).
  * "compare"   -> two sides; left/right titles + 2-4 points each (old vs new,
    approach A vs B, myth vs reality). Also use for do/don't pitfalls.
  * "steps"     -> 3-6 ordered actions / timeline beats the viewer can follow.
  * "quote"     -> ONE pivotal insight sentence in "quote".
  * "hub"       -> one center concept + 3-7 satellite nodes {{label, sub}}.
    Parts of a system, facets of an idea, "the N pillars".
  * "panel"     -> terminal/code/config mock: title, subtitle, optional badge,
    "lines" of short commands/config. Great for APIs, prompts, CLI, schemas.
  * "transform" -> messy/raw "from" becomes clean "to" structure (from_title,
    from_note, to_center, to_nodes, footer).
  * "flow"      -> linked pipeline with arrows. orientation "horizontal" (2-4)
    or "vertical" (3-6); steps [{{label, sub}}]. Use whenever stages are
    causal/sequential so the video SHOWS linkage, not just a list.
  * "matrix"    -> 2×2 or 2×3 articulated cards. Fill "matrix" with
    {{items:[{{label, detail}}]}} (3–4 items). Use for claim/evidence,
    components, trade-offs, checklist facets — denser than bullets, still
    scannable. Prefer this when the source has several parallel facts.
  * "bento"     -> 3–5 tiles (first tile is the hero). Geometry change, not a
    color swap. Fill "bullets" with short tile labels.
  * "cards"     -> 2–5 stacked cards from "bullets" (offset deck, not a list).
  * "rail"      -> 3–5 numbered stations on a path from "bullets" or "steps".
  * "spotlight" -> one lead line + supporting chips. Use for a single insight
    with 1–3 supporting facts in "bullets".
  * "diagram"   -> process map; set show_flowchart true + active_node.
  * "cover"     -> ONLY when instructed for research papers/books (first page).
SMART FIT: match slide LAYOUT to content — numbers→hook/stat/bars; systems→hub/flow;
trade-offs→compare/matrix; how-to→steps/rail; tiles→bento/cards; insight→quote/spotlight;
code→panel; cleanup→transform. Rotate through the menu so a 10–20 slide lesson uses
many GEOMETRIES (bento vs rail vs split vs stack) — not the same cards recolored.
DATA FIT: for a "bullets" slide you may add "weights": one 0-100 importance score per
bullet (same order). The layout engine sizes each item's area from it (bigger = more
important) and computes a unique geometry for that slide — you never pick a template.
Do NOT invent or swap the presentation visual style, color theme, or voice —
those are locked by Studio / the user.

FORMAT TARGET ({format_label} / {platform} · {aspect_ratio}):
{format_guidance}
Style template cue: {style_template}

STORY ARC ({style_label} — follow this structure closely):
{story_arc}
Produce EXACTLY {slide_count} slides (not fewer) so runtime hits ~{target_minutes}.
FIRST: cold-open hook (or cover when required) unless the style arc says
otherwise. LAST: a crisp recap / takeaways slide unless the style is a pure
short hook. Prefer flow/steps/matrix for sequential or multi-facet ideas;
reserve diagram for genuine process maps.

FLOWCHART: one Mermaid `flowchart TD` of the whole process (ids A,B,C…;
short labels). Highlight via active_node on diagram slides only.

NARRATION (spoken aloud — no markup, no emojis, no stage directions):
- {words_per_slide_min}–{words_per_slide_max} words per slide (target
  ~{words_per_slide}). TOTAL across all slides ≈ {total_words} words
  (~{target_minutes} at a calm pace). Do NOT exceed the max.
- Explain THIS slide's concept clearly: intuition → mechanism → takeaway.
  Tie each spoken beat to an on-screen item in order (first sentence ≈ first
  bullet/step/node) so animation highlights feel synced.
- HUMANIZE the voice: sound like a real person teaching on camera — warm,
  clear, slightly imperfect rhythm. Use contractions (it's, you'll, don't),
  short asides ("here's the twist", "watch this part"), and one concrete
  micro-example when it helps. Prefer "you" / "we" over "one" / "the user".
- Vary sentence length. Start some slides mid-thought ("So the trick is…").
  End teaching slides with a crisp "so what" line the viewer can repeat.
- Never corporate-AI, brochure, or textbook-lecture tone. Never stack three
  abstract nouns ("scalability resilience architecture").
- Ban AI-slop words: delve, landscape, leverage, unlock, game-changer,
  furthermore, moreover, robust solution, cutting-edge, embark, tapestry,
  pivotal, nuanced, holistic, seamless, empower.
- Do NOT read bullets verbatim. Do NOT say "lesson", "welcome back",
  "in this video", or "as we can see from the slide".
- Title/recap slides shorter; teaching slides denser. No filler or padding.

ON-SCREEN COPY (what the HTML slideshow shows — must feel human, not a dump):
- Headings: punchy, specific, spoken-aloud friendly (not "Overview" /
  "Introduction" / "Key Points" unless truly needed). Prefer a claim or question.
- Bullets/steps/nodes: ultra-short labels packed with meaning; each item
  distinct. Prefer concrete nouns/verbs ("cache miss", "retry once") over
  vague adjectives ("important", "better", "efficient").
- Caption-ready phrasing: labels should make sense if read alone under the
  visual. No orphan jargon without a tiny context word.
- Never marketing fluff, never wall-of-text paragraphs on the board.

ON-SCREEN FIT (critical — overcrowding / overlap is a failure):
- Cap density: ≤4 bullets, ≤4 matrix cells, ≤5 hub nodes, ≤4 flow steps,
  ≤4 transform chips, ≤4 compare items per side, ≤5 steps.
- Labels ≤ ~6 words; card details ≤ one short line. Leave ≥16px breathing room.
- One idea per slide. Prefer splitting content across two slides over cramming.
- Choose the RIGHT rich layout (flow/hub/compare/stat/panel/bars/matrix) —
  fill with structure, not with more text. Empty space beats overlapping text.

MATH: preserve real LaTeX in "equations" as {{"label","tex"}} (tex WITHOUT $).
Inline math in bullets/headings with $...$. Narration says formulas in words.
Use \\\\lt / \\\\gt instead of < / > inside math.
{structure_block}{analysis_block}{extra_topics_block}
Educational content:
---
{content}
---
"""


_ANALYZE_PROMPT = """You are analysing a source document to plan a RICH concept-explainer video.
Read the content and reply with ONLY a JSON object of this exact shape:
{{
  "title": "a concise, engaging title for the video (specific, not generic)",
  "doc_type": "one of: research paper, book, tutorial, slide deck, manual, article, plan, notes, other",
  "subject": "the domain/topic in a few words",
  "audience": "who this is for, e.g. beginners, practitioners, students",
  "tone": "the teaching tone that fits, e.g. academic, practical, friendly",
  "authors": "comma-separated author/editor names if present, else empty string (for metadata only — do not force onto slides)",
  "institution": "university, lab, company, or org if present, else empty string",
  "source_title": "the document's own title if present (paper/book title), else empty",
  "venue_or_year": "publication venue, journal, edition, or year if present, else empty",
  "is_ml_topic": true,
  "summary": "a 2-3 sentence plain-English summary of what the document is about",
  "key_points": ["4-7 of the most important CONCEPTS to teach — mechanisms and ideas, not section titles"],
  "key_equations": ["the document's most important formulas as LaTeX (no $), e.g. \\\\theta_{{t+1}} = \\\\theta_t - \\\\eta \\\\nabla L; empty list if the document has no math"],
  "teaching_angle": "2 sentences: the best analogy/intuition for the core idea, plus which slide LAYOUTS (flow/compare/hub/bars) will teach it best — NOT a color theme or brand look",
  "hook_idea": "one striking number, tension, or question to open the video (or empty if none in source)"
}}
Set "is_ml_topic" true ONLY if the document is about machine learning, deep
learning, neural networks, transformers, LLMs, backprop, or closely related AI.
Prefer key_points that are teachable mechanisms ("how attention routes information")
over vague themes ("background", "related work").
When the source includes "Figure:" blocks from image understanding, treat those as
first-class content (diagrams, charts, flows) for key_points and teaching_angle —
use them for LAYOUT ideas only, never for color/theme/voice.
Do NOT recommend a presentation visual style, color palette, or voice —
Studio defaults already lock those. Only analyse the document's content.
Content:
---
{content}
---
"""


def _normalize_doc_type(raw: str) -> str:
    """Map messy LLM / heuristic labels onto the canonical doc_type set."""
    t = re.sub(r"\s+", " ", (raw or "").strip().lower())
    aliases = {
        "paper": "research paper",
        "research": "research paper",
        "scientific paper": "research paper",
        "academic paper": "research paper",
        "journal article": "research paper",
        "arxiv": "research paper",
        "pdf paper": "research paper",
        "textbook": "book",
        "ebook": "book",
        "slides": "slide deck",
        "presentation": "slide deck",
        "deck": "slide deck",
        "howto": "tutorial",
        "how-to": "tutorial",
        "guide": "tutorial",
        "documentation": "manual",
        "docs": "manual",
        "readme": "manual",
        "blog": "article",
        "blog post": "article",
        "essay": "article",
        "meeting notes": "notes",
        "memo": "notes",
        "document": "other",
        "unknown": "other",
    }
    if t in aliases:
        return aliases[t]
    allowed = {
        "research paper", "book", "tutorial", "slide deck", "manual",
        "article", "plan", "notes", "other",
    }
    if t in allowed:
        return t
    # Match whole tokens only — never substring ("book" must not match "notebook").
    for a in sorted(allowed, key=len, reverse=True):
        if re.search(rf"(?<![\w-]){re.escape(a)}(?![\w-])", t):
            return a
    return "other"


def _heuristic_doc_type(text: str) -> str:
    """Classify the input without an LLM (Abstract/DOI/arXiv → research paper)."""
    head = (text or "")[:8000]
    low = head.lower()
    # Research-paper signals (strong).
    paper_hits = 0
    for pat in (
        r"\babstract\b", r"\barxiv\b", r"\bdoi\s*:", r"\bdoi\.org\b",
        r"\breferences\b", r"\bbibliography\b", r"\bintroduction\b",
        r"\brelated work\b", r"\bmethodology\b", r"\bexperiment",
        r"\bconclusion\b", r"\bkeywords\b", r"\bproceedings\b",
        r"\bjournal\b", r"\bieee\b", r"\bacl\b", r"\bnips\b", r"\bicml\b",
        r"\bcitation\b", r"\[\d+\]",
    ):
        if re.search(pat, low):
            paper_hits += 1
    if paper_hits >= 3 or ("abstract" in low and ("references" in low or "arxiv" in low)):
        return "research paper"
    if re.search(r"\b(chapter\s+\d+|table of contents|isbn)\b", low):
        return "book"
    if re.search(r"\b(slide\s+\d+|agenda|presented by)\b", low):
        return "slide deck"
    if re.search(r"\b(step\s+\d+|how to|tutorial|walkthrough|getting started)\b", low):
        return "tutorial"
    if re.search(r"\b(api reference|configuration|installation|man page)\b", low):
        return "manual"
    if re.search(r"\b(project plan|roadmap|milestone|okr)\b", low):
        return "plan"
    if len(head.split()) < 120:
        return "notes"
    return "article" if paper_hits >= 1 else "other"


def analyze_document(raw_text: str) -> dict:
    """Ask the LLM to classify the document so the slide prompt can adapt.

    Returns a dict of analysis fields. Falls back to a light heuristic when no
    LLM is available or the call fails, so generation never blocks on this.
    """
    snippet = (raw_text or "").strip()[:6000]
    from ..capabilities import llm_available

    heuristic_type = _heuristic_doc_type(snippet)
    if snippet and llm_available():
        try:
            data = _generate_json(
                _ANALYZE_PROMPT.format(content=snippet), task="analyze"
            )
            if isinstance(data, dict) and (data.get("subject") or data.get("doc_type")):
                data["doc_type"] = _normalize_doc_type(
                    str(data.get("doc_type") or heuristic_type)
                )
                # Heuristic wins when the LLM says "other/notes" but the PDF
                # clearly looks like a research paper (Abstract + References…).
                if heuristic_type == "research paper" and data["doc_type"] in {
                    "other", "notes", "article",
                }:
                    data["doc_type"] = "research paper"
                data["classifier"] = "llm+heuristic"
                log.bind(task="analyze").info(
                    f"doc_type={data.get('doc_type')} subject={data.get('subject')} "
                    f"audience={data.get('audience')}"
                )
                return data
        except Exception as e:
            log.bind(task="analyze").warning(f"doc analysis failed ({e}); using heuristic")
    # Heuristic fallback.
    first = next((ln.strip() for ln in snippet.splitlines() if ln.strip()), "Overview")
    return {
        "title": first[:90],
        "doc_type": heuristic_type,
        "subject": first[:60],
        "audience": "general learners",
        "tone": "clear and practical",
        "authors": "",
        "institution": "",
        "source_title": first[:120],
        "venue_or_year": "",
        "is_ml_topic": False,
        "summary": "",
        "key_points": [],
        "teaching_angle": "Explain the material step by step with concrete examples.",
        "classifier": "heuristic",
    }


# Doc types that benefit from a "cover" intro: show the source, who wrote it,
# and a summary before teaching the content.
_COVER_DOC_TYPES = {"research paper", "book", "plan", "manual", "article"}


def wants_cover_image(doc_type: str) -> bool:
    """True when the opening slide should show the document's first page."""
    return _normalize_doc_type(doc_type) in _COVER_DOC_TYPES


def _apply_cover_slide(
    model: dict, analysis: dict | None, cover_image: str | None
) -> dict:
    """Force slide 1 to a paper-cover layout when the source warrants it.

    Research papers / books get a dedicated ``cover`` layout so a rich hook/stat
    opener cannot hide the first-page image. Tutorials/notes leave slide 1 alone.
    """
    if not cover_image or not model.get("slides"):
        return model
    doc_type = _normalize_doc_type(str((analysis or {}).get("doc_type", "")))
    if not wants_cover_image(doc_type):
        return model
    sl0 = dict(model["slides"][0])
    sl0["layout"] = "cover"
    sl0["image"] = cover_image
    sl0["image_caption"] = (
        (analysis or {}).get("source_title")
        or (analysis or {}).get("title")
        or model.get("title", "")
    )
    # Keep a short on-screen blurb; strip competing rich layouts.
    for k in ("hook", "bars", "stats", "compare", "steps", "quote",
              "hub", "panel", "transform", "flow"):
        sl0.pop(k, None)
    if not sl0.get("bullets"):
        summary = str((analysis or {}).get("summary") or "").strip()
        if summary:
            sl0["bullets"] = [summary[:180]]
        elif (analysis or {}).get("key_points"):
            sl0["bullets"] = [str(p)[:120] for p in (analysis["key_points"][:3])]
    model["slides"][0] = sl0
    model["doc_type"] = doc_type
    log.bind(task="generate").info(
        f"cover slide applied (doc_type={doc_type}, image={cover_image})"
    )
    return model


def _is_ml(analysis: dict) -> bool:
    if analysis.get("is_ml_topic"):
        return True
    blob = " ".join(
        str(analysis.get(k, "")) for k in ("subject", "title", "source_title", "teaching_angle")
    ).lower()
    ml_terms = (
        "machine learning", "deep learning", "neural network", "transformer",
        "backprop", "gradient descent", "llm", "language model", "attention",
        "convolution", "reinforcement learning", "embedding", "fine-tun",
    )
    return any(t in blob for t in ml_terms)


def _structure_block(analysis: dict | None, has_cover_image: bool) -> str:
    """Tell the LLM how to *structure* the opening slides based on doc type.

    For papers/books/plans we want a documentary-style opening: a cover slide,
    a source/institution slide, then a summary slide, then the actual teaching.
    Prefer institution/venue over listing author names.
    """
    if not analysis:
        return ""
    doc_type = str(analysis.get("doc_type", "")).lower()
    lines: list[str] = []
    if wants_cover_image(doc_type):
        src = analysis.get("source_title") or analysis.get("title")
        institution = (analysis.get("institution") or "").strip()
        venue = (analysis.get("venue_or_year") or "").strip()
        context_bits = [b for b in (institution, venue) if b]
        context = " · ".join(context_bits)
        lines.append(
            f"- This is a {doc_type}. Open like a documentary about it:\n"
            f'  * Slide 1 MUST use layout "cover"'
            + (f' for "{src}"' if src else "")
            + (f" ({context})" if context else "")
            + (". The first page of the document is shown as a large image on this slide."
               if has_cover_image else ".")
            + " Narrate what the document is and why it matters. Do NOT use hook/stat/bars on slide 1.\n"
            "  * Slide 2: source context — institution, lab/org, and venue/year if known"
            + (f" — {context}." if context else ".")
            + " Do NOT recite author name lists; institution/venue is enough credit.\n"
            "  * Slide 3: a clear plain-English SUMMARY of the whole document.\n"
            "  * Remaining slides: teach the actual content/methods/results step by step.\n"
        )
    else:
        lines.append(
            f"- This is a {doc_type or 'document'} (not a research paper/book). "
            "Do NOT invent a paper-cover page image. Open with a kinetic hook "
            "(layout hook/stat/quote), then teach concepts with varied rich layouts "
            "(flow, hub, compare, bars, panel) — not a string of bullet slides.\n"
        )
    hook = (analysis.get("hook_idea") or "").strip()
    if hook and not wants_cover_image(doc_type):
        lines.append(
            f'- Opening hook idea from analysis: "{hook}". Use it on slide 1 '
            "(hook/stat/quote) if it is faithful to the source.\n"
        )
    key_points = analysis.get("key_points") or []
    if key_points:
        pts = "; ".join(str(p)[:80] for p in key_points[:7])
        lines.append(
            f"- Core concepts to cover (map each to its own visual slide when possible): {pts}.\n"
            "  Prefer one concept per teaching slide with a matching animated layout.\n"
        )
    angle = (analysis.get("teaching_angle") or "").strip()
    if angle:
        lines.append(f"- Teaching angle: {angle}\n")
    if _is_ml(analysis):
        lines.append(
            "- This is a machine-learning topic. Explain concepts the way Andrej"
            " Karpathy teaches: intuition + tiny concrete examples BEFORE formalism"
            " (gradients as 'which knob to turn', a neuron as a weighted vote,"
            " attention as tokens looking at each other, training as nudging weights"
            " to reduce loss). Use flow for pipelines, hub for architecture parts,"
            " compare for baselines vs proposed, panel for equations/code sketches."
            " Stay faithful to the document — do not invent results.\n"
        )
    return "".join(lines)


def _analysis_block(analysis: dict | None) -> str:
    if not analysis:
        return ""
    kp = analysis.get("key_points") or []
    kp_txt = ("; ".join(str(k) for k in kp))[:700]
    summary = str(analysis.get("summary") or "")[:600]
    keq = analysis.get("key_equations") or []
    keq_txt = ("  ||  ".join(str(k) for k in keq if str(k).strip()))[:600]
    hook = str(analysis.get("hook_idea") or "").strip()[:220]
    return (
        "Document analysis (adapt wording, slide layouts, and examples only — "
        "do NOT change visual style, color theme, or voice):\n"
        f"- Type: {analysis.get('doc_type', 'document')}\n"
        f"- Subject: {analysis.get('subject', '')}\n"
        f"- Audience: {analysis.get('audience', 'general learners')}\n"
        f"- Tone to use: {analysis.get('tone', 'clear and practical')}\n"
        f"- Teaching angle: {analysis.get('teaching_angle', '')}\n"
        + (f"- Opening hook idea: {hook}\n" if hook else "")
        + (f"- Source: {analysis.get('source_title')}\n" if analysis.get("source_title") else "")
        + (
            f"- Institution / org: {analysis.get('institution')}\n"
            if analysis.get("institution") else ""
        )
        + (
            f"- Venue / year: {analysis.get('venue_or_year')}\n"
            if analysis.get("venue_or_year") else ""
        )
        + (
            "- Credit on slides/narration: prefer institution + venue. "
            "Do not list author names unless the work is famously one person "
            "and institution is unknown.\n"
        )
        + (f"- Summary: {summary}\n" if summary else "")
        + (
            f"- Emphasise these CONCEPTS (prefer one rich animated layout each): {kp_txt}\n"
            if kp_txt else ""
        )
        + (
            f"- Key formulas to show as LaTeX equations on the relevant slides: {keq_txt}\n"
            if keq_txt else ""
        )
        + "- Prefer varied visual layouts that animate well (flow/hub/compare/bars/"
        "steps/panel) over consecutive bullet-only slides.\n"
        "- Keep each slide scannable: short labels, breathing room, no overlapping text.\n"
    )


def _clean_tex(tex: str) -> str:
    """Normalise LLM-supplied LaTeX so KaTeX renders it reliably.

    Strips surrounding math delimiters ($…$, \\(…\\), \\[…\\]) and code fences
    the model sometimes adds, unescapes doubled backslashes from JSON round-trips
    only when clearly over-escaped, and rejects empty/broken fragments.
    """
    t = (tex or "").strip()
    if not t:
        return ""
    t = t.replace("```latex", "").replace("```math", "").replace("```", "").strip()
    # Peel one layer of surrounding delimiters if the model included them.
    for lo, hi in (("$$", "$$"), ("\\[", "\\]"), ("\\(", "\\)"), ("$", "$")):
        if t.startswith(lo) and t.endswith(hi) and len(t) > len(lo) + len(hi):
            t = t[len(lo): len(t) - len(hi)].strip()
            break
    # Keep authors from crashing KaTeX with raw angle brackets.
    t = t.replace("<", " \\lt ").replace(">", " \\gt ")
    return t.strip()[:400]


def _sanitize_mermaid(diagram: str) -> str:
    """Best-effort cleanup so LLM-generated Mermaid parses reliably.

    Common breakages we guard against:
    - Code fences / stray backticks left in the string.
    - Square-bracket node labels containing characters Mermaid mis-parses
      (quotes, nested brackets, pipes, ``&``) — we wrap the label in quotes and
      neutralize the offending characters, e.g. ``A[Do (x) & y]`` -> ``A["Do (x) and y"]``.
    - Missing ``flowchart``/``graph`` header.
    """
    text = (diagram or "").replace("```mermaid", "").replace("```", "").strip()
    if not text:
        return ""
    text = text.replace("\\n", "\n")

    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if not lines:
        return ""
    head = lines[0].strip().lower()
    if not (head.startswith("flowchart") or head.startswith("graph")):
        lines.insert(0, "flowchart TD")

    # Quote square-bracket labels:  id[ ... ]  ->  id["..."].
    # We match the LAST ']' on the segment so labels with inner ')' survive,
    # then sanitize characters that break Mermaid inside quoted labels.
    label_re = re.compile(r"(\b[A-Za-z][\w]*)\[([^\[\]]*)\]")

    def _fix(m: re.Match) -> str:
        node_id, label = m.group(1), m.group(2)
        label = label.strip().strip('"').strip("'")
        label = label.replace('"', "").replace("|", "/").replace("&", "and")
        return f'{node_id}["{label}"]'

    fixed = [label_re.sub(_fix, ln) for ln in lines]
    return "\n".join(fixed)


def _delesson(text: str) -> str:
    """Remove 'lesson' wording from on-screen or spoken slide copy."""
    t = (text or "").strip()
    if not t:
        return t
    repl = (
        (r"\bin this lesson\b", "here"),
        (r"\bthis lesson\b", "this"),
        (r"\bthe lesson\b", "the topic"),
        (r"\boverview of the lesson\b", "overview"),
        (r"\blesson\b", ""),
    )
    for pat, sub in repl:
        t = re.sub(pat, sub, t, flags=re.I)
    return re.sub(r"\s{2,}", " ", t).strip(" -:,")


def _coerce_weights(raw, n: int) -> list[float]:
    """Optional per-bullet importance (0-100) that sizes cells in the layout."""
    if not isinstance(raw, list) or n <= 0:
        return []
    out: list[float] = []
    for v in raw[:n]:
        try:
            out.append(max(0.0, min(100.0, float(v))))
        except (TypeError, ValueError):
            return []
    if len(out) != n or max(out) <= 0:
        return []
    hi = max(out)
    # map importance to the synthesizer's 1.0-3.0 area weight
    return [round(1.0 + 2.0 * (v / hi), 2) for v in out]


def _spoken_bits(narration: str) -> list[str]:
    """Sentences and clauses we can drop into an empty card."""
    text = re.sub(r"\s+", " ", (narration or "").strip())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+|(?:\s+[—–-]\s+)", text)
    bits = []
    for part in parts:
        words = part.strip(" .").split()
        if len(words) >= 4:
            bits.append(" ".join(words))
    return bits


def _clip_words(text: str, n: int) -> str:
    words = (text or "").split()
    return " ".join(words[:n]).strip(" .")


def _fill_slide_copy(slide: dict) -> None:
    """Put spoken lines onto cards the model left blank.

    A layout with a title and no body reads as an empty template. The
    narration already has the facts, so use it to fill missing labels.
    """
    bits = _spoken_bits(str(slide.get("narration") or ""))
    if not bits:
        return
    layout = slide.get("layout") or ""
    if layout == "matrix" and isinstance(slide.get("matrix"), dict):
        items = slide["matrix"].get("items") or []
        for i, item in enumerate(items):
            if isinstance(item, dict) and not str(item.get("detail") or "").strip() and i < len(bits):
                item["detail"] = _clip_words(bits[i], 18)
        if len(items) < 3:
            made = []
            for bit in bits[:4]:
                words = bit.split()
                made.append({"label": " ".join(words[:4]), "detail": _clip_words(bit, 18)})
            if len(made) >= 3:
                slide["matrix"] = {"items": made}
    elif layout == "transform" and isinstance(slide.get("transform"), dict):
        tr = slide["transform"]
        nodes = [str(n).strip() for n in (tr.get("to_nodes") or []) if len(str(n).strip()) > 2]
        if len(nodes) < 2:
            nodes = [_clip_words(b, 5) for b in bits[:4]]
        tr["to_nodes"] = nodes[:4]
        if not str(tr.get("footer") or "").strip() and bits:
            tr["footer"] = _clip_words(bits[0], 16)
        if not str(tr.get("from_note") or "").strip() and len(bits) > 1:
            tr["from_note"] = _clip_words(bits[1], 8)
    elif layout == "flow" and isinstance(slide.get("flow"), dict):
        steps = slide["flow"].get("steps") or []
        for i, step in enumerate(steps):
            if isinstance(step, dict) and not str(step.get("sub") or "").strip() and i < len(bits):
                step["sub"] = _clip_words(bits[i], 10)
    elif layout == "stat":
        stats = slide.get("stats") or []
        for i, stat in enumerate(stats):
            if isinstance(stat, dict) and not str(stat.get("label") or "").strip() and i < len(bits):
                stat["label"] = _clip_words(bits[i], 8)
    elif layout == "compare" and isinstance(slide.get("compare"), dict):
        cmp = slide["compare"]
        if not cmp.get("left") and not cmp.get("right") and len(bits) >= 2:
            mid = max(1, len(bits) // 2)
            cmp["left"] = [_clip_words(b, 10) for b in bits[:mid]][:3]
            cmp["right"] = [_clip_words(b, 10) for b in bits[mid:]][:3]
    elif layout in {"bullets", "bento", "cards", "rail", "spotlight"} and not slide.get("bullets"):
        slide["bullets"] = [_clip_words(b, 10) for b in bits[:4]]
    elif layout == "steps" and not slide.get("steps"):
        slide["steps"] = [_clip_words(b, 10) for b in bits[:4]]
    elif layout == "quote" and not str(slide.get("quote") or "").strip():
        slide["quote"] = bits[0][:220]


def _coerce_slides(data: dict) -> dict:
    """Validate/normalize the model's JSON into our slide model."""
    title = _delesson(str(data.get("title") or "Overview").strip()[:120])
    flowchart = _sanitize_mermaid(str(data.get("flowchart") or ""))
    valid_nodes = set(re.findall(r"(?m)^\s*([A-Za-z][\w]*)", flowchart))
    raw_slides = data.get("slides") or []
    slides = []
    for s in raw_slides:
        if isinstance(s, str):
            s = {"heading": s[:80], "narration": s}
        elif not isinstance(s, dict):
            continue
        narration = _delesson(str(s.get("narration") or "").strip())
        heading = _delesson(str(s.get("heading") or "").strip()[:120])
        bullets = [_delesson(str(b).strip()[:140]) for b in (s.get("bullets") or []) if str(b).strip()][:6]
        show_fc = bool(s.get("show_flowchart")) and bool(flowchart)
        active = s.get("active_node")
        active = str(active).strip() if active else None
        # Drop highlight references to nodes that don't exist in the diagram.
        if active and valid_nodes and active not in valid_nodes:
            active = None

        # ---- rich layout fields -------------------------------------------
        layout = str(s.get("layout") or "").strip().lower()

        stats = []
        for st in (s.get("stats") or [])[:3]:
            if isinstance(st, dict) and (st.get("value") or st.get("label")):
                stats.append({
                    "value": _delesson(str(st.get("value") or "").strip()[:18]),
                    "label": _delesson(str(st.get("label") or "").strip()[:60]),
                })

        compare = None
        cmp_raw = s.get("compare")
        if isinstance(cmp_raw, dict):
            left = [_delesson(str(x).strip()[:100]) for x in (cmp_raw.get("left") or []) if str(x).strip()][:4]
            right = [_delesson(str(x).strip()[:100]) for x in (cmp_raw.get("right") or []) if str(x).strip()][:4]
            if left or right:
                compare = {
                    "left_title": _delesson(str(cmp_raw.get("left_title") or "A").strip()[:40]),
                    "right_title": _delesson(str(cmp_raw.get("right_title") or "B").strip()[:40]),
                    "left": left,
                    "right": right,
                }

        steps = [_delesson(str(x).strip()[:120]) for x in (s.get("steps") or []) if str(x).strip()][:5]
        quote = _delesson(str(s.get("quote") or "").strip()[:260])

        # ---- LaTeX equations (rendered with KaTeX) ------------------------
        # Never run these through _delesson/escaping mangling — keep the raw
        # TeX so KaTeX typesets it exactly. Accept {label, tex} or bare strings.
        equations = []
        for eq in (s.get("equations") or [])[:4]:
            if isinstance(eq, dict):
                tex = str(eq.get("tex") or eq.get("latex") or "").strip()
                label = str(eq.get("label") or "").strip()[:60]
            elif isinstance(eq, str):
                tex, label = eq.strip(), ""
            else:
                continue
            tex = _clean_tex(tex)
            if tex:
                equations.append({"tex": tex, "label": label})

        # ---- node-graph "hub" layout --------------------------------------
        hub = None
        hub_raw = s.get("hub")
        if isinstance(hub_raw, dict):
            nodes = []
            for nd in (hub_raw.get("nodes") or [])[:5]:
                if isinstance(nd, dict) and (nd.get("label") or nd.get("sub")):
                    nodes.append({
                        "label": _delesson(str(nd.get("label") or "").strip()[:36]),
                        "sub": _delesson(str(nd.get("sub") or "").strip()[:36]),
                    })
                elif isinstance(nd, str) and nd.strip():
                    nodes.append({"label": _delesson(nd.strip()[:36]), "sub": ""})
            if nodes:
                hub = {
                    "center": _delesson(str(hub_raw.get("center") or "").strip()[:40]),
                    "subtitle": _delesson(str(hub_raw.get("subtitle") or "").strip()[:60]),
                    "footer": _delesson(str(hub_raw.get("footer") or "").strip()[:90]),
                    "nodes": nodes,
                }

        # ---- terminal/code "panel" layout ---------------------------------
        panel = None
        panel_raw = s.get("panel")
        if isinstance(panel_raw, dict):
            lines = [_delesson(str(x).rstrip()[:80]) for x in (panel_raw.get("lines") or []) if str(x).strip()][:9]
            if lines:
                panel = {
                    "title": _delesson(str(panel_raw.get("title") or "session").strip()[:60]),
                    "subtitle": _delesson(str(panel_raw.get("subtitle") or "").strip()[:50]),
                    "badge": _delesson(str(panel_raw.get("badge") or "").strip()[:24]),
                    "lines": lines,
                }

        # ---- before/after "transform" layout ------------------------------
        transform = None
        tr_raw = s.get("transform")
        if isinstance(tr_raw, dict):
            to_nodes = [
                _delesson(str(x).strip()[:28])
                for x in (tr_raw.get("to_nodes") or [])
                if str(x).strip()
            ][:4]
            if to_nodes or tr_raw.get("to_center"):
                transform = {
                    "from_title": _delesson(str(tr_raw.get("from_title") or "SOURCE").strip()[:40]),
                    "from_note": _delesson(str(tr_raw.get("from_note") or "").strip()[:40]),
                    "to_center": _delesson(str(tr_raw.get("to_center") or "").strip()[:36]),
                    "to_nodes": to_nodes,
                    "footer": _delesson(str(tr_raw.get("footer") or "").strip()[:80]),
                }

        # ---- linked "flow" pipeline layout --------------------------------
        flow = None
        flow_raw = s.get("flow")
        if isinstance(flow_raw, dict):
            fsteps = []
            for st in (flow_raw.get("steps") or [])[:4]:
                if isinstance(st, dict) and (st.get("label") or st.get("sub")):
                    fsteps.append({
                        "label": _delesson(str(st.get("label") or "").strip()[:42]),
                        "sub": _delesson(str(st.get("sub") or "").strip()[:72]),
                    })
                elif isinstance(st, str) and st.strip():
                    fsteps.append({"label": _delesson(st.strip()[:28]), "sub": ""})
            if len(fsteps) >= 2:
                orient = str(flow_raw.get("orientation") or "").strip().lower()
                if orient not in ("horizontal", "vertical"):
                    orient = "horizontal" if len(fsteps) <= 4 else "vertical"
                flow = {"orientation": orient, "steps": fsteps}

        # ---- kinetic cold-open "hook" (big number + punchline) ------------
        hook = None
        hook_raw = s.get("hook")
        if isinstance(hook_raw, dict) and (hook_raw.get("value") or hook_raw.get("punchline")):
            hook = {
                "value": _delesson(str(hook_raw.get("value") or "").strip()[:24]),
                "label": _delesson(str(hook_raw.get("label") or "").strip()[:48]),
                "punchline": _delesson(str(hook_raw.get("punchline") or "").strip()[:180]),
            }

        # ---- animated magnitude "bars" ------------------------------------
        bars = None
        bars_raw = s.get("bars")
        if isinstance(bars_raw, dict):
            items = []
            for it in (bars_raw.get("items") or [])[:5]:
                if not isinstance(it, dict):
                    continue
                label = _delesson(str(it.get("label") or "").strip()[:40])
                if not label:
                    continue
                try:
                    val = float(it.get("value") if it.get("value") is not None else 50)
                except (TypeError, ValueError):
                    val = 50.0
                val = max(4.0, min(100.0, val))
                items.append({
                    "label": label,
                    "value": val,
                    "note": _delesson(str(it.get("note") or "").strip()[:48]),
                })
            if len(items) >= 2:
                bars = {
                    "title": _delesson(str(bars_raw.get("title") or "").strip()[:60]),
                    "items": items,
                }

        # ---- articulated matrix cards (2×2 / 2×3) -------------------------
        matrix = None
        matrix_raw = s.get("matrix")
        if isinstance(matrix_raw, dict):
            m_items = []
            for it in (matrix_raw.get("items") or [])[:4]:
                if isinstance(it, dict) and (it.get("label") or it.get("detail")):
                    m_items.append({
                        "label": _delesson(str(it.get("label") or "").strip()[:42]),
                        "detail": _delesson(str(it.get("detail") or "").strip()[:140]),
                    })
                elif isinstance(it, str) and it.strip():
                    m_items.append({"label": _delesson(it.strip()[:36]), "detail": ""})
            if len(m_items) >= 3:
                matrix = {"items": m_items}

        # Resolve the layout: honor an explicit valid choice, else infer from
        # whichever rich field was provided, else fall back to bullets/diagram.
        valid_layouts = {
            "bullets", "stat", "compare", "steps", "quote", "diagram",
            "hub", "panel", "transform", "flow", "hook", "bars", "matrix", "cover",
            "bento", "cards", "rail", "spotlight", "quad", "chips", "numbered", "split",
            "free",
        }
        variety = ""
        if layout == "free":
            layout = "bullets"
        if layout in {
            "bento", "cards", "rail", "spotlight", "quad", "chips", "numbered", "split",
        }:
            variety = layout
            layout = "bullets"
        if layout not in valid_layouts:
            if hook:
                layout = "hook"
            elif bars:
                layout = "bars"
            elif matrix:
                layout = "matrix"
            elif flow:
                layout = "flow"
            elif hub:
                layout = "hub"
            elif panel:
                layout = "panel"
            elif transform:
                layout = "transform"
            elif stats:
                layout = "stat"
            elif compare:
                layout = "compare"
            elif steps:
                layout = "steps"
            elif quote:
                layout = "quote"
            elif show_fc:
                layout = "diagram"
            else:
                layout = "bullets"
        # Layouts that need their data present; degrade gracefully if missing.
        if layout == "hook" and not hook:
            layout = "stat" if stats else ("quote" if quote else "bullets")
        if layout == "bars" and not bars:
            layout = "compare" if compare else "stat" if stats else "bullets"
        if layout == "hub" and not hub:
            layout = "bullets"
        if layout == "panel" and not panel:
            layout = "bullets"
        if layout == "transform" and not transform:
            layout = "bullets"
        if layout == "flow" and not flow:
            layout = "steps" if steps else "bullets"
        if layout == "matrix" and not matrix:
            layout = "bullets"
        # A diagram layout needs a real flowchart; otherwise degrade gracefully.
        if layout == "diagram" and not flowchart:
            layout = "bullets"
        if layout == "diagram":
            show_fc = True

        if not (narration or heading or bullets or stats or compare or steps
                or quote or hub or panel or transform or flow or hook or bars
                or matrix or equations):
            continue
        slides.append({
            "layout": layout,
            "heading": heading or title,
            "bullets": bullets,
            "narration": narration or heading,
            "show_flowchart": show_fc,
            "active_node": active,
            "stats": stats,
            "compare": compare,
            "steps": steps,
            "quote": quote,
            "hub": hub,
            "panel": panel,
            "transform": transform,
            "flow": flow,
            "hook": hook,
            "bars": bars,
            "matrix": matrix,
            "equations": equations,
            "variety": variety,
            "weights": _coerce_weights(s.get("weights"), len(bullets)),
            "image": str(s.get("image") or "") or None,
            "image_caption": _delesson(str(s.get("image_caption") or "")[:160]),
        })
        _fill_slide_copy(slides[-1])
    if not slides:
        raise ValueError("no slides parsed")
    return {"title": title, "flowchart": flowchart, "slides": slides}


def _planning(options: dict | None) -> tuple[int, int, int, str]:
    """Return (slide_count, words_per_slide, target_seconds, extra_topics_block).

    Slide count and words/slide are derived so spoken runtime ≈ ``target_duration``.
    When the user left duration on Auto (0), we plan against the format's
    ``recommended_duration`` so landscape jobs don't collapse to a fixed 8-slide
    stub while Shorts/Reels already force a recommended length at normalize time.
    """
    options = options or {}
    topics = (options.get("extra_topics") or "").strip()
    spec = get_video_spec(options.get("video_format"))
    vertical = spec["orientation"] in ("vertical", "square")
    raw_target = int(options.get("target_duration") or 0)
    recommended = int(spec.get("recommended_duration") or (60 if vertical else 480))
    target = raw_target if raw_target > 0 else recommended
    target = max(int(spec["min_duration"]), min(target, int(spec["max_duration"])))

    # Effective narration pace. Kokoro/Supertonic at speed 1.0 land around
    # 130-140 wpm of *delivered* speech once natural sentence pauses are counted
    # (a little slower for punchy vertical shorts). We budget words at this REAL
    # rate and subtract a per-slide overhead for the fade/pad between slides, so
    # the summed audio tracks the target. This is paired with a hard post-gen
    # trim (_enforce_word_budget) AND an audio-layer duration fit
    # (media.fit_audio_to_target) so the video cannot balloon past the requested
    # length even if the LLM is verbose or the voice reads slowly.
    from .sync import SLIDE_OVERHEAD_SEC

    eff_wpm = 135 if not vertical else 125
    per_slide_overhead = float(SLIDE_OVERHEAD_SEC)

    # Visual beat length: more slides for longer targets so words/slide stay
    # speakable (~20–80) instead of dumping a whole lecture onto 20 slides.
    if vertical:
        secs_per_slide = 7.0
        min_slides, max_slides = 4, 20
        min_wps, max_wps = 16, 48
    else:
        secs_per_slide = 12.0
        min_slides, max_slides = 5, 40
        min_wps, max_wps = 28, 85

    slide_count = int(round(target / secs_per_slide))
    slide_count = max(min_slides, min(max_slides, slide_count))
    speaking_secs = max(1.0, float(target) - slide_count * per_slide_overhead)
    total_words = int(speaking_secs / 60.0 * eff_wpm)
    words_per_slide = max(1, int(round(total_words / slide_count)))

    # If per-slide words explode, add slides (up to max). If too sparse, merge.
    if words_per_slide > max_wps and slide_count < max_slides:
        slide_count = max(min_slides, min(max_slides, int(round(total_words / max_wps))))
        speaking_secs = max(1.0, float(target) - slide_count * per_slide_overhead)
        total_words = int(speaking_secs / 60.0 * eff_wpm)
        words_per_slide = max(1, int(round(total_words / slide_count)))
    elif words_per_slide < min_wps and slide_count > min_slides:
        slide_count = max(min_slides, min(max_slides, int(round(total_words / min_wps))))
        speaking_secs = max(1.0, float(target) - slide_count * per_slide_overhead)
        total_words = int(speaking_secs / 60.0 * eff_wpm)
        words_per_slide = max(1, int(round(total_words / slide_count)))

    words_per_slide = max(min_wps, min(max_wps, words_per_slide))

    if topics:
        extra_block = (
            "- ALSO weave in and teach these additional topics the user requested "
            f"(create dedicated slides for them as needed): {topics}\n"
            "- Prefer concrete, real-world examples / mistakes / analogies from the "
            "WEB RESEARCH block below when present. Do NOT invent citations, stats, "
            "or company stories that are not supported by that research or the source document.\n"
        )
        research = (options.get("topic_research") or "").strip()
        if research:
            extra_block += (
                "- WEB RESEARCH (live internet notes for the topics above — use these "
                "facts, examples, and phrasing to make slides richer and more specific):\n"
                f"{research}\n"
        )
    else:
        extra_block = ""

    layout_pref = (options.get("content_layout") or "auto").strip().lower()
    layout_hints = {
        "auto": (
            "- CONTENT LAYOUT: Auto — pick slide layouts from the source structure "
            "(steps/flow/hub/matrix…). Do NOT change the locked visual style, color "
            "theme, or narration voice; those come from Studio defaults.\n"
        ),
        "teaching": (
            "- CONTENT LAYOUT PREFERENCE: teaching — favor steps, flow, hub, matrix; "
            "clear intuition → mechanism → takeaway per slide.\n"
        ),
        "story": (
            "- CONTENT LAYOUT PREFERENCE: story — favor hook, quote, transform, compare; "
            "narrative arc with a cold open and crisp recap.\n"
        ),
        "ppt": (
            "- CONTENT LAYOUT PREFERENCE: PPT/deck — favor bullets, matrix, compare, steps; "
            "Gamma-like scannable cards, restrained density.\n"
        ),
        "diagram": (
            "- CONTENT LAYOUT PREFERENCE: diagram-heavy — favor flow, hub, diagram, panel; "
            "show systems and pipelines visually whenever possible.\n"
        ),
        "dense": (
            "- CONTENT LAYOUT PREFERENCE: dense brief — favor matrix, bars, stat, panel; "
            "pack parallel facts; still respect on-screen fit caps.\n"
        ),
        "modern_ppt": (
            "- CONTENT LAYOUT PREFERENCE: modern PPT — favor mosaic, process, agenda, "
            "hub, split hero; GraphicMama/corporate deck geometry with rounded cards.\n"
        ),
        "hyper": (
            "- CONTENT LAYOUT PREFERENCE: HyperFrames design identities — favor giant "
            "stat, sparse quote, matrix, compare; distinctive type + motif over color alone "
            "(Swiss grid, velvet calm, maximalist type, noir reveal).\n"
        ),
        "motion": (
            "- CONTENT LAYOUT PREFERENCE: Remotion-style motion — favor hook, kinetic "
            "center type, lower-third name plates, caption punch lines, promo feature "
            "sprints, racing bars; short on-screen text, high energy beats.\n"
        ),
        "content": (
            "- CONTENT LAYOUT PREFERENCE: content layout groups — favor bento grids, "
            "KPI strips, pull quotes, timeline rails, proof duos (claim|evidence), "
            "split media, stacked cards; one logical group per slide.\n"
        ),
    }
    extra_block += layout_hints.get(layout_pref, "")
    try:
        from .audience import audience_prompt_block

        extra_block += audience_prompt_block(options)
    except Exception:
        pass
    return slide_count, words_per_slide, target, extra_block

def _format_guidance(spec: dict, target: int, *, style_template: str = "") -> str:
    """Platform-specific pacing / copy rules injected into the slides prompt."""
    key = spec.get("key") or ""
    orient = spec.get("orientation") or "landscape"
    label = spec.get("label") or "Video"
    bits: list[str] = [
        f"Target runtime is ~{_target_phrase(target)} for {label}. "
        "Narration word counts MUST land near the per-slide budget so the "
        "finished video matches this length (do not under-fill or pad)."
    ]
    if orient in ("vertical", "square"):
        bits.append(
            "Short-form mobile: hook in 2s, one idea per slide, ultra-short "
            "on-screen labels (2–5 words). Prefer hook/stat/quote/tight steps."
        )
    else:
        bits.append(
            "Long-form / landscape: articulate WHY → HOW → SO WHAT. Prefer "
            "matrix/flow/hub/compare when the source has parallel facets; fill "
            "teaching slides with 3–4 scannable items (not sparse 1–2 liners, not crammed)."
        )
    if key == "linkedin_video":
        bits.append(
            "LinkedIn audience: professional, insight-led tone; concrete career/"
            "industry takeaways; avoid slang and meme hooks."
        )
    elif key in ("youtube_shorts", "instagram_reels", "tiktok"):
        bits.append(
            "Retention-first: pattern interrupt on slide 1, open loops mid-deck, "
            "end on a crisp CTA. Keep energy high; no slow academic warm-up."
        )
    elif key == "youtube_video":
        bits.append(
            "YouTube long-form: searchable specificity in headings; teach deeply "
            "enough that a viewer could re-explain the idea."
        )
    tags = [str(t) for t in (spec.get("tags") or []) if str(t).strip()]
    if tags:
        bits.append("Seed topic tags (weave naturally, do not list on-screen): " + ", ".join(tags[:8]) + ".")
    if style_template:
        bits.append(f"Prefer this visual rhythm when choosing layouts: {style_template}.")
    return "\n".join(f"- {b}" for b in bits)


def _target_phrase(seconds: int) -> str:
    if not seconds:
        return "a few minutes"
    m, s = divmod(seconds, 60)
    if m and s:
        return f"{m} min {s} sec"
    if m:
        return f"{m} minute" + ("s" if m != 1 else "")
    return f"{s} seconds"


def _split_content_batches(raw_text: str, max_chars: int) -> list[str]:
    """Split a long document into ordered batches under ``max_chars`` each.

    Splits on paragraph boundaries so we never cut a sentence mid-way. Used so
    very large inputs (books, long papers) are processed in pieces that fit the
    model's context window instead of being truncated to the first N chars.
    """
    text = (raw_text or "").strip()
    if len(text) <= max_chars:
        return [text] if text else []
    paras = re.split(r"\n\s*\n", text)
    batches: list[str] = []
    cur = ""
    for para in paras:
        para = para.strip()
        if not para:
            continue
        # A single huge paragraph is hard-split by characters.
        while len(para) > max_chars:
            if cur:
                batches.append(cur)
                cur = ""
            batches.append(para[:max_chars])
            para = para[max_chars:]
        if len(cur) + len(para) + 2 > max_chars:
            if cur:
                batches.append(cur)
            cur = para
        else:
            cur = f"{cur}\n\n{para}" if cur else para
    if cur:
        batches.append(cur)
    return batches


def _generate_one_batch(
    content_chunk: str,
    slide_count: int,
    words_per_slide: int,
    target: int,
    extra_block: str,
    analysis: dict | None,
    cover_image: str | None,
    is_first: bool,
    is_last: bool,
    part_idx: int,
    part_total: int,
    *,
    style_label: str = "Explainer",
    story_arc: str = "",
    style_template: str = "",
    format_label: str = "YouTube Video",
    platform: str = "YouTube",
    aspect_ratio: str = "16:9",
    format_guidance: str = "",
) -> dict:
    """Generate slides for one content batch. Returns a partial slide model."""
    structure = _structure_block(analysis, has_cover_image=bool(cover_image)) if is_first else ""
    extra = extra_block
    if part_total > 1:
        extra += (
            f"- This is PART {part_idx} of {part_total} of a longer document. "
            + ("Open with title + intro. " if is_first else
               "Continue teaching; do NOT repeat the intro. ")
            + ("End with a 'Key takeaways' recap slide. " if is_last else
               "Do NOT add a recap yet; more parts follow. ")
            + "Cover ONLY the content in this part.\n"
        )
    prompt = SLIDES_PROMPT.format(
        content=content_chunk,
        slide_count=slide_count,
        words_per_slide=words_per_slide,
        words_per_slide_min=int(round(words_per_slide * 0.7)),
        words_per_slide_max=int(round(words_per_slide * 1.15)),
        total_words=words_per_slide * slide_count,
        target_minutes=_target_phrase(target),
        structure_block=structure,
        analysis_block=_analysis_block(analysis) if is_first else "",
        extra_topics_block=extra,
        style_label=style_label or "Explainer",
        story_arc=(story_arc or DEFAULT_STORY_ARC).strip(),
        style_template=(style_template or "Title → teach → recap").strip(),
        format_label=format_label or "Video",
        platform=platform or "Video",
        aspect_ratio=aspect_ratio or "16:9",
        format_guidance=format_guidance or "- Match the requested runtime and platform tone.",
    )
    from .llm_parse import generate_structured, loads_json_lenient
    from .llm_schemas import SlideDeckLLM
    from . import llm_client

    try:
        deck = generate_structured(prompt, SlideDeckLLM, task="slides")
        return _coerce_slides(deck.model_dump())
    except Exception as e:
        # One last lenient parse of a fresh call only if structured validation
        # failed after its own retries — avoid raising away a usable deck.
        log.bind(task="slides").warning(f"pydantic slides path failed ({e}); lenient parse")
        try:
            raw = llm_client.generate_text(
                prompt
                + "\n\nReply with ONLY a valid JSON object with a non-empty slides array.",
                want_json=True,
            )
            data = loads_json_lenient(raw or "")
            if isinstance(data, dict) and data.get("slides"):
                return _coerce_slides(data)
        except Exception as e2:  # noqa: BLE001
            log.bind(task="slides").warning(f"lenient slides parse also failed: {e2}")
        raise


def generate_slides_with_muse(
    raw_text: str,
    options: dict | None = None,
    analysis: dict | None = None,
    cover_image: str | None = None,
) -> dict:
    slide_count, words_per_slide, target, extra_block = _planning(options)
    spec = get_video_spec((options or {}).get("video_format"))
    style_spec = get_style_spec((options or {}).get("video_style"))
    style_label = style_spec.get("label") or "Explainer"
    story_arc = style_spec.get("story_arc") or DEFAULT_STORY_ARC
    style_template = str(style_spec.get("template") or "").strip()
    format_guidance = _format_guidance(spec, target, style_template=style_template)
    batch_kwargs = dict(
        style_label=style_label,
        story_arc=story_arc,
        style_template=style_template,
        format_label=spec.get("label") or "Video",
        platform=spec.get("platform") or "Video",
        aspect_ratio=spec.get("aspect_ratio") or "16:9",
        format_guidance=format_guidance,
    )

    # Engagement / retention guidance applied to EVERY format so videos hook the
    # viewer and hold attention (not just short-form). Long-form gets a strong
    # cold-open + curiosity gaps; short-form gets the punchier block below.
    extra_block += (
        "- HOOK & RETENTION (very important): open with a strong, curiosity-driven"
        " hook in the FIRST slide — a surprising fact, a bold promise, a sharp"
        " question, or the payoff up front — so the viewer wants to keep watching."
        " Then keep momentum: open loops the later slides pay off, vary the rhythm,"
        " and make every slide earn its place. Speak with genuine energy and warmth,"
        " like a creator who loves this topic. End with a satisfying takeaway (and,"
        " when it fits, a light call to action).\n"
        f"- VISUAL STYLE (LOCKED): {style_label}. Follow that style's story arc and "
        "prefer layouts that match its template notes. Do NOT invent a different "
        "look, color theme, or brand because of the source document or figures — "
        "Studio / user defaults already chose the presentation.\n"
        "- ARTICULATE THE SOURCE: prefer specific mechanisms, named components,"
        " trade-offs, and concrete examples over vague slogans. When the document"
        " has several parallel claims/facts, use a 'matrix' or 'hub' layout so the"
        " frame shows the structure — do not collapse everything into two bullets.\n"
    )
    if (style_spec.get("key") or "").lower() == "hybrid":
        extra_block += (
            "- HYBRID CONTENT-FORMAT VARIETY (required): treat each slide as a"
            " different format beat. Map source material to layouts deliberately:\n"
            "  * striking number/cost/scale → hook or stat\n"
            "  * definition / named concept → hub or panel\n"
            "  * A vs B / myth vs reality → compare or bars\n"
            "  * procedure / pipeline → steps or flow (with arrows)\n"
            "  * parallel facets / checklist → matrix (3–4 cells, short labels)\n"
            "  * code, CLI, config, schema → panel\n"
            "  * messy → clean restructuring → transform\n"
            "  * one pivotal insight → quote\n"
            "  Do NOT reuse the same layout on consecutive slides. Aim to use at"
            " least 5 distinct layouts across the deck when length allows.\n"
    )

    if spec["orientation"] in ("vertical", "square"):
        _shape = "vertical" if spec["orientation"] == "vertical" else "square"
        extra_block += (
            f"- This is a {_shape} {spec['label']} ({spec['aspect_ratio']}) short-form video"
            f" (~{_target_phrase(target)} MAX — respect the platform limit strictly)."
            " Design it for mobile, fast-scrolling viewers:\n"
            "  * Slide 1 is a HOOK: one punchy line (use a 'quote' or 'stat' layout)"
            " that makes someone stop scrolling in the first 2 seconds — no slow intro.\n"
            "  * Prefer high-impact single-idea layouts: 'stat' for a striking number,"
            " 'quote' for one memorable line, tight 'steps' (max 3), or 2-3 word"
            " 'bullets'. AVOID dense text and avoid the same layout twice in a row.\n"
            "  * Keep headings to 2-4 words and each bullet to 2-3 words. Narration"
            " must be energetic, punchy and very concise (short sentences).\n"
            "  * End with a quick one-line takeaway or call to action.\n"
        )
    else:
        extra_block += (
            f"- This is a landscape {spec['label']} (~{_target_phrase(target)})."
            " Use clear teaching slides: matrix/flow/hub/compare with 3–4 articulated"
            " items when the source supports it — never overcrowded. Narration should"
            " fully explain each on-screen item in order so runtime matches the target.\n"
        )

    # Batch large inputs so we never truncate the document or overflow the
    # model's context. Each batch stays well under a safe character budget.
    batch_char_budget = 16000
    batches = _split_content_batches(raw_text, batch_char_budget) or [raw_text[:batch_char_budget]]

    if len(batches) == 1:
        model = _generate_one_batch(
            batches[0][:24000], slide_count, words_per_slide, target, extra_block,
            analysis, cover_image, is_first=True, is_last=True, part_idx=1, part_total=1,
            **batch_kwargs,
        )
    else:
        log.bind(task="generate").info(
            f"large input: generating in {len(batches)} batches "
            f"(~{slide_count} slides total, parallel={get_settings().effective_llm_parallel()})"
        )
        # Distribute the slide budget across batches proportionally to size.
        sizes = [len(b) for b in batches]
        total_size = sum(sizes) or 1
        per_batch = [max(2, round(slide_count * s / total_size)) for s in sizes]

        n = len(batches)

        def _run_batch(i: int) -> dict:
            is_first = i == 0
            is_last = i == n - 1
            return _generate_one_batch(
                batches[i], per_batch[i], words_per_slide, target, extra_block,
                analysis, cover_image, is_first, is_last, i + 1, n,
                **batch_kwargs,
            )

        # Fan out the batches concurrently (clamped to 1 for local Ollama). Each
        # slot is either a partial model dict or the Exception that was raised —
        # failed batches are skipped so a single hiccup never kills the lesson.
        results = muse_client.parallel_map(_run_batch, list(range(n)), ordered=True)

        merged_slides: list[dict] = []
        title = ""
        flowchart = ""
        for i, part in enumerate(results):
            if isinstance(part, Exception) or not isinstance(part, dict):
                log.bind(task="generate").warning(f"batch {i + 1} failed ({part}); skipping")
                continue
            if i == 0:
                title = part.get("title", "")
                flowchart = part.get("flowchart", "")
                merged_slides.extend(part.get("slides", []))
            else:
                # Only the first batch's flowchart is kept, so later slides must
                # not reference a (now mismatched) diagram.
                for sl in part.get("slides", []):
                    if sl.get("layout") == "diagram":
                        sl["layout"] = "bullets"
                    sl["show_flowchart"] = False
                    sl["active_node"] = None
                    merged_slides.append(sl)
        if not merged_slides:
            raise ValueError("all batches failed")
        model = {"title": title or "Overview", "flowchart": flowchart, "slides": merged_slides}

    # Prefer the analysis title when the model returned a weak/empty one.
    if analysis and analysis.get("title") and len(model.get("title", "")) < 4:
        model["title"] = str(analysis["title"])[:120]
    if analysis:
        model["doc_type"] = _normalize_doc_type(str(analysis.get("doc_type", "")))
        model["doc_analysis"] = {
            k: analysis.get(k)
            for k in (
                "doc_type", "subject", "audience", "tone", "authors",
                "institution", "source_title", "venue_or_year", "summary",
                "classifier",
            )
            if analysis.get(k) not in (None, "", [])
        }
    # Papers/books: force a dedicated cover layout with the first-page image.
    # Tutorials/notes/etc. skip this so we don't flash a random PDF page.
    model = _apply_cover_slide(model, analysis, cover_image)
    return model


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _chunk_to_word_budget(sentences: list[str], n_chunks: int, words_per_chunk: int) -> list[str]:
    """Greedily pack sentences into ``n_chunks`` chunks of ~``words_per_chunk``.

    Ensures we use the *whole* document so a long target duration is actually
    filled instead of collapsing to a few short slides.
    """
    if not sentences:
        return [""] * n_chunks
    chunks: list[list[str]] = [[] for _ in range(n_chunks)]
    counts = [0] * n_chunks
    idx = 0
    for sent in sentences:
        w = max(1, len(sent.split()))
        # Move to next chunk once the current one is full (but keep last open).
        while idx < n_chunks - 1 and counts[idx] >= words_per_chunk:
            idx += 1
        chunks[idx].append(sent)
        counts[idx] += w
    return [" ".join(c).strip() for c in chunks]


def _build_fallback_slides(raw_text: str, options: dict | None = None) -> dict:
    """Heuristic slide model used when no LLM is available.

    Distributes the *entire* extracted text across the planned number of slides
    so the resulting narration roughly matches the requested target duration,
    rather than only using the first few paragraphs (which produced very short
    videos before).
    """
    slide_count, words_per_slide, _target, _block = _planning(options)
    topics = [t.strip() for t in (options or {}).get("extra_topics", "").split(",") if t.strip()]
    research = ((options or {}).get("topic_research") or "").strip()

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", raw_text) if p.strip()]
    if not paragraphs:
        paragraphs = ["No readable text was extracted from the document."]

    title = paragraphs[0][:80]
    body_text = "\n\n".join(paragraphs[1:]) if len(paragraphs) > 1 else "\n\n".join(paragraphs)
    if topics:
        body_text += "\n\n" + ". ".join(topics)
    if research:
        body_text += "\n\n" + research[:2500]

    sentences = _split_sentences(body_text)
    # Reserve a title + takeaways slide; the rest are content steps.
    n_steps = max(1, slide_count - 2)
    step_narrations = _chunk_to_word_budget(sentences, n_steps, words_per_slide)
    # Drop trailing empty steps but always keep at least one.
    step_narrations = [s for s in step_narrations if s] or ["Overview"]
    n_steps = len(step_narrations)

    # Build flowchart: Start -> S1..Sn -> End
    node_ids = [chr(ord("A") + i) for i in range(n_steps)]
    lines = ["flowchart TD", "    START([Start])"]
    for i, nid in enumerate(node_ids, start=1):
        lines.append(f'    {nid}["Step {i}"]')
    lines.append("    END([Key Takeaways])")
    prev = "START"
    for nid in node_ids:
        lines.append(f"    {prev} --> {nid}")
        prev = nid
    lines.append(f"    {prev} --> END")
    flowchart = "\n".join(lines)

    slides = [{
        "heading": title,
        "bullets": ["Overview", "Follow the highlighted step"],
        "narration": (
            f"Welcome. We'll walk through {title}. "
            "The flowchart shows the overall process; we will highlight each step as we go."
        ),
        "show_flowchart": True,
        "active_node": None,
    }]
    for idx, (nid, narration) in enumerate(zip(node_ids, step_narrations), start=1):
        show_fc = (idx == 1) or (idx % 2 == 0)
        first = _split_sentences(narration)
        slides.append({
            "heading": f"Step {idx}",
            "bullets": [s[:120] for s in first[:3]][:3] or [f"Key idea {idx}"],
            "narration": narration or f"This is step {idx}.",
            "show_flowchart": show_fc,
            "active_node": nid,
        })
    slides.append({
        "heading": "Key Takeaways",
        "bullets": [f"Step {i + 1}" for i in range(n_steps)][:4],
        "narration": (
            "To recap, we covered each step shown in the flowchart. "
            "Review the diagram to reinforce how the pieces connect."
        ),
        "show_flowchart": True,
        "active_node": None,
    })
    return {"title": title, "flowchart": flowchart, "slides": slides}


def _display_caption(narration: str, *, max_chars: int = 150) -> str:
    """Compact on-screen subtitle line (full narration still drives TTS).

    Keeps the lower-third readable — Remotion/broadcast style — instead of
    stuffing the entire spoken paragraph into a single truncated pill.
    """
    t = " ".join((narration or "").split())
    if not t:
        return ""
    if len(t) <= max_chars:
        return t
    cut = t[: max_chars + 1]
    for sep in (". ", "? ", "! ", "; ", ", "):
        i = cut.rfind(sep)
        if i >= 48:
            return cut[: i + (0 if sep.startswith(",") else 1)].strip()
    sp = cut.rfind(" ")
    base = cut[:sp] if sp > 40 else cut[:max_chars]
    return base.rstrip(".,;: ") + "…"


def _trim_narration(text: str, max_words: int) -> str:
    """Trim narration to at most ``max_words`` words, preferring whole sentences.

    This is the hard guarantee that keeps a video near its requested length:
    no matter how verbose the LLM is, each slide's spoken script is capped so
    the summed audio duration tracks the target instead of ballooning.
    """
    text = (text or "").strip()
    if not text:
        return text
    if len(text.split()) <= max_words:
        return text
    kept: list[str] = []
    used = 0
    for sent in _split_sentences(text):
        w = len(sent.split())
        if used + w > max_words:
            if not kept:
                words = sent.split()[:max_words]
                dangling = {"a", "an", "the", "and", "or", "but", "with", "to", "of", "for", "in", "on", "little", "very"}
                while len(words) > 3 and words[-1].lower().strip(".,;:") in dangling:
                    words.pop()
                return " ".join(words).rstrip(",;:") + "."
            break
        kept.append(sent)
        used += w
        if used >= max_words:
            break
    if not kept:
        return " ".join(text.split()[:max_words]).rstrip(",;:") + "."
    return " ".join(kept)


def _slim_receipt(receipt: dict | None) -> dict:
    """Small, acyclic summary of an agent run (no per-turn args/results)."""
    r = receipt or {}
    steps = []
    for s in r.get("steps") or []:
        if not isinstance(s, dict):
            continue
        steps.append({
            "turn": s.get("turn"),
            "thought": str(s.get("thought") or "")[:300],
            "tool": s.get("tool"),
            "status": s.get("status"),
            "elapsed_ms": s.get("elapsed_ms"),
        })
    return {
        "session_id": r.get("session_id"),
        "total_turns": r.get("total_turns"),
        "tools_used": list(r.get("tools_used") or []),
        "has_errors": bool(r.get("has_errors")),
        "total_elapsed_ms": r.get("total_elapsed_ms"),
        "total_duration_sec": r.get("total_duration_sec"),
        "repaired": r.get("repaired", 0),
        "max_turns": r.get("max_turns"),
        "plan": [
            {"id": p.get("id"), "description": p.get("description"), "status": p.get("status"),
             "result_summary": str(p.get("result_summary") or "")[:200]}
            for p in (r.get("plan") or []) if isinstance(p, dict)
        ],
        "steps": steps,
    }


def _enforce_word_budget(model: dict, options: dict | None) -> dict:
    """Cap total narration to the planned budget so length tracks the target.

    Recomputes per-slide caps from the *actual* slide count (batches can drift)
    so a 5-minute plan isn't underfilled when only 8 slides came back, and isn't
    overstuffed when 30 did.
    """
    slides = model.get("slides") or []
    if not slides:
        return model
    _, plan_wps, target, _ = _planning(options)
    if not target:
        return model
    n = len(slides)
    # Redistribute planned speaking time across whatever slides we actually got.
    from .sync import SLIDE_OVERHEAD_SEC
    from ..video_options import get_video_spec

    spec = get_video_spec((options or {}).get("video_format"))
    vertical = spec["orientation"] in ("vertical", "square")
    eff_wpm = 135 if not vertical else 125
    speaking = max(1.0, float(target) - n * float(SLIDE_OVERHEAD_SEC))
    total_words = int(speaking / 60.0 * eff_wpm)
    words_per_slide = max(12, int(round(total_words / n)))
    max_wps = 48 if vertical else 90
    min_wps = 14 if vertical else 24
    words_per_slide = max(min_wps, min(max_wps, words_per_slide))
    per_slide_max = int(round(words_per_slide * 1.12))
    short_max = max(14, int(round(words_per_slide * 0.65)))
    total_before = 0
    total_after = 0
    for i, s in enumerate(slides):
        if not isinstance(s, dict):
            continue
        original = str(s.get("narration") or "")
        total_before += len(original.split())
        is_edge = i == 0 or i == n - 1
        cap = short_max if is_edge else per_slide_max
        trimmed = _trim_narration(original, cap)
        s["narration"] = trimmed
        total_after += len(trimmed.split())
    if total_after != total_before:
        log.bind(task="generate").info(
            f"narration budget: {total_before} -> {total_after} words "
            f"(~{words_per_slide}/slide × {n} for {target}s; plan was {plan_wps}/slide)"
        )
    return model


def build_slide_model(
    raw_text: str, options: dict | None = None, cover_image: str | None = None
) -> tuple[dict, bool]:
    """Return (slide_model, used_llm).

    ``cover_image`` is an optional URL/path to the document's first-page image;
    for papers/books it is shown on the opening slide.
    """
    from ..capabilities import llm_available

    analysis = analyze_document(raw_text) if (raw_text or "").strip() else {
        "doc_type": "other", "title": "Overview", "classifier": "empty",
    }
    try:
        from .audience import overlay_analysis

        analysis = overlay_analysis(analysis, options)
    except Exception:
        pass
    # Resolve Auto style/theme only when those keys are still Auto.
    # Explicit Studio / cron picks must never be swapped by doc/VLM heuristics.
    # lock_visual_preset reinforces an explicit style; it must not freeze style=auto.
    opts = options if isinstance(options, dict) else {}
    style_raw = str(opts.get("video_style") or "").strip().lower()
    theme_raw = str(opts.get("video_theme") or "").strip().lower()
    style_locked = bool(style_raw and style_raw != "auto")
    theme_locked = bool(theme_raw and theme_raw != "auto")

    if style_locked:
        if style_raw and style_raw != "auto" and not opts.get("video_style_label"):
            from ..video_options import VIDEO_STYLES
            if style_raw in VIDEO_STYLES:
                opts["video_style_label"] = VIDEO_STYLES[style_raw]["label"]
        opts["video_style_was_auto"] = False
        opts.pop("video_style_reason", None)
    else:
        apply_auto_video_style(opts, analysis=analysis, text=raw_text or "")

    if theme_locked:
        if theme_raw and theme_raw != "auto" and not opts.get("video_theme_label"):
            from ..video_options import VIDEO_THEMES
            if theme_raw in VIDEO_THEMES:
                opts["video_theme_label"] = VIDEO_THEMES[theme_raw]["label"]
        opts["video_theme_was_auto"] = False
        opts.pop("video_theme_reason", None)
    else:
        apply_auto_video_theme(opts, analysis=analysis)

    # 1. Agentic AI Harness: ReAct loop with tools, layered memory, and self-critique
    use_agent = bool(opts.get("use_agent_harness", True))
    if use_agent and llm_available():
        try:
            import time
            from .agent_harness import AgentHarness

            session_id = str(opts.get("job_id") or opts.get("session_id") or f"gen_{int(time.time())}")
            work_dir = Path(opts["work_dir"]) if opts.get("work_dir") else None
            harness = AgentHarness(session_id=session_id, options=opts, work_dir=work_dir)
            model, used_llm, receipt = harness.run(raw_text, cover_image)
            # The raw receipt embeds each turn's args/result (which contain the
            # model itself). Storing it as-is makes a circular structure that
            # breaks JSON serialisation, so keep a slim copy only.
            slim = _slim_receipt(receipt)
            opts["agent_receipt"] = slim
            model["agent_receipt"] = slim
            model = _enforce_word_budget(model, opts)
            log.bind(task="generate").success(
                f"Agent Harness completed {len(receipt.get('steps', []))} turns: {len(model.get('slides', []))} slides "
                f"(style: {opts.get('video_style', 'n/a')}, theme: {opts.get('video_theme', 'n/a')})"
            )
            if analysis:
                model["doc_type"] = _normalize_doc_type(str(analysis.get("doc_type", "")))
                model["doc_analysis"] = analysis
            model["video_style"] = opts.get("video_style")
            model["video_style_label"] = opts.get("video_style_label")
            model["video_style_reason"] = opts.get("video_style_reason")
            model["video_style_was_auto"] = bool(opts.get("video_style_was_auto"))
            model["video_theme"] = opts.get("video_theme")
            model["video_theme_label"] = opts.get("video_theme_label")
            model["video_theme_reason"] = opts.get("video_theme_reason")
            model["video_theme_was_auto"] = bool(opts.get("video_theme_was_auto"))
            return model, used_llm
        except Exception as e:
            log.bind(task="generate").warning(
                f"Agent harness slide generation failed ({e}); falling back to standard LLM flow: {e}"
            )

    # 2. Standard single-shot LLM flow (fallback if harness is bypassed or hits error)
    if llm_available():
        try:
            model = generate_slides_with_muse(raw_text, opts, analysis, cover_image)
            model = _enforce_word_budget(model, opts)
            log.bind(task="generate").success(
                f"LLM authored {len(model['slides'])} slides "
                f"(type: {analysis.get('doc_type', 'n/a')}, ml: {_is_ml(analysis)}, "
                f"style: {opts.get('video_style', 'n/a')}, "
                f"theme: {opts.get('video_theme', 'n/a')})"
            )
            if analysis:
                model["doc_type"] = _normalize_doc_type(str(analysis.get("doc_type", "")))
                model["doc_analysis"] = analysis
            model["video_style"] = opts.get("video_style")
            model["video_style_label"] = opts.get("video_style_label")
            model["video_style_reason"] = opts.get("video_style_reason")
            model["video_style_was_auto"] = bool(opts.get("video_style_was_auto"))
            model["video_theme"] = opts.get("video_theme")
            model["video_theme_label"] = opts.get("video_theme_label")
            model["video_theme_reason"] = opts.get("video_theme_reason")
            model["video_theme_was_auto"] = bool(opts.get("video_theme_was_auto"))
            return model, True
        except Exception as e:
            log.bind(task="generate").warning(
                f"LLM slide generation failed ({e}); using built-in template"
            )
    else:
        log.bind(task="generate").warning(
            "no LLM available; using built-in template (narration may be short)"
        )
    model = _build_fallback_slides(raw_text, opts)
    model = _apply_cover_slide(model, analysis, cover_image)
    if analysis:
        model["doc_type"] = _normalize_doc_type(str(analysis.get("doc_type", "")))
        model["doc_analysis"] = analysis
    model["video_style"] = opts.get("video_style")
    model["video_style_label"] = opts.get("video_style_label")
    model["video_style_reason"] = opts.get("video_style_reason")
    model["video_style_was_auto"] = bool(opts.get("video_style_was_auto"))
    model["video_theme"] = opts.get("video_theme")
    model["video_theme_label"] = opts.get("video_theme_label")
    model["video_theme_reason"] = opts.get("video_theme_reason")
    model["video_theme_was_auto"] = bool(opts.get("video_theme_was_auto"))
    model = _enforce_word_budget(model, opts)
    return model, False


# --------------------------------------------------------------- HTML render ----

def _render_hub(hub: dict) -> str:
    """Radial node-graph: a center concept ringed by satellite nodes.

    Nodes are placed on an ellipse via CSS custom properties so the layout
    scales with node count. Each satellite is a small labelled card with a
    dashed connector back to the center (matches the shared node-graph style).
    """
    if not isinstance(hub, dict):
        return ""
    nodes = hub.get("nodes") or []
    n = max(1, len(nodes))
    items = []
    for i, nd in enumerate(nodes):
        ang = (360.0 / n) * i - 90.0  # start at top
        label = html.escape(str((nd.get("label") if isinstance(nd, dict) else nd) or ""))
        sub = html.escape(str((nd.get("sub") if isinstance(nd, dict) else "") or ""))
        sub_html = f'<span class="hub-sub">{sub}</span>' if sub else ""
        items.append(
            f'<div class="hub-node" style="--ang:{ang:.2f}deg; --i:{i + 1}">'
            f'<span class="hub-dot"></span>'
            f'<div class="hub-card"><span class="hub-label">{label}</span>{sub_html}</div>'
            f'</div>'
        )
    center = html.escape(str(hub.get("center") or ""))
    subtitle = html.escape(str(hub.get("subtitle") or ""))
    footer = html.escape(str(hub.get("footer") or ""))
    sub_html = f'<div class="hub-center-sub">{subtitle}</div>' if subtitle else ""
    foot_html = f'<div class="hub-foot"><span class="hub-foot-dot"></span>{footer}</div>' if footer else ""
    return (
        '<div class="hub reveal" style="--n:' + str(n) + '">'
        '<div class="hub-ring">'
        f'<div class="hub-center"><span class="hub-center-label">{center}</span>{sub_html}</div>'
        + "".join(items)
        + '</div>'
        + foot_html
        + '</div>'
    )


def _render_matrix(matrix: dict) -> str:
    """2×2 / 2×3 articulated cards — denser than bullets, still scannable."""
    if not isinstance(matrix, dict):
        return ""
    items = matrix.get("items") or []
    cards = []
    for i, it in enumerate(items):
        label = html.escape(str((it.get("label") if isinstance(it, dict) else it) or ""))
        detail = html.escape(str((it.get("detail") if isinstance(it, dict) else "") or ""))
        detail_html = f'<span class="mx-detail">{detail}</span>' if detail else ""
        cards.append(
            f'<div class="mx-card" style="--i:{i + 1}">'
            f'<span class="mx-label">{label}</span>{detail_html}</div>'
        )
    cols = 2 if len(items) <= 4 else 3
    return f'<div class="matrix reveal" style="--cols:{cols}">{"".join(cards)}</div>'


# Compose mode → content geometries (not palettes). Rotate so consecutive
# bullet slides do not look like the same card restyled.
_COMPOSE_VARIETIES: dict[str, tuple[str, ...]] = {
    "bento": ("bento", "quad", "cards"),
    "mosaic": ("quad", "bento", "chips"),
    "kpi": ("numbered", "quad", "spotlight"),
    "rail": ("rail", "numbered", "split"),
    "subway": ("rail", "numbered", "chips"),
    "chapters": ("numbered", "rail", "split"),
    "funnel": ("rail", "numbered", "spotlight"),
    "cycle": ("rail", "quad", "chips"),
    "split": ("split", "cards", "spotlight"),
    "dual": ("split", "quad", "cards"),
    "quote": ("spotlight", "cards", "split"),
    "magazine": ("spotlight", "split", "cards"),
    "mega_type": ("spotlight", "chips", "cards"),
    "kinetic_center": ("spotlight", "chips", "numbered"),
    "caption": ("spotlight", "chips", "cards"),
    "poster": ("spotlight", "cards", "numbered"),
    "kanban": ("split", "quad", "chips"),
    "cards_stack": ("cards", "bento", "numbered"),
    "polaroid": ("cards", "quad", "spotlight"),
    "chalkboard": ("numbered", "cards", "split"),
    "swiss": ("numbered", "split", "quad"),
    "broadcast": ("chips", "spotlight", "rail"),
    "ticker": ("chips", "rail", "spotlight"),
    "glass": ("cards", "split", "bento"),
    "letterbox": ("spotlight", "cards", "split"),
    "quad": ("quad", "bento", "split"),
    "stack": ("cards", "numbered", "split", "bento", "chips", "rail"),
}
_ALL_VARIETIES = (
    "bento", "quad", "rail", "split", "spotlight", "cards", "numbered", "chips", "grid",
    "timeline", "stairs", "notes",
)

# Each design family prefers different content geometries, so decks differ in
# structure (not only colour) from one template to the next.
_COMPOSE_VARIETIES.update({
    "edu_split": ("numbered", "spotlight", "stairs", "split", "rail"),
    "edu_band": ("timeline", "cards", "quad", "rail", "split"),
    "edu_sketch": ("notes", "timeline", "cards", "numbered", "chips"),
    "edu_poster": ("spotlight", "stairs", "numbered", "chips", "cards"),
    "edu_bento": ("bento", "quad", "cards", "stairs", "timeline"),
    "edu_notebook": ("numbered", "notes", "rail", "chips", "split"),
})


def _variety_fits(name: str, n: int, vertical: bool) -> bool:
    if n <= 0:
        return False
    if name == "spotlight":
        return n <= 4
    if name == "split":
        return n >= 2
    if name == "bento":
        return 3 <= n <= 6
    if name == "quad":
        return n >= 3
    if name == "rail":
        return 3 <= n <= 6
    if name == "cards":
        return 2 <= n <= 5
    if name == "numbered":
        return 2 <= n <= 6
    if name == "chips":
        return n >= 2
    if name == "grid":
        return n >= 3 and not vertical
    if name == "timeline":
        return 3 <= n <= 5 and not vertical
    if name == "stairs":
        return 3 <= n <= 5
    if name == "notes":
        return 2 <= n <= 5
    return True


def _lx_items_for(eng, layout: str, s: dict, raw_bullets: list, stats, steps, matrix, narration: str):
    """Turn whatever structure a slide has into synthesizer items (no template)."""
    rich = {
        "hook", "bars", "compare", "quote", "hub", "panel", "transform", "flow", "diagram",
    }
    if layout == "stat" and isinstance(stats, list) and len(stats) >= 2:
        labs, vals = [], []
        for st in stats:
            if not isinstance(st, dict):
                continue
            lab = str(st.get("label") or "").strip()
            val = str(st.get("value") or "").strip()
            labs.append(lab or val)
            vals.append(val if lab else "")
        return eng.make_items(labs, values=vals), "stats"
    if layout == "steps" and steps:
        return eng.make_items([str(x) for x in steps]), "steps"
    if layout == "matrix" and isinstance(matrix, dict):
        rows = matrix.get("items") or []
        labs, dets = [], []
        for r in rows:
            if isinstance(r, dict):
                lab = str(r.get("label") or "").strip()
                det = str(r.get("detail") or "").strip()
            else:
                lab, det = str(r or "").strip(), ""
            if not lab and det:
                lab, det = det, ""
            if lab:
                labs.append(lab)
                dets.append(det)
        return eng.make_items(labs, details=dets), "matrix"
    if layout in rich or layout in ("stat", "steps", "matrix"):
        return [], ""
    texts = [str(b) for b in raw_bullets] or eng.derive_items(narration)
    return eng.make_items(texts, weights=s.get("weights")), "bullets"


def pick_bullet_variety(
    compose: str,
    idx: int,
    n: int,
    *,
    is_hero: bool = False,
    is_recap: bool = False,
    vertical: bool = False,
    forced: str = "",
    avoid: str = "",
) -> str:
    """Choose a content geometry for a bullets slide."""
    if forced and _variety_fits(forced, n, vertical):
        return forced
    if is_recap:
        return "numbered" if n >= 2 else "chips"
    if is_hero:
        return "spotlight" if n <= 3 else "cards"
    pool = list(_COMPOSE_VARIETIES.get(compose, _COMPOSE_VARIETIES["stack"]))
    start = idx % max(1, len(pool))
    ordered = pool[start:] + pool[:start] + list(_ALL_VARIETIES)
    for name in ordered:
        if name == avoid:
            continue
        if _variety_fits(name, n, vertical):
            return name
    return "grid" if n >= 3 and not vertical else "cards"


def _render_bullet_variety(
    items: list[str],
    variety: str,
    *,
    recap: bool = False,
) -> str:
    """HTML for a bullets slide that is not a flat same-y card stack."""
    items = [str(x).strip() for x in (items or []) if str(x).strip()]
    if not items:
        return ""

    def _txt(t: str) -> str:
        return html.escape(t)

    def _chip_row(rest: list[str], start: int = 1) -> str:
        if not rest:
            return ""
        chips = "".join(
            f'<li class="v-chip" style="--i:{start + i}">{_txt(t)}</li>'
            for i, t in enumerate(rest)
        )
        return f'<ul class="v-chips">{chips}</ul>'

    mark = "v-check" if recap else "v-idx"
    if variety == "spotlight":
        lead, rest = items[0], items[1:]
        return (
            '<div class="v-spot reveal">'
            f'<p class="v-lead" style="--i:1">{_txt(lead)}</p>'
            f'{_chip_row(rest, 2)}'
            "</div>"
        )
    if variety == "split":
        mid = max(1, (len(items) + 1) // 2)
        left, right = items[:mid], items[mid:]

        def _col(col, offset):
            lis = "".join(
                f'<li style="--i:{offset + i}"><span class="{mark}">{offset + i:02d}</span>'
                f'<span class="v-t">{_txt(t)}</span></li>'
                for i, t in enumerate(col)
            )
            return f'<ul class="v-col">{lis}</ul>'

        return f'<div class="v-split reveal">{_col(left, 1)}{_col(right, 1 + len(left))}</div>'
    if variety == "rail":
        head, tail = items[:5], items[5:]
        lis = "".join(
            f'<li style="--i:{i + 1}">'
            f'<span class="v-num">{i + 1}</span>'
            f'<span class="v-t">{_txt(t)}</span></li>'
            for i, t in enumerate(head)
        )
        return f'<ol class="v-rail reveal">{lis}</ol>{_chip_row(tail, 6)}'
    if variety == "numbered":
        lis = "".join(
            f'<li style="--i:{i + 1}">'
            f'<span class="v-num">{i + 1:02d}</span>'
            f'<span class="v-t">{_txt(t)}</span></li>'
            for i, t in enumerate(items[:6])
        )
        return f'<ol class="v-agenda reveal">{lis}</ol>'
    if variety == "cards":
        cards = "".join(
            f'<article class="v-card" style="--i:{i + 1};--tilt:{(i % 3 - 1) * 1.2:.1f}deg">'
            f'<span class="{mark}">{i + 1:02d}</span>'
            f'<span class="v-t">{_txt(t)}</span></article>'
            for i, t in enumerate(items[:5])
        )
        return f'<div class="v-cards reveal">{cards}</div>{_chip_row(items[5:], 6)}'
    if variety in ("bento", "quad"):
        cap = 4 if variety == "quad" else 5
        head, tail = items[:cap], items[cap:]
        tiles = "".join(
            f'<div class="v-tile" style="--i:{i + 1}">'
            f'<span class="v-k">{i + 1:02d}</span>'
            f'<span class="v-t">{_txt(t)}</span></div>'
            for i, t in enumerate(head)
        )
        cls = "v-bento v-quad reveal" if variety == "quad" else "v-bento reveal"
        return f'<div class="{cls}">{tiles}</div>{_chip_row(tail, cap + 1)}'
    if variety == "timeline":
        head, tail = items[:5], items[5:]
        nodes = "".join(
            f'<div class="v-tile v-tl" style="--i:{i + 1}">'
            f'<span class="v-dot">{i + 1}</span>'
            f'<span class="v-t">{_txt(t)}</span></div>'
            for i, t in enumerate(head)
        )
        line = (
            '<svg class="v-line" viewBox="0 0 100 4" preserveAspectRatio="none" aria-hidden="true">'
            '<path class="draw" pathLength="1" d="M0 2 L100 2"/></svg>'
        )
        return (
            f'<div class="v-time reveal" style="--n:{len(head)}">{line}{nodes}</div>{_chip_row(tail, 6)}'
        )
    if variety == "stairs":
        head, tail = items[:5], items[5:]
        steps_ = "".join(
            f'<div class="v-tile v-st" style="--i:{i + 1};--k:{i}">'
            f'<span class="{mark}">{i + 1:02d}</span>'
            f'<span class="v-t">{_txt(t)}</span></div>'
            for i, t in enumerate(head)
        )
        return f'<div class="v-stairs reveal" style="--n:{len(head)}">{steps_}</div>{_chip_row(tail, 6)}'
    if variety == "notes":
        head, tail = items[:5], items[5:]
        notes_ = "".join(
            f'<div class="v-card v-note" style="--i:{i + 1};--k:{i}">'
            f'<span class="v-pin" aria-hidden="true"></span>'
            f'<span class="v-t">{_txt(t)}</span></div>'
            for i, t in enumerate(head)
        )
        return f'<div class="v-notes reveal" style="--n:{len(head)}">{notes_}</div>{_chip_row(tail, 6)}'
    if variety == "chips":
        return f'<div class="v-spot reveal">{_chip_row(items, 1)}</div>'
    return ""


def _render_panel(panel: dict) -> str:
    """A terminal / code-editor window mock with syntax-tinted lines."""
    if not isinstance(panel, dict):
        return ""
    def _line(raw: str) -> str:
        raw_str = str(raw or "")
        esc = html.escape(raw_str)
        cls = "pl"
        stripped = raw_str.lstrip()
        if stripped.startswith("#") or stripped.startswith("//"):
            cls = "pl comment"
        elif stripped.startswith(("$", ">")):
            cls = "pl cmd"
        return f'<div class="{cls}">{esc}</div>'

    lines = "".join(_line(x) for x in (panel.get("lines") or []))
    title = html.escape(str(panel.get("title") or ""))
    subtitle = html.escape(str(panel.get("subtitle") or ""))
    badge = html.escape(str(panel.get("badge") or ""))
    sub_html = f'<div class="panel-sub">{subtitle}</div>' if subtitle else ""
    badge_html = (
        f'<div class="panel-foot"><span class="panel-model">MODEL</span>'
        f'<span class="panel-badge">{badge}</span></div>' if badge else ""
    )
    return (
        '<div class="panel reveal">'
        '<div class="panel-bar">'
        '<span class="panel-dot"></span><span class="panel-dot"></span><span class="panel-dot"></span>'
        f'<span class="panel-title">{title}</span>'
        '<span class="panel-settings">settings</span>'
        '</div>'
        f'{sub_html}'
        f'<div class="panel-body">{lines}<span class="panel-caret"></span></div>'
        f'{badge_html}'
        '</div>'
    )


def _render_transform(tr: dict) -> str:
    """Before → after: source card, arrow, then a titled chip grid (no overlap)."""
    if not isinstance(tr, dict):
        return ""
    to_nodes = tr.get("to_nodes") or []
    chips = []
    for i, lbl in enumerate(to_nodes):
        if len(str(lbl).strip()) < 2:
            continue
        chips.append(
            f'<div class="tr-chip" style="--i:{i + 1}">'
            f'<span class="tr-dot"></span>'
            f'<span class="tr-node-label">{html.escape(str(lbl))}</span>'
            f'</div>'
        )
    from_title = html.escape(str(tr.get("from_title") or ""))
    from_note = html.escape(str(tr.get("from_note") or ""))
    to_center = html.escape(str(tr.get("to_center") or ""))
    footer = html.escape(str(tr.get("footer") or ""))
    note_html = f'<div class="tr-src-note">{from_note}</div>' if from_note else ""
    center_html = (
        f'<div class="tr-center"><span class="tr-center-dot"></span>'
        f'<span class="tr-center-label">{to_center}</span></div>'
        if to_center else ""
    )
    foot_html = (
        f'<div class="tr-foot"><span class="tr-foot-dot"></span>{footer}</div>'
        if footer else ""
    )
    chips_html = f'<div class="tr-chips">{"".join(chips)}</div>' if chips else ""
    return (
        '<div class="transform reveal">'
        '<div class="tr-stage">'
        '<div class="tr-src">'
        f'<div class="tr-src-title">{from_title}</div>'
        '<div class="tr-src-lines"><i></i><i></i><i></i><i></i><i></i></div>'
        f'{note_html}'
        '</div>'
        '<div class="tr-arrow" aria-hidden="true">&rarr;</div>'
        f'<div class="tr-dest" style="--n:{max(1, len(to_nodes))}">'
        f'{center_html}{chips_html}'
        '</div>'
        '</div>'
        + foot_html
        + '</div>'
    )


def _render_flow(flow: dict) -> str:
    """A connected pipeline: linked cards joined by animated arrows.

    Shows linkage/flow explicitly — each stage feeds the next through a glowing
    animated connector, so causal/sequential ideas read as a real flow instead
    of a flat list. Horizontal for short chains, vertical for longer ones.
    """
    if not isinstance(flow, dict):
        return ""
    steps = flow.get("steps") or []
    orient = flow.get("orientation") or "horizontal"
    n = len(steps)
    parts = []
    for i, st in enumerate(steps):
        label = html.escape(str((st.get("label") if isinstance(st, dict) else st) or ""))
        sub = html.escape(str((st.get("sub") if isinstance(st, dict) else "") or ""))
        sub_html = f'<span class="flow-sub">{sub}</span>' if sub else ""
        parts.append(
            f'<div class="flow-node" style="--i:{i + 1}" data-anim-from="{0.14 + i * 0.07:.2f}" data-anim-dur="0.35">'
            f'<span class="flow-idx">{i + 1}</span>'
            f'<div class="flow-body"><span class="flow-label">{label}</span>{sub_html}</div>'
            f'</div>'
        )
        if i < n - 1:
            # Animated connector between stages (arrow + travelling pulse).
            parts.append(
                f'<div class="flow-arrow" style="--i:{i + 1}" data-anim-from="{0.20 + i * 0.07:.2f}" data-anim-dur="0.28">'
                '<span class="flow-line"><span class="flow-pulse"></span></span>'
                '<span class="flow-head"></span>'
                '</div>'
            )
    return f'<div class="flow flow-{orient} reveal" style="--n:{n}">' + "".join(parts) + '</div>'


def _render_hook(hook: dict) -> str:
    """Cold-open kinetic number + punchline (Cloud Codes / tech-YouTube style)."""
    if not isinstance(hook, dict):
        return ""
    value = html.escape(str(hook.get("value") or ""))
    label = html.escape(str(hook.get("label") or ""))
    punch = html.escape(str(hook.get("punchline") or ""))
    label_html = f'<div class="hook-label" data-anim-from="0.22" data-anim-dur="0.35">{label}</div>' if label else ""
    punch_html = (
        f'<p class="hook-punch" data-anim-from="0.32" data-anim-dur="0.4">{punch}</p>'
        if punch else ""
    )
    return (
        '<div class="hook reveal">'
        '<div class="hook-bar" data-anim-from="0.04" data-anim-dur="0.45" aria-hidden="true"></div>'
        f'<div class="hook-value" data-anim-from="0.08" data-anim-dur="0.5">{value}</div>'
        f'{label_html}{punch_html}'
        '</div>'
    )


def _render_bars(bars: dict) -> str:
    """HyperFrames-style animated magnitude bars for comparisons."""
    if not isinstance(bars, dict):
        return ""
    items = bars.get("items") or []
    title = html.escape(str(bars.get("title") or ""))
    title_html = (
        f'<div class="bars-title" data-anim-from="0.08" data-anim-dur="0.35">{title}</div>'
        if title else ""
    )
    rows = []
    for i, it in enumerate(items):
        label = html.escape(str((it.get("label") if isinstance(it, dict) else it) or ""))
        note = html.escape(str((it.get("note") if isinstance(it, dict) else "") or ""))
        try:
            val = it.get("value") if isinstance(it, dict) else 50
            pct = float(val if val is not None else 50)
        except (TypeError, ValueError):
            pct = 50.0
        pct = max(4.0, min(100.0, pct))
        note_html = f'<span class="bar-note">{note}</span>' if note else ""
        rows.append(
            f'<div class="bar-row" style="--i:{i + 1};--w:{pct:.1f}%" '
            f'data-anim-from="{0.14 + i * 0.08:.2f}" data-anim-dur="0.45">'
            f'<div class="bar-meta"><span class="bar-label">{label}</span>{note_html}</div>'
            f'<div class="bar-track"><div class="bar-fill" style="--w:{pct:.1f}%"></div></div>'
            f'</div>'
        )
    return (
        f'<div class="bars reveal">{title_html}'
        + "".join(rows)
        + '</div>'
    )


def _slide_density(s: dict, layout: str) -> str:
    """Return low|med|high so CSS can shrink type for packed frames."""
    if not isinstance(s, dict):
        return "low"
    n = len(s.get("bullets") or []) + len(s.get("steps") or [])
    if layout == "hub":
        hub = s.get("hub")
        nodes = hub.get("nodes") if isinstance(hub, dict) else []
        n = len(nodes or [])
    elif layout == "compare":
        cmp = s.get("compare") if isinstance(s.get("compare"), dict) else {}
        n = len(cmp.get("left") or []) + len(cmp.get("right") or [])
    elif layout == "matrix":
        matrix = s.get("matrix")
        items = matrix.get("items") if isinstance(matrix, dict) else []
        n = len(items or [])
    elif layout == "flow":
        flow = s.get("flow")
        steps = flow.get("steps") if isinstance(flow, dict) else []
        n = len(steps or [])
    elif layout == "bars":
        bars = s.get("bars")
        items = bars.get("items") if isinstance(bars, dict) else []
        n = len(items or [])
    elif layout == "panel":
        panel = s.get("panel")
        lines = panel.get("lines") if isinstance(panel, dict) else []
        n = len(lines or [])
    eqs = len(s.get("equations") or [])
    if n >= 6 or (n >= 4 and eqs) or (layout == "matrix" and n >= 4):
        return "high"
    if n >= 4 or eqs:
        return "med"
    return "low"


def _layout_body(
    *, layout: str, vertical: bool, is_hero: bool,
    bullets_html: str, bullets_block: str, fc_block: str, img_block: str,
    stats: list, compare: dict | None, steps: list, quote: str,
    hub: dict | None = None, panel: dict | None = None,
    transform: dict | None = None, flow: dict | None = None,
    hook: dict | None = None, bars: dict | None = None,
    matrix: dict | None = None,
) -> tuple[str, str]:
    """Return (body_css_class, body_inner_html) for a slide's chosen layout.

    Each layout is a small purpose-built "template" so the deck doesn't look the
    same on every slide: number callouts for metrics, a two-column comparison,
    a numbered timeline for procedures, a spotlight for a key quote, a framed
    diagram for the process map, plus the default takeaway cards.
    """
    # Dedicated research-paper / book cover: large first page + short blurb.
    if layout == "cover" and img_block:
        return (
            ("body stack cover-body" if vertical else "body two cover-body"),
            f"{img_block}{bullets_block}",
        )

    # An explicit document image wins over generic layouts (non-rich slides).
    if img_block:
        return ("body stack" if vertical else "body two"), f"{bullets_block}{img_block}"

    if layout == "hook" and hook:
        return "body one", _render_hook(hook)

    if layout == "bars" and bars:
        return "body one", _render_bars(bars)

    if layout == "matrix" and matrix:
        return "body one", _render_matrix(matrix)

    if layout == "stat" and stats:
        cards = "".join(
            f'<div class="stat-card" style="--i:{i + 1}">'
            f'<div class="stat-value">{html.escape(str(st.get("value", "")))}</div>'
            f'<div class="stat-label">{html.escape(str(st.get("label", "")))}</div>'
            f'</div>'
            for i, st in enumerate(stats)
        )
        extra = f'<ul class="bullets compact">{bullets_html}</ul>' if bullets_html else ""
        return "body one", f'<div class="stat-grid reveal">{cards}</div>{extra}'

    if layout == "compare" and compare:
        def _col(title: str, items: list, side: str) -> str:
            lis = "".join(
                f'<li style="--i:{i + 1}">{html.escape(str(x))}</li>'
                for i, x in enumerate(items)
            )
            return (
                f'<div class="cmp-col cmp-{side}">'
                f'<div class="cmp-title">{html.escape(title)}</div>'
                f'<ul>{lis}</ul></div>'
            )
        body = (
            '<div class="compare reveal">'
            + _col(compare.get("left_title", "A"), compare.get("left", []), "left")
            + '<div class="cmp-vs">VS</div>'
            + _col(compare.get("right_title", "B"), compare.get("right", []), "right")
            + '</div>'
        )
        return "body one", body

    if layout == "steps" and steps:
        items = "".join(
            f'<li class="step" style="--i:{i + 1}">'
            f'<span class="step-num">{i + 1}</span>'
            f'<span class="step-text">{html.escape(str(t))}</span></li>'
            for i, t in enumerate(steps)
        )
        return "body one", f'<ol class="steps reveal">{items}</ol>'

    if layout == "quote" and quote:
        return "body one", (
            '<blockquote class="quote reveal">'
            '<span class="q-mark">&ldquo;</span>'
            f'<p>{html.escape(quote)}</p>'
            '</blockquote>'
        )

    if layout == "hub" and hub:
        return "body one", _render_hub(hub)

    if layout == "panel" and panel:
        return "body one", _render_panel(panel)

    if layout == "transform" and transform:
        return ("body stack" if vertical else "body one"), _render_transform(transform)

    if layout == "flow" and flow:
        return "body one", _render_flow(flow)

    if layout == "diagram" and fc_block:
        return ("body stack" if vertical else "body two"), f"{bullets_block}{fc_block}"

    # Default: takeaway cards. Hero centers them.
    if is_hero:
        return "body hero-body", bullets_block
    return "body one", bullets_block


def _render_equations(equations: list) -> str:
    """Render key LaTeX formulas as prominent cards KaTeX will typeset.

    We emit the raw TeX wrapped in ``$$…$$`` (HTML-escaped) so the client-side
    KaTeX auto-render turns each into a display equation. A ``slide-has-math``
    marker on the wrapper lets the capture worker know to wait for KaTeX.
    """
    if not equations:
        return ""
    cards = []
    for eq in equations:
        tex = str(eq.get("tex") or "").strip()
        if not tex:
            continue
        label = str(eq.get("label") or "").strip()
        label_html = f'<span class="eq-label">{html.escape(label)}</span>' if label else ""
        cards.append(
            f'<div class="eq reveal">{label_html}$${html.escape(tex)}$$</div>'
        )
    if not cards:
        return ""
    return f'<div class="eq-list slide-has-math">{"".join(cards)}</div>'


# The experimental "template-free" layout synthesizer produced chevron/stagger
# geometry that could overflow the frame. Educator decks use the predictable,
# tested layouts below; set LAYOUT_ENGINE=1 to bring the synthesizer back.
_USE_LX_ENGINE = os.environ.get("LAYOUT_ENGINE", "").strip().lower() in {"1", "true", "yes", "on"}


def render_slideshow_html(model: dict, options: dict | None = None) -> str:
    """Render a single-file HTML that shows ONE slide based on ?slide=N.

    The lecture is intentionally "designed": each slide is a themed scene with a
    kicker label, animated content cards, an optional device-framed diagram, and
    a YouTube-style caption bar that surfaces the narration on screen. The first
    slide gets a hero treatment and the last gets a recap treatment.

    No autoplay: navigation is controlled externally (capture worker) or via
    arrow keys / on-screen buttons for human preview.
    """
    spec = get_video_spec((options or {}).get("video_format"))
    theme_spec = get_theme_spec((options or {}).get("video_theme"))
    style_spec = get_style_spec((options or {}).get("video_style"))
    stok = style_spec["tokens"]
    base = theme_spec["base"]
    palettes = theme_spec["palettes"] or [{"a": "#a855f7", "b": "#8b5cf6", "glow": "#7c3aed"}]
    mer = theme_spec["mermaid"]
    # Square (1:1) reuses the vertical (stacked, single-column) layout: it reads
    # far better on a near-square canvas than the side-by-side landscape layout.
    vertical = spec["orientation"] in ("vertical", "square")
    title = html.escape(model.get("title", "Overview"))
    flowchart = model.get("flowchart", "")
    slides = model.get("slides", [])
    total = len(slides)

    # Theme palettes rotate per slide so a long lecture stays visually fresh.
    palette_count = len(palettes)

    # Template-free layout synthesizer: per-template fingerprint + per-deck
    # uniqueness registry (no two slides share a geometry signature).
    from .. import layout_engine as lx_engine
    from ..video_options import VIDEO_STYLES as _ALL_STYLES

    _style_key = str(style_spec.get("key") or "hybrid")
    _fam, _fvar = _edu_family(_style_key)
    lx_profile = lx_engine.template_profiles(list(_ALL_STYLES)).get(_style_key) or {
        "families": lx_engine.FAMILIES, "motif": "none", "htype": "plain", "tempo": 1.0,
    }
    lx_used: Counter = Counter()
    lx_sigs: set[str] = set()
    lx_last = ""
    if spec["orientation"] == "vertical":
        lx_box = (min(float(spec["width"]) - 320, 760.0), 1180.0)
    elif spec["orientation"] == "square":
        lx_box = (min(float(spec["width"]) - 320, 760.0), 520.0)
    else:
        lx_box = (float(spec["width"]) - 340, 590.0)
    lx_seed_base = f"{model.get('title', '')}|{_style_key}"

    slide_blocks = []
    last_variety = ""
    for idx, s in enumerate(slides):
        if not isinstance(s, dict):
            s = {"heading": str(s)[:80] if s else "", "narration": str(s) if s else ""}
        heading = html.escape(str(s.get("heading") or ""))
        raw_bullets = [b for b in s.get("bullets", []) if str(b).strip()]
        narration_raw = s.get("narration", "") or ""
        narration = html.escape(_display_caption(str(narration_raw)))
        is_hero = idx == 0
        is_recap = (idx == total - 1) and total > 1
        theme = idx % palette_count

        show_fc = bool(s.get("show_flowchart") and flowchart)
        active = s.get("active_node")
        fc_block = ""
        if show_fc:
            diagram = flowchart
            if active:
                diagram = (
                    diagram
                    + f"\n    style {active} fill:{mer['activeFill']},color:#fff,"
                    f"stroke:{mer['activeStroke']},stroke-width:3px"
                )
            # Store the diagram source in a data attribute and render lazily,
            # only when the slide is shown, into a unique target node. Rendering
            # hidden Mermaid (display:none) yields an empty/zero-size SVG, so we
            # must (re)render on activation.
            fc_block = (
                '<div class="device">'
                '<div class="device-bar"><span></span><span></span><span></span>'
                '<em class="device-title">process map</em></div>'
                f'<div class="diagram" data-mermaid="{html.escape(diagram)}" '
                f'data-rendered="0" id="diagram-{idx}"></div>'
                '</div>'
            )

        # Optional slide image (document first page on cover/hero).
        # ``cover`` layout always shows it; other rich layouts never do (so a
        # hook/stat opener isn't replaced by a PDF page). Plain layouts may.
        layout_early = str(s.get("layout") or "").strip().lower()
        rich_layouts = {
            "hook", "bars", "stat", "compare", "steps", "quote",
            "hub", "panel", "transform", "flow", "diagram", "matrix",
        }
        img_src = s.get("image")
        img_block = ""
        show_img = bool(img_src) and (
            layout_early == "cover" or layout_early not in rich_layouts
        )
        if show_img:
            cap = html.escape(str(s.get("image_caption") or ""))
            paper_cls = "paper is-cover" if layout_early == "cover" else "paper"
            img_block = (
                f'<figure class="{paper_cls}">'
                f'<img class="paper-img" src="{html.escape(str(img_src))}" alt="document page" '
                'loading="eager" />'
                + (f'<figcaption>{cap}</figcaption>' if cap else "")
                + '</figure>'
            )

        # Bullets become dot-marked chips (node-graph style). Recap keeps a check.
        bullet_items = []
        for bidx, b in enumerate(raw_bullets, start=1):
            if is_recap:
                marker = (
                    '<span class="b-mark check"><svg viewBox="0 0 24 24" width="12" '
                    'height="12" fill="none" stroke="currentColor" stroke-width="3" '
                    'stroke-linecap="round" stroke-linejoin="round">'
                    '<path d="M20 6 9 17l-5-5"/></svg></span>'
                )
            else:
                marker = '<span class="b-mark"></span>'
            bullet_items.append(
                f'<li style="--i:{bidx}">{marker}'
                f'<span class="b-text">{html.escape(str(b))}</span></li>'
            )
        bullets_html = "".join(bullet_items)

        # ---- choose the per-slide layout (rich, content-driven) ------------
        layout = s.get("layout") or ("diagram" if fc_block else "bullets")
        stats = s.get("stats") or []
        compare = s.get("compare")
        steps = s.get("steps") or []
        quote = s.get("quote") or ""
        if not isinstance(quote, str):
            quote = str((quote.get("text") if isinstance(quote, dict) else quote) or "")
        hub = s.get("hub")
        panel = s.get("panel")
        transform = s.get("transform")
        flow = s.get("flow")
        hook = s.get("hook")
        bars = s.get("bars")

        bullets_block = f'<div class="text reveal"><ul class="bullets">{bullets_html}</ul></div>'
        # Fan many takeaways into two columns (landscape) so the frame fills its
        # space rather than a tall single-column list. Skip on hero/vertical.
        if len(raw_bullets) >= 3 and not is_hero and not vertical:
            bullets_block = (
                f'<div class="text reveal"><ul class="bullets grid">{bullets_html}</ul></div>'
            )
        elif len(raw_bullets) >= 5 and vertical:
            bullets_block = (
                f'<div class="text reveal"><ul class="bullets compact">{bullets_html}</ul></div>'
            )

        matrix = s.get("matrix")
        compose = f"edu_{_fam}"
        variety = ""
        lx_res = None
        if not img_block and _USE_LX_ENGINE:
            lx_items, lx_kind = _lx_items_for(
                lx_engine, layout, s, raw_bullets, stats, steps, matrix, narration_raw,
            )
            if lx_items:
                lx_res = lx_engine.synthesize(
                    lx_items,
                    seed=f"{lx_seed_base}|{idx}|{s.get('heading', '')}",
                    vertical=vertical,
                    box=lx_box,
                    family_order=tuple(lx_profile["families"]),
                    used=lx_used,
                    sigs=lx_sigs,
                    last_family=lx_last,
                    kind=lx_kind,
                    recap=is_recap,
                    tempo=float(lx_profile["tempo"]),
                    forced=str(s.get("family") or ""),
                )
        if lx_res:
            lx_last = lx_res["family"]
            variety = f"lx-{lx_last}"
            body_cls, body_inner = "body one lx-body", lx_res["html"]
        elif layout in ("bullets", "cover") or (
            layout not in {
                "hook", "bars", "stat", "compare", "steps", "quote",
                "hub", "panel", "transform", "flow", "diagram", "matrix",
            }
        ):
            n_items = len(raw_bullets)
            variety = pick_bullet_variety(
                compose,
                idx,
                n_items,
                is_hero=is_hero,
                is_recap=is_recap,
                vertical=vertical,
                forced=str(s.get("variety") or ""),
                avoid=last_variety,
            )
            last_variety = variety
            rich_html = _render_bullet_variety(raw_bullets, variety, recap=is_recap)
            if rich_html and not img_block:
                body_cls, body_inner = "body one", rich_html
            else:
                body_cls, body_inner = _layout_body(
                    layout=layout,
                    vertical=vertical,
                    is_hero=is_hero,
                    bullets_html=bullets_html,
                    bullets_block=bullets_block,
                    fc_block=fc_block,
                    img_block=img_block,
                    stats=stats,
                    compare=compare,
                    steps=steps,
                    quote=quote,
                    hub=hub,
                    panel=panel,
                    transform=transform,
                    flow=flow,
                    hook=hook,
                    bars=bars,
                    matrix=matrix,
                )
        else:
            body_cls, body_inner = _layout_body(
                layout=layout,
                vertical=vertical,
                is_hero=is_hero,
                bullets_html=bullets_html,
                bullets_block=bullets_block,
                fc_block=fc_block,
                img_block=img_block,
                stats=stats,
                compare=compare,
                steps=steps,
                quote=quote,
                hub=hub,
                panel=panel,
                transform=transform,
                flow=flow,
                hook=hook,
                bars=bars,
                matrix=matrix,
            )

        # Surface key formulas from the source as display equations, appended to
        # whatever layout was chosen so math shows alongside bullets/steps/etc.
        eq_block = _render_equations(s.get("equations") or [])
        if eq_block:
            body_inner = f"{body_inner}{eq_block}"

        scene_cls = "scene"
        if is_hero:
            scene_cls += " is-hero"
        if is_recap:
            scene_cls += " is-recap"
        if layout == "hook":
            scene_cls += " is-hook"

        # Hook/quote slides hide the heading — the on-screen layout IS the title.
        hide_heading = (layout == "quote" and quote) or (layout == "hook" and hook)
        heading_html = "" if hide_heading else (
            f'<h2 class="reveal" data-anim-from="0.06" data-anim-dur="0.4">{_accent_heading(heading)}</h2>'
            f'{_H_UNDER}'
        )
        density = _slide_density(s, layout)

        # Never paint page/slide numbers on the frame — they read as UI chrome
        # in the final YouTube video.
        slide_blocks.append(
            f'<section class="slide" data-index="{idx}" data-alt="{idx % 3}" data-theme="{theme}" '
            f'data-layout="{html.escape(layout)}" data-variety="{html.escape(variety)}" data-density="{density}">'
            f'<div class="bg" aria-hidden="true"></div>'
            f'<div class="frame-orn" aria-hidden="true"></div>'
            f'{_DECOS}'
            f'{_COVER_ART if idx == 0 else ""}'
            f'{lx_engine.motif_html(f"{lx_seed_base}|{idx}", lx_profile["motif"]) if _USE_LX_ENGINE else ""}'
            f'<div class="stage-wrap">'
            f'<div class="{scene_cls}">'
            f'<div class="kicker reveal" data-anim-from="0.02" data-anim-dur="0.35">'
            f'<span class="k-chip">{title}</span>'
            f'</div>'
            f'{heading_html}'
            f'<div class="{body_cls}">{body_inner}</div>'
            f'</div>'
            f'</div>'
            f'<div class="caption" role="caption">'
            f'<p class="cap-text">{narration}</p></div>'
            f'</section>'
        )

    theme_root = (
        f"--ink:{base['ink']}; --muted:{base['muted']}; --panel:{base['panel']}; "
        f"--line:{base['line']}; --bg:{base['bg']}; --grid:{base['grid']}; "
        f"--diagram-bg:{base['diagram_bg']}; --caption-bg:{base['caption_bg']}; "
        f"--caption-text:{base['caption_text']}; "
        f"--font:{stok['font']}; --h2-font:{stok.get('h2_font', stok['font'])}; "
        f"--h2-weight:{stok['h2_weight']}; --h2-scale:{stok['h2_scale']}; "
        f"--h2-spacing:{stok['h2_spacing']}; --card-radius:{stok['card_radius']}; "
        f"--card-border:{stok['card_border']}; --card-shadow:{stok['card_shadow']}; "
        f"--panel-alpha:{stok['panel_alpha']}; --grid-opacity:{stok['grid_opacity']}; "
        f"--blob-opacity:{stok['blob_opacity']}; --kicker-transform:{stok['uppercase_kicker']};"
        f"--style-motif:{html.escape(str(stok.get('motif') or style_spec.get('motif') or style_spec.get('key') or 'hybrid'))};"
        f"--h2-max-ch:{html.escape(str(stok.get('h2_max_ch') or '20ch'))};"
        f"--body-max-ch:{html.escape(str(stok.get('body_max_ch') or '38ch'))};"
    )
    theme_palettes = "\n  ".join(
        f'.slide[data-theme="{i}"] {{ --a:{p["a"]}; --b:{p["b"]}; --glow:{p["glow"]}; }}'
        for i, p in enumerate(palettes)
    )

    from .edu_theme import EDU_CSS, EDU_FIT_JS
    from .sync import js_sync_constants

    motion_fps = int(getattr(get_settings(), "motion_fps", 24) or 24)
    style_key = html.escape(str(style_spec.get("key") or "hybrid"))
    compose = html.escape(str(
        stok.get("layout_mode")
        or style_spec.get("layout_mode")
        or "stack"
    ))
    from ..visual_layouts import generated_compose_css, motion_slideshow_css, slideshow_compose_css
    from ..video_options import VIDEO_STYLES
    return _SLIDESHOW_TEMPLATE.format(
        title=title,
        count=total,
        slides="\n".join(slide_blocks),
        body_class=("vertical" if vertical else "landscape") + " edu",
        edu_family=_fam,
        edu_font=_fvar,
        edu_css=EDU_CSS,
        edu_fit_js=EDU_FIT_JS,
        style_key=style_key,
        compose=compose,
        motion=html.escape(str(stok.get("chrome_motion") or "rise")),
        caption=html.escape(str(stok.get("chrome_caption") or "bar")),
        align=html.escape(str(stok.get("chrome_align") or "left")),
        kicker=html.escape(str(stok.get("chrome_kicker") or "left")),
        orn=html.escape(str(stok.get("chrome_orn") or "none")),
        motif=html.escape(str(lx_profile["motif"])),
        htype=html.escape(str(lx_profile["htype"])),
        lx_css=lx_engine.LX_CSS,
        lx_js=lx_engine.LX_JS,
        compose_css=slideshow_compose_css() + "\n" + generated_compose_css(VIDEO_STYLES) + "\n" + motion_slideshow_css(),
        aspect_label=html.escape(spec["aspect_ratio"]),
        platform_label=html.escape(spec["label"]),
        theme_root=theme_root,
        theme_palettes=theme_palettes,
        mermaid_theme="dark" if base.get("dark", True) else "default",
        m_primary=mer["primaryColor"],
        m_border=mer["primaryBorderColor"],
        m_text=mer["primaryTextColor"],
        m_line=mer["lineColor"],
        m_main=mer["mainBkg"],
        m_secondary=mer["secondaryColor"],
        m_tertiary=mer["tertiaryColor"],
        sync_js=js_sync_constants(motion_fps),
    )


_SLIDESHOW_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{title}</title>
<link rel="preconnect" href="https://fonts.googleapis.com" />
<link href="https://fonts.googleapis.com/css2?family=Anton&family=Archivo:wght@500;600;700;800&family=Baloo+2:wght@500;600;700&family=Barlow:wght@500;600;700;800&family=Bricolage+Grotesque:wght@500;600;700;800&family=Caveat:wght@500;600;700&family=DM+Sans:ital,opsz,wght@0,9..40,400;0,9..40,500;0,9..40,600;0,9..40,700;0,9..40,800;0,9..40,900;1,9..40,400&family=Figtree:wght@500;600;700;800&family=Fraunces:ital,opsz,wght@0,9..144,500;0,9..144,700;1,9..144,500&family=Fredoka:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&family=Instrument+Serif:ital,wght@0,400;1,400&family=Inter:wght@200;300;400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;600&family=Literata:ital,opsz,wght@0,7..72,500;0,7..72,700;1,7..72,500&family=Manrope:wght@500;600;700;800&family=Montserrat:wght@500;600;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,600;1,6..72,400&family=Nunito:wght@500;600;700;800&family=Oswald:wght@500;600;700&family=Outfit:wght@500;600;700;800&family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400;1,600&family=Plus+Jakarta+Sans:wght@500;600;700;800&family=Poppins:wght@500;600;700;800&family=Rubik:wght@500;600;700;800&family=Sora:wght@500;600;700;800&family=Space+Grotesk:wght@500;600;700&family=Space+Mono:wght@400;700&family=Syne:wght@500;600;700;800&family=Work+Sans:wght@500;600;700;800&family=Kalam:wght@400;700&family=Patrick+Hand&family=Permanent+Marker&family=Gloria+Hallelujah&family=Bangers&family=Lora:wght@500;700&display=swap" rel="stylesheet" />
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css" />
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js"></script>
<style>
  :root {{ {theme_root} }}
  * {{ box-sizing:border-box; }}
  html,body {{ margin:0; height:100%; }}
  body {{ font-family:var(--font,Inter,Segoe UI,system-ui,sans-serif); color:var(--ink); overflow:hidden; background:var(--bg); }}

  /* Each slide owns the full frame and paints its own themed background. */
  .slide {{ display:none; position:fixed; inset:0; overflow:hidden; }}
  .slide.active {{ display:block; }}
  .stage-wrap {{ position:absolute; inset:0; display:flex; align-items:center; justify-content:center; padding:52px 72px 108px; overflow:hidden; min-height:0; }}
  body.vertical .stage-wrap {{ padding:72px 44px 152px; }}

  /* Per-slide accent themes (data-theme cycles through the selected palette).
     Injected from the active video theme so colors are user-selectable. */
  {theme_palettes}

  .slide .bg {{
    position:absolute; inset:0; z-index:0;
    background:
      radial-gradient(900px 520px at 50% -12%, color-mix(in srgb, var(--glow) 30%, transparent), transparent 70%),
      radial-gradient(700px 500px at 105% 118%, color-mix(in srgb, var(--a) 12%, transparent), transparent),
      var(--bg);
  }}
  /* Subtle perspective grid gives the frame depth on video. */
  .slide .bg::before {{
    content:""; position:absolute; inset:0; opacity:var(--grid-opacity,.6);
    background-image:
      linear-gradient(to right, var(--grid) 1px, transparent 1px),
      linear-gradient(to bottom, var(--grid) 1px, transparent 1px);
    background-size:54px 54px;
    -webkit-mask-image:radial-gradient(circle at 50% 45%, #000 10%, transparent 80%);
    mask-image:radial-gradient(circle at 50% 45%, #000 10%, transparent 80%);
  }}
  .slide .bg::after {{
    content:""; position:absolute; width:560px; height:560px; right:-140px; top:-160px;
    background:radial-gradient(circle at 50% 50%, var(--glow), transparent 62%);
    opacity:var(--blob-opacity,.22); filter:blur(30px); border-radius:50%;
  }}

  .scene {{ position:relative; z-index:1; width:100%; max-width:min(1580px,96vw); max-height:100%; min-width:0; overflow:hidden; display:flex; flex-direction:column; align-items:stretch; }}
  body.vertical .scene {{ max-width:min(760px,94vw); }}

  /* Kicker label — small mono chip like the terminal-style references. */
  .kicker {{ display:flex; align-items:center; gap:10px; margin-bottom:16px; flex:none; min-width:0; }}
  .k-chip {{
    font-family:"JetBrains Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
    font-size:13px; font-weight:600; letter-spacing:.08em; text-transform:var(--kicker-transform,uppercase);
    color:var(--a); padding:6px 14px; border-radius:8px;
    background:color-mix(in srgb, var(--a) 12%, transparent);
    border:1px solid color-mix(in srgb, var(--a) 45%, transparent);
    max-width:60%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
  }}
  .k-num {{
    font-family:"JetBrains Mono",ui-monospace,monospace;
    font-size:12px; font-weight:600; letter-spacing:.06em; color:var(--muted);
    padding:5px 11px; border-radius:6px;
    background:color-mix(in srgb, var(--panel) 80%, transparent);
    border:1px solid var(--line);
  }}
  .k-step {{
    font-family:"JetBrains Mono",ui-monospace,monospace;
    font-size:13px; font-weight:500; color:var(--muted); letter-spacing:.04em;
    display:none;
  }}

  /* Headings — theme ink with a colored accent (last word tinted). Using
     var(--ink) keeps the title readable on BOTH dark and white themes. */
  .slide h2 {{
    margin:0 0 22px; font-size:calc(clamp(36px, 4.6vw, 56px) * var(--h2-scale,1)); line-height:1.08;
    font-weight:var(--h2-weight,800); letter-spacing:var(--h2-spacing,-.02em);
    font-family:var(--h2-font,var(--font)); color:var(--ink);
    overflow-wrap:anywhere; word-break:break-word; text-wrap:balance;
    max-width:min(100%, var(--h2-max-ch, 20ch));
    flex:none;
  }}
  .slide h2 .accent {{ color:var(--a); }}
  body.vertical .slide h2 {{ font-size:calc(60px * var(--h2-scale,1)); }}

  /* Body layout — fill the frame; avoid sparse empty mid-slide. */
  .body {{ display:grid; gap:22px; align-items:stretch; min-width:0; min-height:0; flex:1 1 auto; overflow:hidden; width:100%; }}
  .body.one {{ grid-template-columns:minmax(0,1fr); }}
  .body.two {{ grid-template-columns:minmax(0,1.05fr) minmax(0,1fr); gap:24px; }}
  .body.stack {{ grid-template-columns:minmax(0,1fr); }}
  .body > :only-child {{ grid-column:1 / -1; min-width:0; width:100%; max-width:100%; }}

  /* Bullet / node cards — dark chips with a thin accent border + dot. */
  .bullets {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:14px; width:100%; }}
  /* When a slide has many takeaways, fan them into two columns so the frame
     fills its space instead of a tall thin list. */
  .bullets.grid {{ display:grid; grid-template-columns:1fr 1fr; gap:14px 18px; }}
  body.vertical .bullets.grid {{ grid-template-columns:1fr; }}
  .bullets li {{
    display:flex; align-items:center; gap:16px; padding:16px 20px;
    min-height:0;
    background:color-mix(in srgb, var(--panel) calc(var(--panel-alpha,1) * 100%), transparent);
    border:var(--card-border,1px) solid var(--line); border-radius:var(--card-radius,14px);
    box-shadow:var(--card-shadow,0 10px 30px rgba(0,0,0,.4));
  }}
  .b-mark {{
    flex:none; width:13px; height:12px; border-radius:50%;
    background:var(--a); box-shadow:0 0 0 4px color-mix(in srgb, var(--a) 20%, transparent);
  }}
  .b-mark.check {{
    width:28px; height:28px; border-radius:8px; display:grid; place-items:center;
    color:var(--a); background:color-mix(in srgb, var(--a) 12%, transparent);
    box-shadow:none; border:1px solid color-mix(in srgb, var(--a) 40%, transparent);
  }}
  .b-text {{ font-size:clamp(16px, 1.35vw, 24px); line-height:1.35; color:var(--ink); font-weight:600;
    overflow-wrap:anywhere; word-break:break-word; text-wrap:pretty;
    max-width:100%; }}
  .bullets li, .mx-card, .hub-card, .flow-node, .stat-card, .cmp-col, .step {{
    min-height:0; max-width:100%;
  }}
  h2, .kicker, .cap-text, .step-text, .mx-label, .mx-detail, .hub-label, .flow-label {{
    overflow-wrap:anywhere; word-break:break-word; max-width:100%;
  }}
  body.vertical .b-text {{ font-size:29px; }}

  /* Hero scene */
  .scene.is-hero {{ text-align:center; }}
  .scene.is-hero .kicker {{ justify-content:center; }}
  .scene.is-hero h2 {{ font-size:calc(clamp(40px, 5.4vw, 68px) * var(--h2-scale,1)); margin-bottom:18px; }}
  body.vertical .scene.is-hero h2 {{ font-size:calc(clamp(36px, 7vw, 58px) * var(--h2-scale,1)); }}
  .scene.is-hero .hero-body {{ grid-template-columns:1fr; justify-items:center; }}
  .scene.is-hero .bullets {{ align-items:stretch; max-width:860px; width:100%; }}
  .scene.is-hero .bullets li {{ justify-content:flex-start; }}

  /* Device-framed diagram (dark terminal window) */
  .device {{
    border-radius:18px; overflow:hidden; background:#0e0e12;
    border:1px solid var(--line); box-shadow:0 30px 70px rgba(0,0,0,.55);
  }}
  .device-bar {{
    display:flex; align-items:center; gap:7px; padding:11px 14px;
    background:#17171c; border-bottom:1px solid var(--line);
  }}
  .device-bar span {{ width:11px; height:11px; border-radius:50%; background:#3f3f46; }}
  .device-bar span:nth-child(1) {{ background:#fb7185; }}
  .device-bar span:nth-child(2) {{ background:#fbbf24; }}
  .device-bar span:nth-child(3) {{ background:#34d399; }}
  .device-title {{ margin-left:8px; font-family:"JetBrains Mono",ui-monospace,monospace; font-size:12px; font-style:normal; font-weight:500; color:#71717a; letter-spacing:.05em; }}
  .diagram {{ display:flex; align-items:center; justify-content:center; min-height:min(240px,28vh); max-height:min(400px,42vh); padding:16px; background:var(--diagram-bg); overflow:hidden; }}
  body.vertical .diagram {{ min-height:min(200px,24vh); max-height:min(340px,36vh); }}
  .diagram svg {{ max-width:100%; height:auto; }}
  .diagram .diagram-error {{ color:#fca5a5; font-size:14px; white-space:pre-wrap; }}

  /* KaTeX math from papers. Scale display equations up so a formula reads as a
     first-class visual, and let long expressions scroll rather than clip. */
  .katex {{ font-size:1.06em; }}
  .katex-display {{ margin:.6em 0; overflow-x:auto; overflow-y:hidden; padding:2px 0; }}
  .b-text .katex, .lead .katex, .sub .katex, .quote .katex {{ font-size:1em; }}
  .eq {{ display:block; margin:14px 0; padding:16px 20px; border-radius:var(--card-radius);
    background:var(--panel); border:1px solid var(--line); text-align:center; }}
  .eq .katex-display {{ margin:0; }}
  .eq-label {{ display:block; margin-bottom:6px; font-size:13px; font-weight:600;
    letter-spacing:.04em; color:var(--muted); text-transform:uppercase; }}
  .eq-list {{ display:flex; flex-direction:column; gap:12px; width:100%; margin-top:6px; }}

  /* Framed document page (e.g. a paper/book first page on the cover slide). */
  .paper {{ margin:0; display:flex; flex-direction:column; align-items:center; gap:12px; }}
  .paper-img {{
    max-height:min(480px,52vh); max-width:100%; width:auto; border-radius:14px;
    background:#fff; border:1px solid var(--line);
    box-shadow:0 30px 70px rgba(0,0,0,.55);
  }}
  .paper.is-cover .paper-img {{
    max-height:min(520px,56vh); max-width:min(100%, 520px);
    box-shadow:0 36px 80px rgba(0,0,0,.6);
  }}
  body.vertical .paper-img {{ max-height:min(520px,48vh); }}
  body.vertical .paper.is-cover .paper-img {{ max-height:min(560px,52vh); }}
  .paper figcaption {{ font-size:14px; color:var(--muted); font-style:italic; text-align:center; max-width:90%; }}
  .cover-body .text {{ max-width:420px; }}
  .slide.active .paper {{ animation:pop-in .85s cubic-bezier(.34,1.56,.64,1) .15s both; will-change:transform; }}
  body.capture .slide.active .paper {{ animation:none !important; }}

  /* ---- Rich per-slide layouts ---- */
  /* Kinetic hook — cold-open number (tech YouTube / Cloud Codes style) */
  .scene.is-hook {{ text-align:left; max-width:1100px; }}
  .hook {{ position:relative; width:100%; padding:8px 0 4px; }}
  .hook-bar {{
    width:72px; height:6px; border-radius:999px; margin-bottom:22px;
    background:linear-gradient(90deg, var(--a), var(--b));
    box-shadow:0 0 24px color-mix(in srgb, var(--a) 55%, transparent);
  }}
  .hook-value {{
    font-size:clamp(72px, 9vw, 128px); line-height:.92; font-weight:900;
    letter-spacing:-.04em; color:var(--a);
    text-shadow:0 0 48px color-mix(in srgb, var(--a) 40%, transparent);
  }}
  body.vertical .hook-value {{ font-size:clamp(64px, 14vw, 96px); }}
  .hook-label {{
    margin-top:14px; font-family:"JetBrains Mono",ui-monospace,monospace;
    font-size:15px; font-weight:600; letter-spacing:.08em; text-transform:uppercase;
    color:var(--muted);
  }}
  .hook-punch {{
    margin:22px 0 0; max-width:34ch; font-size:clamp(22px, 2.4vw, 32px);
    line-height:1.35; font-weight:600; color:var(--ink);
  }}
  .slide.active .hook-bar {{ animation:wipe-x .55s cubic-bezier(.22,1,.36,1) both; }}
  .slide.active .hook-value {{ animation:hero-in .9s cubic-bezier(.22,1,.36,1) .08s both; }}
  .slide.active .hook-label {{ animation:rise .5s cubic-bezier(.22,1,.36,1) .22s both; }}
  .slide.active .hook-punch {{ animation:mot-clip .65s cubic-bezier(0.16,1,0.3,1) .24s both; }}

  /* Animated magnitude bars (HyperFrames-style sequence timing) */
  .bars {{ display:flex; flex-direction:column; gap:18px; width:100%; max-width:920px; }}
  .bars-title {{
    font-size:15px; font-weight:700; letter-spacing:.08em; text-transform:uppercase;
    color:var(--muted); margin-bottom:4px; font-family:"JetBrains Mono",ui-monospace,monospace;
  }}
  .bar-row {{ display:flex; flex-direction:column; gap:8px; }}
  .bar-meta {{ display:flex; justify-content:space-between; gap:12px; align-items:baseline; }}
  .bar-label {{ font-size:24px; font-weight:700; color:var(--ink); }}
  .bar-note {{ font-size:15px; color:var(--muted); font-family:"JetBrains Mono",ui-monospace,monospace; }}
  .bar-track {{
    height:20px; border-radius:999px; overflow:hidden;
    background:color-mix(in srgb, var(--panel) 85%, transparent);
    border:1px solid var(--line);
  }}
  .bar-fill {{
    height:100%; width:0; border-radius:inherit;
    background:linear-gradient(90deg, var(--a), var(--b));
    box-shadow:0 0 18px color-mix(in srgb, var(--a) 45%, transparent);
  }}
  .slide.active .bar-fill {{
    animation:bar-grow .7s cubic-bezier(.22,1,.36,1) both;
    animation-delay:calc(.18s + var(--i) * .1s);
    width:var(--w, 50%);
  }}
  @keyframes bar-grow {{ from {{ width:0; }} to {{ width:var(--w, 50%); }} }}
  @keyframes wipe-x {{ from {{ transform:scaleX(0); transform-origin:left; opacity:0; }} to {{ transform:scaleX(1); opacity:1; }} }}

  /* Stat / metric callouts */
  .stat-grid {{ display:flex; flex-wrap:wrap; gap:22px; justify-content:center; width:100%; }}
  .stat-card {{
    flex:1 1 220px; max-width:360px; text-align:center; padding:32px 28px; border-radius:20px;
    background:var(--panel);
    border:1px solid color-mix(in srgb, var(--a) 30%, var(--line)); box-shadow:0 24px 56px rgba(0,0,0,.45);
  }}
  .stat-value {{
    font-size:66px; line-height:1; font-weight:900; letter-spacing:-.03em;
    color:var(--a); text-shadow:0 0 34px color-mix(in srgb, var(--a) 45%, transparent);
  }}
  body.vertical .stat-value {{ font-size:56px; }}
  .stat-label {{ margin-top:12px; font-size:16px; font-weight:500; color:var(--muted); font-family:"JetBrains Mono",ui-monospace,monospace; letter-spacing:.03em; }}
  .bullets.compact {{ margin-top:26px; }}

  /* Two-column comparison */
  .compare {{ display:grid; grid-template-columns:minmax(0,1fr) auto minmax(0,1fr); gap:18px; align-items:stretch; width:100%; min-width:0; }}
  body.vertical .compare {{ grid-template-columns:1fr; }}
  body.vertical .compare .cmp-vs {{ display:none; }}
  .cmp-col {{
    padding:24px 24px 20px; border-radius:18px; background:var(--panel);
    border:1px solid var(--line); box-shadow:0 18px 44px rgba(0,0,0,.4);
  }}
  .cmp-left {{ border-top:3px solid var(--a); }}
  .cmp-right {{ border-top:3px solid var(--b); }}
  .cmp-title {{ font-size:22px; font-weight:800; margin-bottom:14px; color:var(--ink); }}
  .cmp-col ul {{ margin:0; padding-left:20px; list-style:none; }}
  .cmp-col li {{ font-size:19px; line-height:1.45; margin-bottom:12px; color:var(--caption-text); padding-left:18px; position:relative; }}
  .cmp-col li::before {{ content:""; position:absolute; left:0; top:10px; width:8px; height:8px; border-radius:50%; background:var(--a); }}
  .cmp-vs {{
    align-self:center; font-family:"JetBrains Mono",monospace; font-weight:700; font-size:14px; color:var(--a); width:46px; height:46px;
    display:flex; align-items:center; justify-content:center; border-radius:50%;
    background:color-mix(in srgb, var(--a) 12%, transparent); border:1px solid color-mix(in srgb, var(--a) 45%, transparent);
  }}

  /* Numbered process timeline — steps are visually linked by a connector line
     running through the number badges so the sequence reads as a flow. */
  .steps {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:14px; width:100%; max-width:1040px; }}
  .steps .step {{ display:flex; align-items:center; gap:18px; padding:18px 22px; border-radius:16px;
    background:var(--panel); border:1px solid var(--line); box-shadow:0 14px 36px rgba(0,0,0,.4);
    position:relative; }}
  /* Connector: a vertical line + arrowhead linking each step to the next. */
  .steps .step:not(:last-child)::after {{
    content:""; position:absolute; left:41px; bottom:-14px; width:2px; height:14px;
    background:linear-gradient(to bottom, color-mix(in srgb, var(--a) 60%, transparent), color-mix(in srgb, var(--a) 20%, transparent));
    z-index:0;
  }}
  .step-num {{
    flex:none; width:40px; height:40px; border-radius:12px; display:flex; align-items:center; justify-content:center;
    font-family:"JetBrains Mono",monospace; font-weight:700; font-size:17px; color:var(--a);
    background:color-mix(in srgb, var(--a) 12%, transparent); border:1px solid color-mix(in srgb, var(--a) 40%, transparent);
    position:relative; z-index:1;
  }}
  .step-text {{ font-size:22px; line-height:1.4; font-weight:600; color:var(--ink); }}
  body.vertical .step-text {{ font-size:24px; }}

  /* Quote spotlight */
  .quote {{ position:relative; margin:0 auto; max-width:1040px; text-align:center; padding:16px 24px; overflow:hidden; }}
  .quote .q-mark {{ font-size:72px; line-height:0; color:var(--a); opacity:.3; display:block; height:36px; }}
  .quote p {{
    font-size:clamp(26px, 3.4vw, 44px); line-height:1.22; font-weight:800; letter-spacing:-.02em; margin:0; color:var(--ink);
    display:-webkit-box; -webkit-line-clamp:5; -webkit-box-orient:vertical; overflow:hidden;
  }}
  .quote p .accent {{ color:var(--a); }}
  body.vertical .quote p {{ font-size:clamp(24px, 5vw, 36px); }}

  /* ---- Node-graph hub layout ------------------------------------------ */
  .hub {{ width:100%; display:flex; flex-direction:column; align-items:center; gap:26px; }}
  .hub-ring {{ position:relative; width:min(880px,74vw); height:min(400px,44vh); margin:0 auto; }}
  .hub-center {{
    position:absolute; left:50%; top:50%; transform:translate(-50%,-50%);
    min-width:180px; text-align:center; padding:20px 26px; border-radius:16px;
    background:color-mix(in srgb, var(--a) 12%, var(--panel));
    border:1px solid color-mix(in srgb, var(--a) 55%, transparent);
    box-shadow:0 0 0 6px color-mix(in srgb, var(--a) 10%, transparent), 0 24px 60px color-mix(in srgb, var(--a) 24%, transparent);
    z-index:3;
  }}
  .hub-center-label {{ font-size:28px; font-weight:800; color:var(--ink); }}
  .hub-center-sub {{ margin-top:6px; font-family:"JetBrains Mono",monospace; font-size:13px; letter-spacing:.12em; text-transform:uppercase; color:var(--a); }}
  /* Each node sits on an ellipse around the center. Chromium supports sin()/
     cos() so we place with independent x/y radii (wider than tall) and keep
     the card upright (no rotation needed). */
  .hub-node {{
    position:absolute; left:50%; top:50%; z-index:2;
    --rx:min(460px,40vw); --ry:min(230px,26vh);
    transform:translate(
      calc(cos(var(--ang)) * var(--rx) - 50%),
      calc(sin(var(--ang)) * var(--ry) - 50%)
    );
  }}
  .hub-card {{
    display:flex; flex-direction:column; gap:3px; padding:12px 14px; border-radius:12px;
    background:var(--panel); border:1px solid var(--line); box-shadow:0 14px 34px rgba(0,0,0,.42);
    white-space:normal; max-width:min(200px,28vw); text-align:center;
  }}
  .hub-label {{ font-size:17px; font-weight:700; color:var(--ink); line-height:1.25;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .hub-sub {{ font-family:"JetBrains Mono",monospace; font-size:12px; color:var(--muted); white-space:normal;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .hub-dot {{ position:absolute; left:50%; top:50%; width:9px; height:9px; border-radius:50%;
    background:var(--a); transform:translate(-50%,-50%); box-shadow:0 0 12px var(--a); }}
  /* Dashed connector from center to each node (drawn under the cards). */
  .hub-ring::before {{
    content:""; position:absolute; inset:0;
    background:
      radial-gradient(circle at 50% 50%, color-mix(in srgb, var(--a) 22%, transparent), transparent 60%);
    opacity:.5;
  }}
  .hub-node::before {{
    content:""; position:absolute; left:50%; top:50%; width:1px; height:1px;
    box-shadow:0 0 0 0 transparent;
  }}
  .hub-foot {{ display:flex; align-items:center; gap:9px; font-family:"JetBrains Mono",monospace;
    font-size:15px; color:var(--a); }}
  .hub-foot-dot {{ width:8px; height:8px; border-radius:50%; background:var(--a); box-shadow:0 0 10px var(--a); }}

  /* ---- Matrix cards (articulated parallel facts) ---------------------- */
  .matrix {{
    display:grid; grid-template-columns:repeat(var(--cols,2), minmax(0,1fr));
    gap:14px 16px; width:100%;
  }}
  body.vertical .matrix {{ grid-template-columns:1fr 1fr; gap:12px; }}
  .mx-card {{
    display:flex; flex-direction:column; gap:10px; padding:20px 20px 18px;
    border-radius:var(--card-radius,14px); background:var(--panel);
    border:1px solid var(--line); box-shadow:var(--card-shadow,0 14px 34px rgba(0,0,0,.35));
    border-top:3px solid var(--a); min-height:0; overflow:hidden;
  }}
  .mx-label {{
    font-size:21px; font-weight:800; color:var(--ink); letter-spacing:-.01em; line-height:1.25;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }}
  .mx-detail {{
    font-size:17px; line-height:1.4; color:var(--caption-text); font-weight:500;
    display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;
  }}
  body.vertical .mx-label {{ font-size:18px; }}
  body.vertical .mx-detail {{ font-size:15px; }}

  /* Density-aware type — packed slides shrink gently so content still reads large. */
  .slide[data-density="med"] h2 {{ font-size:calc(clamp(32px, 4.2vw, 48px) * var(--h2-scale,1)); margin-bottom:14px; }}
  .slide[data-density="high"] h2 {{ font-size:calc(clamp(28px, 3.6vw, 42px) * var(--h2-scale,1)); margin-bottom:10px; }}
  body.vertical .slide[data-density="med"] h2 {{ font-size:calc(clamp(30px, 5.4vw, 44px) * var(--h2-scale,1)); }}
  body.vertical .slide[data-density="high"] h2 {{ font-size:calc(clamp(26px, 4.8vw, 38px) * var(--h2-scale,1)); }}
  .slide[data-density="high"] .b-text {{ font-size:20px; }}
  body.vertical .slide[data-density="high"] .b-text {{ font-size:22px; }}
  .slide[data-density="high"] .bullets li {{ padding:10px 14px; gap:10px; min-height:0; }}
  .slide[data-density="high"] .bullets {{ gap:8px; }}
  .slide[data-density="high"] .step-text {{ font-size:18px; }}
  .slide[data-density="high"] .hub-ring {{ height:min(360px,42vh); }}
  .slide[data-density="high"] .hub-label {{ font-size:15px; }}
  .slide[data-density="high"] .mx-label {{ font-size:17px; }}
  .slide[data-density="high"] .mx-detail {{ font-size:14px; }}
  .slide[data-density="high"] .mx-card {{ min-height:0; padding:14px 16px; }}
  .bullets.compact li {{ padding:14px 16px; }}
  .bullets.compact .b-text {{ font-size:22px; line-height:1.38; }}

  /* ---- Content varieties (geometry, not palette) ---------------------- */
  .v-bento, .v-split, .v-rail, .v-agenda, .v-cards, .v-spot {{
    width:100%; min-width:0; min-height:0; max-height:100%; overflow:hidden;
  }}
  .v-t {{
    display:-webkit-box; -webkit-line-clamp:4; -webkit-box-orient:vertical;
    overflow:hidden; overflow-wrap:anywhere; word-break:break-word; min-width:0;
    font-weight:600; line-height:1.35; color:var(--ink);
  }}
  .v-bento {{
    display:grid; grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);
    grid-auto-rows:minmax(0,1fr); gap:14px; align-items:stretch;
  }}
  .v-bento .v-tile:first-child {{ grid-row:span 2; }}
  .v-bento.v-quad {{ grid-template-columns:minmax(0,1fr) minmax(0,1fr); }}
  .v-bento.v-quad .v-tile:first-child {{ grid-row:auto; }}
  body.vertical .v-bento {{ grid-template-columns:1fr; }}
  body.vertical .v-bento .v-tile:first-child {{ grid-row:auto; }}
  .v-tile {{
    display:flex; flex-direction:column; justify-content:flex-end; gap:10px;
    min-width:0; min-height:0; padding:18px 20px;
    background:color-mix(in srgb, var(--panel) calc(var(--panel-alpha,1) * 100%), transparent);
    border:var(--card-border,1px) solid var(--line); border-radius:var(--card-radius,16px);
    box-shadow:var(--card-shadow,0 12px 32px rgba(0,0,0,.28));
  }}
  .v-tile:first-child .v-t {{ font-size:clamp(22px, 2.6vw, 32px); -webkit-line-clamp:6; }}
  .v-k, .v-num, .v-idx {{
    font-size:13px; font-weight:800; letter-spacing:.08em; color:var(--a);
    font-variant-numeric:tabular-nums;
  }}
  .v-split {{ display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:18px; }}
  body.vertical .v-split {{ grid-template-columns:1fr; }}
  .v-col {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:10px; min-width:0; }}
  .v-col li, .v-agenda li {{
    display:flex; align-items:flex-start; gap:12px; padding:14px 16px; min-width:0;
    background:color-mix(in srgb, var(--panel) calc(var(--panel-alpha,1) * 100%), transparent);
    border:var(--card-border,1px) solid var(--line); border-radius:var(--card-radius,12px);
  }}
  .v-rail {{
    list-style:none; margin:0; padding:0; display:flex; gap:12px; flex-wrap:nowrap;
    width:100%; overflow:hidden;
  }}
  .v-rail li {{
    flex:1 1 0; min-width:0; display:flex; flex-direction:column; gap:10px;
    padding:16px 14px; text-align:left;
    background:color-mix(in srgb, var(--panel) calc(var(--panel-alpha,1) * 100%), transparent);
    border:var(--card-border,1px) solid var(--line); border-radius:var(--card-radius,14px);
    border-top:3px solid var(--a);
  }}
  body.vertical .v-rail {{ flex-direction:column; }}
  .v-num {{
    display:grid; place-items:center; width:36px; height:36px; flex:none;
    border-radius:10px; background:color-mix(in srgb, var(--a) 16%, transparent);
    color:var(--a); font-size:15px;
  }}
  .v-rail .v-num {{ width:28px; height:28px; font-size:13px; border-radius:999px; }}
  .v-agenda {{ list-style:none; margin:0; padding:0; display:flex; flex-direction:column; gap:10px; }}
  .v-cards {{ display:flex; flex-direction:column; gap:12px; width:min(720px,100%); }}
  .v-card {{
    display:flex; align-items:flex-start; gap:14px; padding:16px 18px; min-width:0;
    background:color-mix(in srgb, var(--panel) calc(var(--panel-alpha,1) * 100%), transparent);
    border:var(--card-border,1px) solid var(--line); border-radius:var(--card-radius,16px);
    box-shadow:var(--card-shadow,0 14px 36px rgba(0,0,0,.3));
    transform:rotate(var(--tilt,0deg));
  }}
  .v-card:nth-child(even) {{ margin-left:22px; }}
  body.vertical .v-card:nth-child(even) {{ margin-left:0; }}
  .v-spot {{ display:flex; flex-direction:column; gap:18px; width:100%; }}
  .v-lead {{
    margin:0; font-size:clamp(26px, 3.4vw, 44px); font-weight:750; line-height:1.2;
    max-width:min(100%, 22ch); overflow-wrap:anywhere;
  }}
  .v-chips {{ list-style:none; margin:0; padding:0; display:flex; flex-wrap:wrap; gap:10px; }}
  .v-chip {{
    padding:10px 16px; border-radius:999px; font-weight:650; font-size:16px;
    max-width:100%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap;
    background:color-mix(in srgb, var(--a) 12%, var(--panel));
    border:1px solid color-mix(in srgb, var(--a) 35%, var(--line)); color:var(--ink);
  }}
  .slide[data-density="high"] .v-t {{ -webkit-line-clamp:3; font-size:16px; }}
  .slide[data-density="high"] .v-lead {{ font-size:clamp(22px, 2.8vw, 34px); }}
  .slide[data-density="high"] .v-tile, .slide[data-density="high"] .v-card {{ padding:12px 14px; }}
  body.vertical .stage-wrap {{ padding:64px 40px 140px; }}
  .slide[data-density="high"] .stage-wrap {{ padding-top:36px; padding-bottom:96px; }}

  /* ---- Terminal / code panel layout ----------------------------------- */
  .panel {{
    width:min(860px,78vw); margin:0 auto; border-radius:16px; overflow:hidden;
    background:var(--panel); border:1px solid var(--line); box-shadow:0 26px 70px rgba(0,0,0,.5);
    text-align:left;
  }}
  .panel-bar {{ display:flex; align-items:center; gap:8px; padding:12px 16px;
    background:color-mix(in srgb, #000 18%, var(--panel)); border-bottom:1px solid var(--line); }}
  .panel-dot {{ width:11px; height:11px; border-radius:50%; background:color-mix(in srgb, var(--muted) 45%, transparent); }}
  .panel-dot:nth-child(1) {{ background:#ff5f57; }} .panel-dot:nth-child(2) {{ background:#febc2e; }} .panel-dot:nth-child(3) {{ background:#28c840; }}
  .panel-title {{ margin-left:8px; font-family:"JetBrains Mono",monospace; font-size:14px; font-weight:600; color:var(--ink); }}
  .panel-settings {{ margin-left:auto; font-family:"JetBrains Mono",monospace; font-size:12px; color:var(--muted); }}
  .panel-sub {{ padding:12px 20px 0; font-family:"JetBrains Mono",monospace; font-size:12px; letter-spacing:.14em; text-transform:uppercase; color:var(--muted); }}
  .panel-body {{ padding:16px 22px 22px; font-family:"JetBrains Mono",monospace; font-size:16px; line-height:1.7; }}
  .panel-body .pl {{ color:var(--ink); white-space:pre-wrap; }}
  .panel-body .pl.comment {{ color:var(--a); }}
  .panel-body .pl.cmd {{ color:#7dd3fc; }}
  .panel-caret {{ display:inline-block; width:9px; height:19px; margin-left:2px; vertical-align:-3px;
    background:var(--a); box-shadow:0 0 10px var(--a); }}
  .panel-foot {{ display:flex; align-items:center; gap:12px; padding:0 22px 20px; }}
  .panel-model {{ font-family:"JetBrains Mono",monospace; font-size:12px; letter-spacing:.14em; color:var(--muted); }}
  .panel-badge {{ font-family:"JetBrains Mono",monospace; font-size:14px; font-weight:600; color:var(--a);
    padding:5px 12px; border-radius:8px; background:color-mix(in srgb, var(--a) 12%, transparent);
    border:1px solid color-mix(in srgb, var(--a) 45%, transparent); }}

  /* ---- Before -> after transform layout (chip grid; no absolute overlap) -- */
  .transform {{ width:100%; display:flex; flex-direction:column; align-items:center; gap:22px; }}
  .tr-stage {{ display:flex; align-items:center; gap:28px; width:100%; justify-content:center; }}
  body.vertical .tr-stage {{ flex-direction:column; gap:18px; }}
  .tr-src {{ width:min(340px,30vw); padding:20px 20px 16px; border-radius:var(--card-radius,14px);
    background:color-mix(in srgb, #000 10%, var(--panel));
    border:1px solid var(--line); box-shadow:var(--card-shadow,0 18px 44px rgba(0,0,0,.35)); flex:none; }}
  body.vertical .tr-src {{ width:min(560px,82vw); }}
  .tr-src-title {{ font-family:"JetBrains Mono",monospace; font-size:13px; letter-spacing:.1em; color:var(--muted); margin-bottom:14px;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }}
  .tr-src-lines {{ display:flex; flex-direction:column; gap:8px; }}
  .tr-src-lines i {{ height:8px; border-radius:5px; background:color-mix(in srgb, var(--muted) 28%, transparent); }}
  .tr-src-lines i:nth-child(odd) {{ width:100%; }} .tr-src-lines i:nth-child(even) {{ width:72%; }}
  .tr-src-note {{ margin-top:14px; font-family:"JetBrains Mono",monospace; font-size:12px; color:var(--b); }}
  .tr-arrow {{ font-size:32px; color:var(--a); flex:none; line-height:1; }}
  .tr-dest {{
    flex:1 1 auto; min-width:min(420px,38vw); max-width:min(560px,48vw);
    display:flex; flex-direction:column; gap:14px; align-items:stretch;
  }}
  body.vertical .tr-dest {{ width:min(560px,82vw); max-width:none; min-width:0; }}
  .tr-center {{
    display:flex; align-items:center; gap:10px; padding:12px 16px;
    border-radius:var(--card-radius,12px);
    background:color-mix(in srgb, var(--a) 12%, var(--panel));
    border:1px solid color-mix(in srgb, var(--a) 45%, transparent);
  }}
  .tr-center-dot {{ width:12px; height:12px; border-radius:50%; flex:none; background:var(--a); box-shadow:0 0 14px var(--a); }}
  .tr-center-label {{
    font-size:20px; font-weight:800; color:var(--a); line-height:1.25;
    display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden;
  }}
  .tr-chips {{ display:grid; grid-template-columns:repeat(2, minmax(0,1fr)); gap:10px; }}
  .tr-chip {{
    display:flex; align-items:center; gap:10px; padding:12px 14px;
    border-radius:var(--card-radius,10px); background:var(--panel);
    border:1px solid color-mix(in srgb, var(--b) 40%, var(--line));
    min-width:0; overflow:hidden;
  }}
  .tr-dot {{
    width:10px; height:10px; border-radius:50%; flex:none;
    background:transparent; border:2px solid var(--b);
    box-shadow:0 0 10px color-mix(in srgb, var(--b) 55%, transparent);
  }}
  .tr-node-label {{
    font-family:"JetBrains Mono",monospace; font-size:18px; color:var(--ink); line-height:1.3;
    display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden; min-width:0;
  }}
  .tr-foot {{ display:flex; align-items:center; gap:9px; font-family:"JetBrains Mono",monospace; font-size:14px; color:var(--a);
    max-width:90%; text-align:center; }}
  .tr-foot-dot {{ width:8px; height:8px; border-radius:50%; flex:none; background:var(--a); box-shadow:0 0 10px var(--a); }}

  /* ---- Linked flow / pipeline layout ---------------------------------- */
  .flow {{ display:flex; align-items:stretch; justify-content:center; gap:0; width:100%; }}
  .flow-horizontal {{ flex-direction:row; flex-wrap:wrap; }}
  .flow-vertical {{ flex-direction:column; align-items:center; max-width:720px; margin:0 auto; }}
  .flow-node {{
    flex:1 1 0; min-width:168px; max-width:300px; position:relative;
    display:flex; flex-direction:column; gap:8px; padding:22px 20px 18px;
    border-radius:16px; background:var(--panel);
    border:1px solid color-mix(in srgb, var(--a) 30%, var(--line));
    box-shadow:0 16px 40px rgba(0,0,0,.4);
    min-height:112px;
  }}
  .flow-vertical .flow-node {{ width:100%; max-width:600px; flex:none; }}
  .flow-idx {{
    position:absolute; top:-14px; left:18px; width:30px; height:30px; border-radius:9px;
    display:flex; align-items:center; justify-content:center;
    font-family:"JetBrains Mono",monospace; font-weight:700; font-size:14px; color:#fff;
    background:linear-gradient(135deg,var(--a),var(--b));
    box-shadow:0 8px 18px color-mix(in srgb, var(--a) 45%, transparent);
  }}
  .flow-body {{ display:flex; flex-direction:column; gap:6px; min-width:0; }}
  .flow-label {{ display:block; font-size:26px; font-weight:800; color:var(--ink); line-height:1.2; }}
  .flow-sub {{ display:block; }}
  body.vertical .flow-label {{ font-size:24px; }}
  .flow-sub {{ font-family:"JetBrains Mono",monospace; font-size:13px; color:var(--muted); line-height:1.35; }}
  /* Connector between stages. Horizontal = arrow to the right; vertical = down. */
  .flow-arrow {{ flex:none; display:flex; align-items:center; justify-content:center; position:relative; }}
  .flow-horizontal .flow-arrow {{ width:46px; }}
  .flow-vertical .flow-arrow {{ height:34px; flex-direction:column; }}
  .flow-line {{ position:relative; background:color-mix(in srgb, var(--a) 40%, transparent); overflow:hidden; }}
  .flow-horizontal .flow-line {{ width:100%; height:3px; border-radius:2px; }}
  .flow-vertical .flow-line {{ width:3px; height:100%; border-radius:2px; }}
  .flow-pulse {{ position:absolute; border-radius:50%; background:var(--a); box-shadow:0 0 12px var(--a); }}
  .flow-horizontal .flow-pulse {{ top:50%; left:0; width:8px; height:8px; transform:translate(-4px,-50%); }}
  .flow-vertical .flow-pulse {{ left:50%; top:0; width:8px; height:8px; transform:translate(-50%,-4px); }}
  .flow-head {{ position:absolute; width:0; height:0; }}
  .flow-horizontal .flow-head {{ right:2px; border-top:5px solid transparent; border-bottom:5px solid transparent; border-left:8px solid var(--a); }}
  .flow-vertical .flow-head {{ bottom:0; border-left:5px solid transparent; border-right:5px solid transparent; border-top:8px solid var(--a); }}
  .slide.active .flow-pulse {{ animation:flow-pulse-h 1.8s ease-in-out infinite; }}
  .slide.active .flow-vertical .flow-pulse {{ animation:flow-pulse-v 1.8s ease-in-out infinite; }}
  @keyframes flow-pulse-h {{ 0% {{ left:0; opacity:0; }} 20% {{ opacity:1; }} 80% {{ opacity:1; }} 100% {{ left:100%; opacity:0; }} }}
  @keyframes flow-pulse-v {{ 0% {{ top:0; opacity:0; }} 20% {{ opacity:1; }} 80% {{ opacity:1; }} 100% {{ top:100%; opacity:0; }} }}

  .slide.active .stat-card {{ animation:pop-in .7s cubic-bezier(.34,1.56,.64,1) both; animation-delay:calc(.2s + var(--i) * .12s); }}
  .slide.active .cmp-col {{ animation:rise .6s cubic-bezier(.22,1,.36,1) .2s both; }}
  .slide.active .steps .step {{ animation:mot-rise .5s cubic-bezier(0.16,1,0.3,1) both; animation-delay:calc(.14s + var(--i) * .06s); }}
  .slide.active .quote {{ animation:pop-in .8s cubic-bezier(.34,1.56,.64,1) .15s both; }}
  .slide.active .hub-center, .slide.active .tr-center, .slide.active .tr-src {{ animation:pop-in .7s cubic-bezier(.34,1.56,.64,1) .2s both; }}
  .slide.active .hub-card, .slide.active .hub-dot {{ animation:fade-up .5s ease both; animation-delay:calc(.42s + var(--i) * .08s); }}
  .slide.active .tr-chip {{ animation:fade-up .5s ease both; animation-delay:calc(.42s + var(--i) * .08s); }}
  .slide.active .panel {{ animation:pop-in .8s cubic-bezier(.34,1.56,.64,1) .18s both; }}
  .slide.active .panel-body .pl {{ animation:rise .45s cubic-bezier(.22,1,.36,1) both; animation-delay:calc(.44s + var(--i) * .07s); }}
  .slide.active .hub-foot, .slide.active .tr-foot {{ animation:fade-up .5s ease .7s both; }}

  /* Lower-third subtitle — Remotion/broadcast style strip.
     Full narration is spoken; on-screen text is a compact readable line.
     Left accent bar replaces the old CC chip that overlapped text. */
  .caption {{
    position:absolute; left:50%; transform:translateX(-50%);
    bottom:28px; z-index:2;
    width:min(1320px, calc(100% - 96px));
    display:flex; flex-direction:column; gap:8px;
    background:linear-gradient(180deg, rgba(8,10,14,.55), rgba(8,10,14,.78));
    color:var(--caption-text);
    padding:12px 22px 12px 20px;
    border-radius:12px;
    border:1px solid color-mix(in srgb, var(--line) 70%, transparent);
    border-left:3px solid var(--a);
    box-shadow:0 12px 36px rgba(0,0,0,.42);
    backdrop-filter:blur(14px) saturate(1.1);
    min-height:0;
    box-sizing:border-box;
  }}
  body.vertical .caption {{
    bottom:48px; width:min(640px, calc(100% - 48px));
    padding:14px 20px;
  }}
  .cap-tag {{ display:none; }}
  .cap-text {{
    margin:0; flex:1 1 auto; min-width:0; width:100%;
    font-size:18px; line-height:1.42; font-weight:500;
    letter-spacing:.01em; color:var(--caption-text);
    white-space:normal;
    display:-webkit-box; -webkit-box-orient:vertical; -webkit-line-clamp:2;
    overflow:hidden; text-overflow:ellipsis;
    text-shadow:0 1px 2px rgba(0,0,0,.45);
    transform:none !important;
  }}
  body.vertical .cap-text {{ font-size:17px; -webkit-line-clamp:3; }}
  /* Progress ticks under the subtitle (HyperFrames-style beat markers). */
  .cap-ticks {{
    display:flex; gap:4px; flex:none; width:100%;
    margin:0; padding:0; justify-content:flex-start;
  }}
  .cap-ticks i {{
    flex:1; max-width:28px; height:3px; border-radius:2px;
    background:color-mix(in srgb, var(--caption-text) 22%, transparent);
  }}
  .cap-ticks i.on {{ background:var(--a); box-shadow:0 0 8px var(--a); }}

  /* Top progress bar */
  .progress {{ position:fixed; top:0; left:0; height:3px; z-index:5; width:0;
    background:linear-gradient(90deg,var(--a),var(--b)); transition:width .4s ease; box-shadow:0 0 12px var(--a); }}

  /* Brand chip (dark) */
  .brand-tag {{ position:fixed; top:18px; left:20px; z-index:5; display:flex; align-items:center; gap:9px;
    font-size:13px; font-weight:700; color:var(--ink); }}
  .brand-tag .dot {{ width:20px; height:20px; border-radius:6px; background:linear-gradient(135deg,var(--a),var(--b));
    box-shadow:0 0 16px color-mix(in srgb, var(--a) 60%, transparent); }}

  /* Entrance animations — 2026 expo-out / clip-path; data-motion overrides below. */
  .slide.active .kicker {{ animation:mot-rise .4s cubic-bezier(0.16,1,0.3,1) both; }}
  .slide.active h2 {{ animation:mot-rise .55s cubic-bezier(0.16,1,0.3,1) .06s both; }}
  .slide.active .device {{ animation:mot-scale .55s cubic-bezier(0.16,1,0.3,1) .12s both; will-change:transform; }}
  .slide.active .bullets li {{ animation:mot-rise .5s cubic-bezier(0.16,1,0.3,1) both; animation-delay:calc(.14s + var(--i) * .05s); }}
  .slide.active .b-mark {{ animation:mot-scale .4s cubic-bezier(0.16,1,0.3,1) both; animation-delay:calc(.2s + var(--i) * .05s); }}
  .slide.active .caption {{ animation:mot-rise .45s cubic-bezier(0.16,1,0.3,1) .16s both; }}
  .slide.active .cap-text {{ animation:none; }}
  .slide.active .bg::before {{ animation:none; }}
  .slide.active .bg {{ animation:ken-soft 16s cubic-bezier(0.16,1,0.3,1) both; }}
  .slide.active.is-hero h2 {{ animation:mot-clip .7s cubic-bezier(0.16,1,0.3,1) .08s both; }}
  .slide.active .diagram svg {{ animation:mot-rise .55s cubic-bezier(0.16,1,0.3,1) .28s both; }}

  @keyframes mot-rise {{ from {{ opacity:0; transform:translateY(18px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes mot-clip {{ from {{ opacity:0; clip-path:inset(0 100% 0 0); }} to {{ opacity:1; clip-path:inset(0 0 0 0); }} }}
  @keyframes mot-scale {{ from {{ opacity:0; transform:scale(.94); }} to {{ opacity:1; transform:none; }} }}
  @keyframes mot-wipe {{ from {{ opacity:0; clip-path:inset(100% 0 0 0); }} to {{ opacity:1; clip-path:inset(0 0 0 0); }} }}
  @keyframes mot-blur {{ from {{ opacity:0; filter:blur(12px); transform:translateY(10px); }} to {{ opacity:1; filter:blur(0); transform:none; }} }}
  @keyframes ken-soft {{ from {{ transform:scale(1.04); }} to {{ transform:scale(1); }} }}
  @keyframes rise {{ from {{ opacity:0; transform:translateY(18px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes rise-blur {{ from {{ opacity:0; transform:translateY(16px); filter:blur(8px); }} to {{ opacity:1; transform:none; filter:blur(0); }} }}
  @keyframes hero-in {{ from {{ opacity:0; clip-path:inset(0 100% 0 0); }} to {{ opacity:1; clip-path:inset(0 0 0 0); }} }}
  @keyframes pop-in {{ from {{ opacity:0; transform:scale(.94); }} to {{ opacity:1; transform:none; }} }}
  @keyframes card-in {{ from {{ opacity:0; transform:translateY(14px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes mark-pop {{ from {{ opacity:0; transform:scale(.6); }} to {{ opacity:1; transform:none; }} }}
  @keyframes cap-in {{ from {{ opacity:0; transform:translate(-50%,18px); }} to {{ opacity:1; transform:translate(-50%,0); }} }}
  @keyframes fade-up {{ from {{ opacity:0; transform:translateY(10px); }} to {{ opacity:1; transform:none; }} }}
  @keyframes drift {{ 0%,100% {{ transform:none; }} 50% {{ transform:translate(-12px,10px); }} }}
  @keyframes kenburns {{ from {{ transform:scale(1.04); }} to {{ transform:scale(1); }} }}
  @media (prefers-reduced-motion: reduce) {{ * {{ animation-duration:.001s !important; }} }}
  @media (max-width:900px) {{ .body.two {{ grid-template-columns:1fr; }} }}

  /* ---- Narration-synced focus -----------------------------------------
     As each item is explained the timeline adds .is-active to it and .is-dim
     to the rest, so the viewer's eye is guided to exactly what's being said.
     Applied to bullets, steps, stat cards and compare columns. */
  .sync .bullets li, .sync .steps .step, .sync .stat-card, .sync .cmp-col, .sync .flow-node,
  .sync .panel-body .pl, .sync .tr-chip, .sync .tr-node-label, .sync .bar-row, .sync .mx-card,
  .sync .v-tile, .sync .v-card, .sync .v-rail li, .sync .v-agenda li, .sync .v-col li, .sync .v-chip {{
    transition:transform .35s cubic-bezier(0.16,1,0.3,1), opacity .35s ease,
      filter .35s ease, box-shadow .35s ease, border-color .35s ease;
  }}
  .bar-row.is-active .bar-track {{
    border-color: color-mix(in srgb, var(--a) 55%, var(--line));
    box-shadow:0 0 0 1px color-mix(in srgb, var(--a) 35%, transparent);
  }}
  .bar-row.is-active .bar-label {{ color:var(--a); }}
  .sync .hub-node {{ transition:opacity .4s ease, filter .4s ease; }}
  .sync .hub-node .hub-card {{ transition:box-shadow .4s ease, border-color .4s ease; }}
  .bullets li.is-active {{ transform:translateX(6px) scale(1.03); }}
  .bullets li.is-active .b-mark {{
    background:var(--a); box-shadow:0 0 0 6px color-mix(in srgb, var(--a) 24%, transparent),
      0 0 28px color-mix(in srgb, var(--a) 80%, transparent);
    transform:scale(1.2);
  }}
  .bullets li.is-active .b-text {{ color:var(--ink); font-weight:600; }}
  .v-tile.is-active, .v-card.is-active, .v-rail li.is-active, .v-agenda li.is-active, .v-col li.is-active {{
    transform:translateY(-4px) scale(1.02);
    border-color:color-mix(in srgb, var(--a) 55%, var(--line));
    box-shadow:0 12px 28px color-mix(in srgb, var(--a) 22%, transparent);
  }}
  .v-chip.is-active {{ background:color-mix(in srgb, var(--a) 28%, var(--panel)); }}
  .steps .step.is-active, .stat-card.is-active, .cmp-col.is-active, .flow-node.is-active,
  .tr-chip.is-active, .mx-card.is-active {{
    border-color:color-mix(in srgb, var(--a) 70%, transparent);
    box-shadow:0 0 0 2px color-mix(in srgb, var(--a) 60%, transparent),
      0 22px 56px color-mix(in srgb, var(--a) 30%, transparent);
    transform:translateY(-3px) scale(1.02);
    z-index:3;
  }}
  .tr-node-label.is-active {{
    color:var(--a); font-weight:700;
  }}
  /* Hub nodes are radially positioned via transform — never override it. Glow
     the inner card + dot instead so positioning stays intact. */
  .hub-node.is-active {{ z-index:5; }}
  .hub-node.is-active .hub-card {{
    border-color:color-mix(in srgb, var(--a) 70%, transparent);
    box-shadow:0 0 0 2px color-mix(in srgb, var(--a) 60%, transparent),
      0 22px 60px color-mix(in srgb, var(--a) 34%, transparent);
  }}
  .hub-node.is-active .hub-dot {{ box-shadow:0 0 18px 4px var(--a); }}
  .panel-body .pl.is-active {{
    background:color-mix(in srgb, var(--a) 16%, transparent);
    box-shadow:inset 3px 0 0 var(--a); color:var(--ink); font-weight:600;
  }}
  .steps .step.is-active .step-num, .stat-card.is-active .stat-value {{
    color:var(--a); text-shadow:0 0 24px color-mix(in srgb, var(--a) 55%, transparent);
  }}
  .is-dim {{ opacity:.38; filter:saturate(.62) blur(.4px); transform:scale(.985); }}
  /* Hub nodes are radially transform-positioned; NEVER let the generic active/
     dim transforms override that placement — pin the radial transform and only
     vary opacity/filter (glow is handled on the inner .hub-card). */
  .hub-node.is-active, .hub-node.is-dim {{ transform:translate(
    calc(cos(var(--ang)) * var(--rx) - 50%),
    calc(sin(var(--ang)) * var(--ry) - 50%)
  ) !important; }}
  .hub-node.is-dim {{ opacity:.38; filter:saturate(.62); }}

  /* HUD (human preview only; hidden in captured frames) */
  .hud {{ position:fixed; bottom:64px; left:50%; transform:translateX(-50%); z-index:6; display:flex; gap:10px; align-items:center;
    background:rgba(20,20,23,.92); border:1px solid var(--line); border-radius:999px; padding:7px 12px;
    box-shadow:0 8px 22px rgba(0,0,0,.5); }}
  .hud button {{ border:none; background:linear-gradient(135deg,var(--a),var(--b)); color:#fff; border-radius:999px;
    width:32px; height:32px; cursor:pointer; font-size:16px; transition:transform .15s; }}
  .hud button:hover {{ transform:scale(1.08); }}
  .hud .idx {{ font-family:"JetBrains Mono",monospace; font-size:12px; color:var(--muted); min-width:52px; text-align:center; font-weight:500; }}
  body.capture .hud {{ display:none; }}
  /* Never bake chrome into captured frames (progress / brand / page nums). */
  body.capture .progress,
  body.capture .brand-tag,
  body.capture .k-num {{ display:none !important; }}
  /* During deterministic seek capture the JS frame timeline owns all motion.
     Disable the wall-clock CSS keyframe entrances so they don't fight it, and
     start animated targets hidden (the timeline reveals them at frame 0+).
     IMPORTANT: never zero .scene — it is the layout container; opacity:0 on it
     hides EVERY child even after the timeline reveals them (blank video). */
  body.capture .slide.active .kicker,
  body.capture .slide.active h2,
  body.capture .slide.active .lead,
  body.capture .slide.active .sub,
  body.capture .slide.active .device,
  body.capture .slide.active .paper,
  body.capture .slide.active .diagram,
  body.capture .slide.active .diagram svg,
  body.capture .slide.active .bullets li,
  body.capture .slide.active .v-tile,
  body.capture .slide.active .v-card,
  body.capture .slide.active .v-rail li,
  body.capture .slide.active .v-agenda li,
  body.capture .slide.active .v-col li,
  body.capture .slide.active .v-chip,
  body.capture .slide.active .v-lead,
  body.capture .slide.active .b-mark,
  body.capture .slide.active .stat-card,
  body.capture .slide.active .steps .step,
  body.capture .slide.active .cmp-col,
  body.capture .slide.active .hub-center,
  body.capture .slide.active .hub-card,
  body.capture .slide.active .hub-dot,
  body.capture .slide.active .hub-foot,
  body.capture .slide.active .panel,
  body.capture .slide.active .panel-body .pl,
  body.capture .slide.active .tr-src,
  body.capture .slide.active .tr-center,
  body.capture .slide.active .tr-chip,
  body.capture .slide.active .tr-foot,
  body.capture .slide.active .mx-card,
  body.capture .slide.active .flow-node,
  body.capture .slide.active .flow-arrow,
  body.capture .slide.active .eq,
  body.capture .slide.active .quote,
  body.capture .slide.active .hook-bar,
  body.capture .slide.active .hook-value,
  body.capture .slide.active .hook-label,
  body.capture .slide.active .hook-punch,
  body.capture .slide.active .bars-title,
  body.capture .slide.active .lx-c,
  body.capture .slide.active .lx-dot,
  body.capture .slide.active .lx-line path {{ animation:none !important; opacity:0; }}
  body.capture .slide.active .bar-row {{ animation:none !important; opacity:0; }}
  body.capture .slide.active .bar-fill {{ animation:none !important; width:0; }}
  /* Captions / ambient BG must NOT use delayed wall-clock CSS during capture —
     fill-mode:both + delay leaves them at opacity:0 for the whole screenshot
     pass (missing CC bar / drifting Ken Burns between frames).
     CRITICAL: only .caption is centered with translateX(-50%). Never apply that
     transform to .cap-text — it shifts the subtitle left and clips it. */
  body.capture .slide.active .caption {{
    animation:none !important;
    opacity:1 !important;
    transform:translateX(-50%) !important;
    filter:none !important;
  }}
  body.capture .slide.active .cap-text {{
    animation:none !important;
    opacity:1 !important;
    transform:none !important;
    filter:none !important;
  }}
  body.capture .slide.active .bg,
  body.capture .slide.active .bg::before {{
    animation:none !important;
  }}
  /* Highlight-walk states are set per seeked frame by the JS timeline. The
     wall-clock CSS transitions used in preview would only be partway applied
     when the worker screenshots immediately after seeking, making the walk look
     janky in the captured video. Disable transitions during capture so each
     frame reflects its exact .is-active / .is-dim state. */
  body.capture .sync .bullets li,
  body.capture .sync .steps .step,
  body.capture .sync .stat-card,
  body.capture .sync .cmp-col,
  body.capture .sync .flow-node,
  body.capture .sync .panel-body .pl,
  body.capture .sync .tr-chip,
  body.capture .sync .tr-node-label,
  body.capture .sync .mx-card,
  body.capture .sync .hub-node,
  body.capture .sync .hub-node .hub-card,
  body.capture .sync .bar-row {{ transition:none !important; }}
  /* The held pose after the entrance must be sharp. Blur and opacity:0 are
     only for the short draw-on, never for the frames the video sits on. */
  body.capture.settled .slide.active h2,
  body.capture.settled .slide.active .kicker,
  body.capture.settled .slide.active .paper,
  body.capture.settled .slide.active .paper-img,
  body.capture.settled .slide.active .stat-card,
  body.capture.settled .slide.active .mx-card,
  body.capture.settled .slide.active .flow-node,
  body.capture.settled .slide.active .flow-arrow,
  body.capture.settled .slide.active .hook-value,
  body.capture.settled .slide.active .hook-label,
  body.capture.settled .slide.active .hook-punch,
  body.capture.settled .slide.active .diagram,
  body.capture.settled .slide.active .diagram svg,
  body.capture.settled .slide.active .bullets li,
  body.capture.settled .slide.active .steps .step,
  body.capture.settled .slide.active .tr-src,
  body.capture.settled .slide.active .tr-dest,
  body.capture.settled .slide.active .tr-center,
  body.capture.settled .slide.active .tr-chip,
  body.capture.settled .slide.active .tr-node-label,
  body.capture.settled .slide.active .tr-src-title,
  body.capture.settled .slide.active .tr-src-note,
  body.capture.settled .slide.active .tr-foot,
  body.capture.settled .slide.active .tr-arrow,
  body.capture.settled .slide.active .hub-center,
  body.capture.settled .slide.active .hub-center-label,
  body.capture.settled .slide.active .hub-card,
  body.capture.settled .slide.active .hub-label,
  body.capture.settled .slide.active .flow-label,
  body.capture.settled .slide.active .flow-sub,
  body.capture.settled .slide.active .mx-label,
  body.capture.settled .slide.active .mx-detail {{
    opacity:1 !important; filter:none !important; animation:none !important;
  }}

  /* ---- Style skins (next-gen Zenz — unique look + larger type fit) ---- */
  /* Shared: every template gets readable type + shaped content cards. */
  body[data-style] .b-text {{ font-size:26px; line-height:1.4; font-weight:600; }}
  body.vertical[data-style] .b-text {{ font-size:28px; }}
  body[data-style] .step-text {{ font-size:22px; }}
  body[data-style] .mx-label {{ font-size:21px; }}
  body[data-style] .mx-detail {{ font-size:16px; }}
  body[data-style] .hub-label {{ font-size:19px; }}
  body[data-style] .flow-label {{ font-size:22px; }}
  body[data-style] .cmp-title {{ font-size:22px; }}
  body[data-style] .cmp-col li {{ font-size:18px; }}
  body[data-style] .cap-text {{ font-size:18px; }}
  body[data-style] .bullets li,
  body[data-style] .mx-card,
  body[data-style] .flow-node {{ min-height:0; }}
  body[data-style] .mx-card,
  body[data-style] .flow-node {{ min-height:0; }}

  /* Teach · board */
  body[data-style="whiteboard"] {{
    --font:"Caveat","DM Sans",Inter,system-ui,sans-serif;
    --h2-font:"Caveat","DM Sans",Inter,system-ui,sans-serif;
  }}
  body[data-style="whiteboard"] h2 {{
    font-family:var(--h2-font); font-weight:700; letter-spacing:-.01em;
    font-size:calc(clamp(36px, 4.8vw, 58px) * var(--h2-scale,1.05));
  }}
  body[data-style="whiteboard"] .b-text {{ font-size:30px; line-height:1.32; }}
  body.vertical[data-style="whiteboard"] .b-text {{ font-size:32px; }}
  body[data-style="whiteboard"] .step-text {{ font-size:26px; }}
  body[data-style="whiteboard"] .mx-label {{ font-size:24px; }}
  body[data-style="whiteboard"] .mx-detail {{ font-size:18px; }}
  body[data-style="whiteboard"] .hub-label {{ font-size:22px; }}
  body[data-style="whiteboard"] .hub-center-label {{ font-size:32px; }}
  body[data-style="whiteboard"] .flow-label {{ font-size:26px; }}
  body[data-style="whiteboard"] .cmp-title {{ font-size:26px; }}
  body[data-style="whiteboard"] .cmp-col li {{ font-size:20px; }}
  body[data-style="whiteboard"] .cap-text {{
    font-family:"DM Sans",Inter,system-ui,sans-serif; font-size:17px;
  }}
  body[data-style="whiteboard"] .slide .bg {{
    background:
      radial-gradient(800px 480px at 12% 8%, color-mix(in srgb, var(--a) 10%, transparent), transparent 65%),
      radial-gradient(700px 420px at 92% 88%, color-mix(in srgb, var(--b) 12%, transparent), transparent 70%),
      var(--bg);
  }}
  body[data-style="whiteboard"] .slide .bg::before {{
    opacity:.5; background-size:36px 36px;
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="whiteboard"] .slide .bg::after {{ opacity:.06; }}
  body[data-style="whiteboard"] .bullets li,
  body[data-style="whiteboard"] .mx-card,
  body[data-style="whiteboard"] .hub-card,
  body[data-style="whiteboard"] .tr-src,
  body[data-style="whiteboard"] .tr-chip,
  body[data-style="whiteboard"] .flow-node,
  body[data-style="whiteboard"] .stat-card,
  body[data-style="whiteboard"] .cmp-col {{
    border:2.5px solid color-mix(in srgb, var(--ink) 28%, var(--line));
    border-radius:8px;
    box-shadow:4px 4px 0 color-mix(in srgb, var(--ink) 12%, transparent);
    background:color-mix(in srgb, var(--panel) 94%, #fff);
  }}
  body[data-style="whiteboard"] .bullets li {{ min-height:0; padding:14px 18px; }}
  body[data-style="whiteboard"] .mx-card,
  body[data-style="whiteboard"] .flow-node {{ min-height:0; }}
  body[data-style="whiteboard"] .k-chip {{
    font-family:"Caveat",cursive; font-size:22px; letter-spacing:.02em;
    text-transform:none; border-radius:6px; border-style:dashed; font-weight:600;
  }}
  body[data-style="whiteboard"] .tr-center {{
    border:2px dashed color-mix(in srgb, var(--a) 55%, transparent);
    background:color-mix(in srgb, var(--a) 8%, var(--panel));
  }}
  body[data-style="whiteboard"] .caption {{
    border-radius:8px; border-left-width:4px;
    background:color-mix(in srgb, var(--panel) 90%, transparent);
  }}

  /* Hybrid family — channel packs */
  body[data-style="hybrid"] h2 {{ font-size:calc(60px * var(--h2-scale,1.05)); }}
  body[data-style="hybrid"] .bullets li {{
    border-left:4px solid var(--a); border-radius:14px;
  }}
  body[data-style="hybrid_kinetic"] h2 {{
    font-size:calc(62px * var(--h2-scale,1.08)); letter-spacing:-.04em;
  }}
  body[data-style="hybrid_kinetic"] .hook-value {{
    background:linear-gradient(90deg,var(--a),var(--b));
    -webkit-background-clip:text; background-clip:text; color:transparent;
  }}
  body[data-style="hybrid_data"] .stat-value {{ font-size:74px; }}
  body[data-style="hybrid_data"] .bars .bar-track {{ height:22px; }}
  body[data-style="hybrid_story"] .quote p {{ font-size:52px; font-style:italic; }}
  body[data-style="hybrid_story"] .quote .q-mark {{ opacity:.45; }}

  /* Classic teach / film */
  body[data-style="explainer"] h2 {{ font-size:calc(60px * var(--h2-scale,1.06)); }}
  body[data-style="explainer"] .bullets li {{
    border-radius:16px; border:1px solid color-mix(in srgb, var(--a) 22%, var(--line));
  }}
  body[data-style="tutorial"] .step-num {{
    width:46px; height:46px; font-size:19px; border-radius:14px;
  }}
  body[data-style="tutorial"] .step-text {{ font-size:24px; }}
  body[data-style="cinematic"] h2 {{ font-size:calc(68px * var(--h2-scale,1.12)); }}
  body[data-style="cinematic"] .b-text {{ font-size:24px; }}
  body[data-style="cinematic"] .bullets li {{
    background:transparent; border:none; box-shadow:none; padding-left:0; min-height:0;
  }}
  body[data-style="documentary"] h2 {{
    font-family:"Playfair Display",Georgia,serif; font-size:calc(58px * var(--h2-scale,1.08));
  }}
  body[data-style="documentary"] .b-text {{ font-size:24px; }}
  body[data-style="teardown"] .bullets li {{
    border-left:3px solid var(--b); border-radius:10px;
  }}
  body[data-style="modern"] h2 {{ font-size:calc(60px * var(--h2-scale,1.06)); }}
  body[data-style="bold"] h2 {{
    font-size:calc(66px * var(--h2-scale,1.12)); text-transform:uppercase; letter-spacing:.02em;
  }}
  body[data-style="bold"] .b-text {{ font-size:28px; font-weight:700; }}
  body[data-style="editorial"] h2 {{
    font-family:"Playfair Display",Georgia,serif; font-size:calc(60px * var(--h2-scale,1.1));
  }}
  body[data-style="editorial"] .b-text {{ font-size:25px; }}

  /* Blueprint / neon / terminal */
  body[data-style="blueprint"] .slide .bg::before {{
    opacity:.7; background-size:28px 28px;
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="blueprint"] h2 {{
    font-family:"JetBrains Mono",monospace; font-size:calc(48px * var(--h2-scale,1));
    letter-spacing:.04em; text-transform:uppercase;
  }}
  body[data-style="blueprint"] .b-text {{ font-size:22px; font-family:"DM Sans",sans-serif; }}
  body[data-style="blueprint"] .k-chip,
  body[data-style="blueprint"] .tr-src-title,
  body[data-style="blueprint"] .mx-detail {{
    font-family:"JetBrains Mono",monospace; letter-spacing:.06em;
  }}
  body[data-style="blueprint"] .bullets li,
  body[data-style="blueprint"] .mx-card,
  body[data-style="blueprint"] .hub-card {{
    border-radius:2px; border:1px solid color-mix(in srgb, var(--a) 45%, var(--line));
    box-shadow:none; background:color-mix(in srgb, var(--panel) 80%, transparent);
  }}
  body[data-style="neon"] .slide .bg::after {{ opacity:.45; filter:blur(40px); }}
  body[data-style="neon"] h2 {{
    font-size:calc(62px * var(--h2-scale,1.1));
    text-shadow:0 0 40px color-mix(in srgb, var(--a) 55%, transparent);
  }}
  body[data-style="neon"] .b-text {{ font-size:25px; }}
  body[data-style="neon"] .bullets li,
  body[data-style="neon"] .mx-card,
  body[data-style="neon"] .hub-card,
  body[data-style="neon"] .flow-node,
  body[data-style="neon"] .tr-chip {{
    border:1px solid color-mix(in srgb, var(--a) 55%, transparent);
    box-shadow:0 0 28px color-mix(in srgb, var(--a) 28%, transparent),
      inset 0 0 24px color-mix(in srgb, var(--a) 8%, transparent);
    background:color-mix(in srgb, var(--panel) 70%, transparent);
    backdrop-filter:blur(10px);
  }}
  body[data-style="terminal"] {{ font-variant-ligatures:none; }}
  body[data-style="terminal"] h2 {{
    font-family:"JetBrains Mono",monospace; letter-spacing:-.04em;
    font-size:calc(48px * var(--h2-scale,1));
  }}
  body[data-style="terminal"] .b-text {{
    font-family:"IBM Plex Mono",monospace; font-size:22px;
  }}
  body[data-style="terminal"] .k-chip {{
    font-family:"JetBrains Mono",ui-monospace,monospace;
    border-radius:4px; border-style:dashed;
  }}
  body[data-style="terminal"] .bullets li,
  body[data-style="terminal"] .mx-card,
  body[data-style="terminal"] .hub-card {{
    border-radius:6px; border:1px solid color-mix(in srgb, var(--a) 35%, var(--line));
    box-shadow:none; background:color-mix(in srgb, var(--panel) 92%, transparent);
  }}
  body[data-style="playful"] h2 {{
    font-family:"Fredoka","Baloo 2",sans-serif; font-size:calc(60px * var(--h2-scale,1.08));
  }}
  body[data-style="playful"] .b-text {{ font-size:26px; }}
  body[data-style="playful"] .bullets li {{ border-radius:22px; }}

  /* Decks */
  body[data-style="gamma"] h2 {{
    font-weight:750; letter-spacing:-.03em; font-size:calc(60px * var(--h2-scale,1.08));
  }}
  body[data-style="gamma"] .b-text {{ font-size:25px; }}
  body[data-style="gamma"] .bullets li,
  body[data-style="gamma"] .mx-card,
  body[data-style="gamma"] .stat-card,
  body[data-style="gamma"] .flow-node {{
    border:none; border-radius:18px;
    box-shadow:0 18px 40px color-mix(in srgb, var(--ink) 8%, transparent);
    background:color-mix(in srgb, var(--panel) 96%, #fff);
  }}
  body[data-style="gamma"] .slide .bg::before {{ opacity:.15; }}
  body[data-style="keynote"] h2 {{ font-size:calc(64px * var(--h2-scale,1.14)); font-weight:800; }}
  body[data-style="keynote"] .b-text {{ font-size:28px; }}
  body[data-style="keynote"] .bullets {{ gap:18px; }}
  body[data-style="keynote"] .bullets li {{
    background:transparent; border:none; box-shadow:none; padding-left:0; min-height:0;
  }}
  body[data-style="keynote"] .slide .bg::before {{ opacity:.12; }}
  body[data-style="slides"] h2 {{ font-size:calc(56px * var(--h2-scale,1.05)); }}
  body[data-style="slides"] .bullets li,
  body[data-style="slides"] .mx-card {{
    border-radius:4px; border-left:4px solid var(--a);
    box-shadow:0 8px 20px rgba(0,0,0,.18);
  }}
  body[data-style="notion"] h2 {{ font-size:calc(54px * var(--h2-scale,1.04)); }}
  body[data-style="notion"] .b-text {{ font-size:24px; }}
  body[data-style="notion"] .bullets li,
  body[data-style="notion"] .mx-card {{
    border-radius:8px; border:1px solid var(--line);
    box-shadow:none; background:color-mix(in srgb, var(--panel) 88%, transparent);
  }}
  body[data-style="notion"] .k-chip {{
    text-transform:none; border-radius:6px; letter-spacing:0;
    background:color-mix(in srgb, var(--a) 10%, var(--panel));
  }}
  body[data-style="minimal"] .slide .bg::before,
  body[data-style="minimal"] .slide .bg::after {{ opacity:.08; }}
  body[data-style="minimal"] h2 {{ font-size:calc(58px * var(--h2-scale,1.1)); font-weight:500; }}
  body[data-style="minimal"] .b-text {{ font-size:24px; font-weight:500; }}
  body[data-style="minimal"] .bullets li,
  body[data-style="minimal"] .mx-card {{
    border:none; box-shadow:none; background:transparent; padding-left:0; min-height:0;
  }}
  body[data-style="pitch"] h2 {{
    letter-spacing:-.035em; font-size:calc(60px * var(--h2-scale,1.08));
  }}
  body[data-style="pitch"] .bullets li {{ border-left:3px solid var(--a); border-radius:12px; }}
  body[data-style="corporate"] h2 {{ font-size:calc(56px * var(--h2-scale,1.04)); }}
  body[data-style="corporate"] .bullets li {{ border-radius:8px; border-top:2px solid var(--a); }}
  body[data-style="saas"] h2 {{ font-size:calc(58px * var(--h2-scale,1.06)); }}
  body[data-style="saas"] .bullets li {{ border-radius:16px; }}
  body[data-style="glass"] .bullets li,
  body[data-style="glass"] .mx-card,
  body[data-style="glass"] .flow-node {{
    backdrop-filter:blur(16px); background:color-mix(in srgb, var(--panel) 55%, transparent);
    border:1px solid color-mix(in srgb, #fff 18%, var(--line));
  }}
  body[data-style="cards"] .bullets li,
  body[data-style="cards"] .mx-card {{
    border-radius:20px; box-shadow:0 22px 48px rgba(0,0,0,.35);
  }}
  body[data-style="kinetic"] h2 {{
    font-size:calc(66px * var(--h2-scale,1.12)); letter-spacing:-.05em;
  }}
  body[data-style="dataviz"] .stat-value {{ font-size:72px; }}
  body[data-style="dataviz"] .bar-label {{ font-size:22px; }}
  body[data-style="device"] .device {{ border-radius:22px; }}
  body[data-style="broadcast"] .caption {{
    border-radius:0; width:min(1400px,100%); bottom:0; border-left-width:6px;
  }}
  body[data-style="broadcast"] .cap-text {{ font-size:20px; font-weight:600; }}

  /* Modern PPT */
  body[data-style="geo_navy"] .slide .bg::before {{
    opacity:.18;
    background:
      linear-gradient(135deg, color-mix(in srgb, var(--a) 55%, transparent) 0 18%, transparent 18.2%),
      linear-gradient(315deg, color-mix(in srgb, var(--b) 45%, transparent) 0 16%, transparent 16.2%),
      linear-gradient(to right, var(--grid) 1px, transparent 1px),
      linear-gradient(to bottom, var(--grid) 1px, transparent 1px);
    background-size:100% 100%, 100% 100%, 54px 54px, 54px 54px;
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="geo_navy"] h2 {{
    text-transform:uppercase; letter-spacing:.02em; font-size:calc(52px * var(--h2-scale,1.06));
  }}
  body[data-style="geo_navy"] .b-text {{ font-size:24px; }}
  body[data-style="geo_navy"] .bullets li,
  body[data-style="geo_navy"] .mx-card {{
    border-radius:12px; border:1px solid color-mix(in srgb, var(--a) 28%, var(--line));
  }}
  body[data-style="coral_split"] .slide .bg {{
    background:
      linear-gradient(105deg, color-mix(in srgb, var(--a) 18%, var(--bg)) 0 42%, transparent 42%),
      var(--bg);
  }}
  body[data-style="coral_split"] h2 {{ font-size:calc(58px * var(--h2-scale,1.06)); }}
  body[data-style="coral_split"] .bullets li,
  body[data-style="coral_split"] .stat-card,
  body[data-style="coral_split"] .flow-node {{
    border-radius:0 18px 18px 0; border-left:5px solid var(--a);
  }}
  body[data-style="coral_split"] .k-chip {{ border-radius:999px; }}
  body[data-style="blush_soft"] .slide .bg::after {{
    opacity:.28; filter:blur(48px); background:radial-gradient(circle, var(--a), transparent 60%);
  }}
  body[data-style="blush_soft"] h2 {{
    font-family:"Nunito",sans-serif; font-size:calc(58px * var(--h2-scale,1.06));
  }}
  body[data-style="blush_soft"] .bullets li {{ border-radius:24px; }}
  body[data-style="blush_soft"] .bullets li:nth-child(even) {{
    transform:translateX(8px);
  }}
  body[data-style="blush_soft"] .k-chip {{ border-radius:999px; }}
  body[data-style="mosaic"] .mx-card,
  body[data-style="mosaic"] .hub-card,
  body[data-style="mosaic"] .bullets li {{
    border-radius:4px; border:2px solid var(--ink);
    box-shadow:6px 6px 0 color-mix(in srgb, var(--a) 55%, transparent);
  }}
  body[data-style="mosaic"] h2 {{ font-size:calc(56px * var(--h2-scale,1.05)); }}
  body[data-style="process"] .flow-node,
  body[data-style="process"] .bullets li {{
    border-radius:12px; border-top:3px solid var(--a);
  }}
  body[data-style="process"] .flow-label {{ font-size:24px; }}
  body[data-style="agenda"] h2 {{ font-size:calc(58px * var(--h2-scale,1.06)); }}
  body[data-style="agenda"] .mx-card::before,
  body[data-style="agenda"] .bullets li .b-mark {{
    box-shadow:0 0 0 3px color-mix(in srgb, var(--a) 25%, transparent);
  }}
  body[data-style="rainbow_bar"] .kicker::after {{
    content:""; display:block; height:4px; width:120px; margin-left:12px; border-radius:99px;
    background:linear-gradient(90deg,var(--a),var(--b),#f59e0b,#22c55e,#06b6d4);
  }}
  body[data-style="rainbow_bar"] .bullets li,
  body[data-style="rainbow_bar"] .hub-card {{
    border-top:3px solid var(--a);
  }}
  body[data-style="circle_stack"] .flow-node,
  body[data-style="circle_stack"] .stat-card {{ border-radius:999px; text-align:center; }}
  body[data-style="circle_stack"] .bullets li {{ border-radius:999px; padding-left:28px; }}
  body[data-style="hex_grid"] .hub-card,
  body[data-style="hex_grid"] .mx-card {{
    clip-path:polygon(10% 0, 90% 0, 100% 50%, 90% 100%, 10% 100%, 0 50%);
    border:none; padding:28px 22px;
  }}
  body[data-style="wave_soft"] .slide .bg::before {{
    opacity:.35;
    background:
      radial-gradient(120% 80% at 0% 100%, color-mix(in srgb, var(--a) 22%, transparent), transparent 55%),
      radial-gradient(100% 70% at 100% 0%, color-mix(in srgb, var(--b) 18%, transparent), transparent 50%);
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="wave_soft"] .bullets li,
  body[data-style="wave_soft"] .mx-card {{ border-radius:28px 18px 28px 18px; }}

  /* Hyper · design */
  body[data-style="swiss_pulse"] .slide .bg::before {{
    opacity:.4; background-size:48px 48px;
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="swiss_pulse"] h2 {{
    font-family:"Space Grotesk",sans-serif; font-size:calc(62px * var(--h2-scale,1.1));
    letter-spacing:-.05em;
  }}
  body[data-style="swiss_pulse"] .stat-value {{ font-size:80px; letter-spacing:-.06em; }}
  body[data-style="swiss_pulse"] .bullets li,
  body[data-style="swiss_pulse"] .mx-card {{ border-radius:0; border:2px solid var(--ink); }}
  body[data-style="velvet_std"] h2 {{
    font-family:"Playfair Display",serif; font-size:calc(60px * var(--h2-scale,1.1));
  }}
  body[data-style="velvet_std"] .stage-wrap {{ padding:72px 100px 120px; }}
  body[data-style="velvet_std"] .bullets li {{
    border:none; box-shadow:none; background:transparent; border-bottom:1px solid var(--line);
    border-radius:0; min-height:0;
  }}
  body[data-style="deconstructed"] h2 {{
    font-size:calc(64px * var(--h2-scale,1.12)); transform:skewX(-4deg);
  }}
  body[data-style="deconstructed"] .bullets li,
  body[data-style="deconstructed"] .mx-card {{
    transform:rotate(-1.2deg); border:2px solid var(--ink);
  }}
  body[data-style="deconstructed"] .slide .bg::after {{
    opacity:.2; mix-blend-mode:multiply;
  }}
  body[data-style="maximalist"] h2 {{
    font-size:calc(70px * var(--h2-scale,1.14)); text-transform:uppercase; letter-spacing:-.02em;
  }}
  body[data-style="maximalist"] .b-text {{ font-size:28px; font-weight:800; }}
  body[data-style="maximalist"] .k-chip {{
    font-size:14px; border-width:2px; background:var(--a); color:#fff;
  }}
  body[data-style="data_drift"] .slide .bg::before {{
    opacity:.55; background-size:24px 24px;
    -webkit-mask-image:none; mask-image:none;
  }}
  body[data-style="data_drift"] h2 {{
    font-weight:200; letter-spacing:.06em; font-size:calc(54px * var(--h2-scale,1.05));
  }}
  body[data-style="data_drift"] .b-text {{ font-weight:400; font-size:24px; }}
  body[data-style="soft_signal"] h2 {{
    font-family:"Outfit",sans-serif; font-size:calc(58px * var(--h2-scale,1.06)); font-weight:500;
  }}
  body[data-style="soft_signal"] .bullets li {{
    border-radius:20px; background:color-mix(in srgb, var(--panel) 70%, transparent);
  }}
  body[data-style="folk_freq"] h2 {{
    font-family:"Baloo 2",sans-serif; letter-spacing:-.02em; font-size:calc(58px * var(--h2-scale,1.06));
  }}
  body[data-style="folk_freq"] .hub-card,
  body[data-style="folk_freq"] .mx-card {{
    border:2px dashed color-mix(in srgb, var(--a) 50%, var(--line));
    border-radius:16px;
  }}
  body[data-style="shadow_cut"] .slide .bg {{
    background:
      linear-gradient(135deg, color-mix(in srgb, var(--ink) 88%, #000) 0 48%, transparent 48%),
      var(--bg);
  }}
  body[data-style="shadow_cut"] h2 {{
    color:#fff; mix-blend-mode:difference; font-size:calc(62px * var(--h2-scale,1.1));
  }}

  /* Motion · Remotion */
  body[data-style="kinetic_center"] .scene {{ text-align:center; }}
  body[data-style="kinetic_center"] h2 {{
    font-size:calc(72px * var(--h2-scale,1.16)); letter-spacing:-.05em; text-align:center;
  }}
  body[data-style="kinetic_center"] .b-text {{ font-size:26px; }}
  body[data-style="lower_third"] .caption {{
    bottom:36px; border-radius:0 14px 14px 0; width:min(1100px,90%);
    border-left-width:8px;
  }}
  body[data-style="lower_third"] .cap-text {{ font-size:20px; font-weight:600; }}
  body[data-style="lower_third"] .brand-tag {{
    background:var(--a); color:#fff; border-radius:0;
  }}
  body[data-style="promo_sprint"] h2 {{ font-size:calc(64px * var(--h2-scale,1.1)); }}
  body[data-style="promo_sprint"] .hub-card {{
    border:3px solid var(--a); box-shadow:0 0 0 6px color-mix(in srgb, var(--a) 18%, transparent);
  }}
  body[data-style="caption_pop"] h2 {{
    font-size:clamp(48px, 7vw, 84px); text-align:center; letter-spacing:-.04em;
  }}
  body[data-style="caption_pop"] .scene {{ text-align:center; }}
  body[data-style="chart_race"] .bar-fill {{
    box-shadow:0 0 24px color-mix(in srgb, var(--a) 50%, transparent);
  }}
  body[data-style="chart_race"] .bar-label {{ font-size:24px; }}
  body[data-style="logo_intro"] .scene {{ text-align:center; }}
  body[data-style="logo_intro"] h2 {{ font-size:calc(68px * var(--h2-scale,1.14)); }}

  /* Content · layouts */
  body[data-style="bento"] .matrix {{
    gap:12px; grid-template-columns:repeat(4, minmax(0,1fr));
  }}
  body[data-style="bento"] .mx-card:nth-child(1) {{ grid-column:span 2; grid-row:span 2; min-height:220px; }}
  body[data-style="bento"] .mx-label {{ font-size:24px; }}
  body[data-style="big_stat"] .stat-value {{ font-size:96px; }}
  body[data-style="big_stat"] .stat-label {{ font-size:20px; }}
  body[data-style="quote_pull"] .quote p {{
    font-size:56px; border-left:6px solid var(--a); padding-left:24px; text-align:left;
  }}
  body[data-style="timeline_rail"] .flow-horizontal {{
    align-items:flex-start; gap:8px;
  }}
  body[data-style="timeline_rail"] .flow-node {{
    border-radius:12px; border-top:4px solid var(--a); min-height:140px;
  }}
  body[data-style="split_media"] .compare {{ gap:28px; }}
  body[data-style="split_media"] .cmp-col {{ min-height:280px; }}
  body[data-style="proof_duo"] .cmp-col {{
    border-radius:20px; border:2px solid var(--a);
  }}
  body[data-style="proof_duo"] .cmp-title {{ font-size:24px; }}
  body[data-style="kpi_strip"] .stat-grid {{
    display:flex; gap:14px; flex-wrap:nowrap;
  }}
  body[data-style="kpi_strip"] .stat-card {{ flex:1; text-align:center; padding:24px 16px; }}
  body[data-style="kpi_strip"] .stat-value {{ font-size:48px; }}
  body[data-style="stack_cards"] .mx-card,
  body[data-style="stack_cards"] .hub-card {{
    box-shadow:
      0 2px 0 color-mix(in srgb, var(--line) 80%, transparent),
      0 14px 28px rgba(15,23,42,.14),
      8px 8px 0 color-mix(in srgb, var(--a) 18%, transparent);
  }}
  body[data-style="stack_cards"] .mx-label {{ font-size:22px; }}

  {compose_css}
  {lx_css}
  {edu_css}

</style>
</head>
<body class="{body_class}" data-edu="{edu_family}" data-efont="{edu_font}" data-style="{style_key}" data-compose="{compose}" data-motion="{motion}" data-caption="{caption}" data-align="{align}" data-kicker="{kicker}" data-orn="{orn}" data-motif="{motif}" data-htype="{htype}">
<div class="progress" id="progress"></div>
<div class="brand-tag"><span class="dot"></span>{title}</div>

<div id="deck">
{slides}
</div>

<div class="hud">
  <button id="prev" aria-label="Previous">&#8592;</button>
  <span class="idx" id="idx"></span>
  <button id="next" aria-label="Next">&#8594;</button>
</div>

<script type="module">
  import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
  mermaid.initialize({{ startOnLoad:false, theme:"{mermaid_theme}", securityLevel:"loose",
    themeVariables:{{ primaryColor:"{m_primary}", primaryBorderColor:"{m_border}", primaryTextColor:"{m_text}",
      lineColor:"{m_line}", fontFamily:"Inter, system-ui, sans-serif", fontSize:"18px",
      mainBkg:"{m_main}", secondaryColor:"{m_secondary}", tertiaryColor:"{m_tertiary}" }},
    flowchart:{{ htmlLabels:true, curve:"basis", padding:14 }} }});

  // Wrap each slide's content in a themed background + stage so the frame is full-bleed.
  // HTML already includes .bg + .stage-wrap; keep this as a fallback for older decks.
  document.querySelectorAll('.slide').forEach((s) => {{
    if (!s.querySelector('.bg')) {{
      const bg = document.createElement('div'); bg.className = 'bg';
      s.insertBefore(bg, s.firstChild);
    }}
    if (!s.querySelector('.stage-wrap')) {{
      const wrap = document.createElement('div'); wrap.className = 'stage-wrap';
      const scene = s.querySelector('.scene');
      const caption = s.querySelector('.caption');
      if (scene) {{ wrap.appendChild(scene); s.insertBefore(wrap, caption || null); }}
    }}
  }});

  const slides = [...document.querySelectorAll('.slide')];
  const idxEl = document.getElementById('idx');
  const progressEl = document.getElementById('progress');
  const clamp = (n) => Math.max(0, Math.min(slides.length - 1, n));
  function current() {{
    const p = new URLSearchParams(location.search);
    return clamp(parseInt(p.get('slide') || '0', 10) || 0);
  }}

  async function renderDiagram(slide) {{
    const el = slide.querySelector('.diagram');
    if (!el || el.dataset.rendered === '1') return;
    const src = el.dataset.mermaid || '';
    if (!src.trim()) {{ el.dataset.rendered = '1'; return; }}
    try {{
      const id = 'mmd-' + (slide.dataset.index || '0') + '-' + Date.now();
      const {{ svg, bindFunctions }} = await mermaid.render(id, src);
      el.innerHTML = svg;
      if (bindFunctions) bindFunctions(el);
      el.dataset.rendered = '1';
    }} catch (e) {{
      el.innerHTML = '<div class="diagram-error">Flowchart could not be rendered.</div>';
      el.dataset.rendered = '1';
    }}
  }}

  // Typeset any LaTeX math (dollar and backslash-paren delimiters) inside a
  // slide so equations from papers render as real math instead of raw source.
  // KaTeX is loaded with `defer`, so wait for it (bounded) before typesetting.
  function plainMath(slide) {{
    if (!slide) return;
    slide.querySelectorAll('.eq').forEach((el) => {{
      if (el.querySelector('.katex')) return;
      el.innerHTML = el.innerHTML.replace(/\$\$([\\s\\S]+?)\$\$/g, (_, tex) => {{
        const clean = String(tex)
          .replace(/\\\\[a-zA-Z]+/g, ' ')
          .replace(/[{{}}]/g, '')
          .replace(/\\s+/g, ' ')
          .trim();
        return '<span class="eq-fallback">' + clean + '</span>';
      }});
    }});
  }}

  function renderMath(slide) {{
    if (!slide || slide.dataset.mathDone === '1') return;
    const rk = window.renderMathInElement;
    if (typeof rk !== 'function') return;  // KaTeX not ready yet; retried below
    try {{
      rk(slide, {{
        delimiters: [
          {{ left: '$$', right: '$$', display: true }},
          {{ left: '\\\\[', right: '\\\\]', display: true }},
          {{ left: '$', right: '$', display: false }},
          {{ left: '\\\\(', right: '\\\\)', display: false }},
        ],
        throwOnError: false,
        ignoredTags: ['script', 'noscript', 'style', 'textarea', 'pre', 'code'],
      }});
      slide.dataset.mathDone = '1';
    }} catch (e) {{ /* best-effort */ }}
  }}

  async function waitForKatex(maxMs) {{
    const t0 = Date.now();
    while (typeof window.renderMathInElement !== 'function') {{
      if (Date.now() - t0 > (maxMs || 4000)) return false;
      await new Promise(r => setTimeout(r, 60));
    }}
    return true;
  }}

  // ---- Frame-driven timeline (Remotion/HyperFrames-inspired) -------------
  // Motion is a pure function of a frame number so the capture worker can seek
  // deterministically: window.__seekFrame(f) positions every animated element.
  // Easing + interpolate + spring mirror Remotion's model; per-element offsets
  // (data-anim-from / data-anim-dur) mirror Sequence timing; stagger + easing
  // choices follow LottieFiles motion-design principles.
  const FPS = (window.__captureFps || 24);
  // Seconds the entrance choreography plays before the highlight walk begins.
  // Injected by the capture worker so it matches the backend's motion_seconds.
  const ENTRANCE_SECONDS = (window.__entranceSeconds || 1.0);
  // Must match app.pipeline.sync (Python sparse capture uses the same numbers).
  {sync_js}
  const easings = {{
    // Expressive, natural curves (LottieFiles-style): avoid linear motion.
    outExpo: (t) => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
    outBack: (t) => {{ const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); }},
    outCubic: (t) => 1 - Math.pow(1 - t, 3),
    inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
    outBounce: (t) => {{
      const n1 = 7.5625, d1 = 2.75;
      if (t < 1 / d1) return n1 * t * t;
      if (t < 2 / d1) {{ t -= 1.5 / d1; return n1 * t * t + 0.75; }}
      if (t < 2.5 / d1) {{ t -= 2.25 / d1; return n1 * t * t + 0.9375; }}
      t -= 2.625 / d1; return n1 * t * t + 0.984375;
    }},
    linear: (t) => t,
  }};
  function interpolate(frame, inRange, outRange, ease) {{
    const [f0, f1] = inRange, [v0, v1] = outRange;
    if (frame <= f0) return v0;
    if (frame >= f1) return v1;
    const t = (frame - f0) / (f1 - f0);
    const e = (ease || easings.outCubic)(t);
    return v0 + (v1 - v0) * e;
  }}
  // Lightweight critically-damped spring for scale/pop (frame-based, seekable).
  function spring(frame, fromF, {{ stiffness = 100, damping = 12, mass = 1 }} = {{}}) {{
    const t = Math.max(0, (frame - fromF) / FPS);
    const w0 = Math.sqrt(stiffness / mass);
    const zeta = damping / (2 * Math.sqrt(stiffness * mass));
    if (zeta < 1) {{
      const wd = w0 * Math.sqrt(1 - zeta * zeta);
      return 1 - Math.exp(-zeta * w0 * t) * (Math.cos(wd * t) + (zeta * w0 / wd) * Math.sin(wd * t));
    }}
    return 1 - Math.exp(-w0 * t) * (1 + w0 * t);
  }}

  // Build a per-slide list of animated targets with their choreography.
  // Staging inspired by Remotion sequences + Manim Write/FadeIn/GrowFromCenter:
  // title → supporting copy → visual → list items with staggered dwell.
  function buildTimeline(slide) {{
    if (!slide || slide.__timeline) return slide && slide.__timeline;
    const targets = [];
    const groups = [
      {{ sel: '.kicker', from: 0.00, dur: 0.38, kind: 'rise' }},
      {{ sel: 'h2', from: 0.05, dur: 0.48, kind: 'riseBlur' }},
      {{ sel: '.lead, .sub', from: 0.12, dur: 0.40, kind: 'rise' }},
      {{ sel: '.hook-bar', from: 0.02, dur: 0.45, kind: 'wipe' }},
      {{ sel: '.hook-value', from: 0.08, dur: 0.55, kind: 'pop' }},
      {{ sel: '.hook-label', from: 0.22, dur: 0.38, kind: 'rise' }},
      {{ sel: '.hook-punch', from: 0.32, dur: 0.45, kind: 'riseBlur' }},
      {{ sel: '.bars-title', from: 0.08, dur: 0.38, kind: 'rise' }},
      {{ sel: '.bar-row', from: 0.14, dur: 0.52, kind: 'bar', stagger: 0.10 }},
      {{ sel: '.device, .paper, .diagram', from: 0.14, dur: 0.52, kind: 'pop' }},
      {{ sel: '.bullets li', from: 0.16, dur: 0.42, kind: 'card', stagger: 0.07 }},
      {{ sel: '.v-tile, .v-card, .v-rail li, .v-agenda li, .v-col li, .v-chip', from: 0.16, dur: 0.42, kind: 'card', stagger: 0.07 }},
      {{ sel: '.v-lead', from: 0.10, dur: 0.48, kind: 'riseBlur' }},
      {{ sel: '.lx-line path', from: 0.12, dur: 0.6, kind: 'lxfly' }},
      {{ sel: '.lx-dot, .lx-c', from: 0.14, dur: 0.5, kind: 'lxfly' }},
      {{ sel: '.stat-card', from: 0.14, dur: 0.45, kind: 'pop', stagger: 0.08 }},
      {{ sel: '.steps .step', from: 0.16, dur: 0.42, kind: 'card', stagger: 0.07 }},
      {{ sel: '.cmp-col', from: 0.12, dur: 0.45, kind: 'rise', stagger: 0.10 }},
      {{ sel: '.quote', from: 0.08, dur: 0.52, kind: 'pop' }},
      {{ sel: '.hub-center, .tr-center, .tr-src', from: 0.10, dur: 0.48, kind: 'pop' }},
      {{ sel: '.hub-card, .hub-dot, .tr-chip', from: 0.20, dur: 0.40, kind: 'fade', stagger: 0.06 }},
      {{ sel: '.mx-card', from: 0.14, dur: 0.42, kind: 'card', stagger: 0.07 }},
      {{ sel: '.panel', from: 0.08, dur: 0.50, kind: 'pop' }},
      {{ sel: '.panel-body .pl', from: 0.18, dur: 0.36, kind: 'rise', stagger: 0.05 }},
      {{ sel: '.flow-node', from: 0.12, dur: 0.42, kind: 'pop', stagger: 0.09 }},
      {{ sel: '.flow-arrow', from: 0.20, dur: 0.32, kind: 'fade', stagger: 0.09 }},
      {{ sel: '.eq', from: 0.18, dur: 0.45, kind: 'pop', stagger: 0.09 }},
      {{ sel: '.hub-foot, .tr-foot', from: 0.40, dur: 0.38, kind: 'fade' }},
      {{ sel: '.b-mark', from: 0.20, dur: 0.28, kind: 'pop', stagger: 0.04 }},
      {{ sel: '.deco', from: 0.10, dur: 0.70, kind: 'p', stagger: 0.18 }},
      {{ sel: '.h-under path, h2 .accent', from: 0.30, dur: 0.60, kind: 'p' }},
      {{ sel: '.v-line path', from: 0.20, dur: 0.80, kind: 'p' }},
      {{ sel: '.caption', from: 0.28, dur: 0.42, kind: 'cap' }},
    ];
    // Each design family has its own motion language, so templates differ in
    // how they move as well as how they look.
    const FAM = document.body.dataset.edu || '';
    // One motion set per family, and a different one for each of the three slide
    // layouts (data-alt), so a deck never moves the same way slide after slide.
    const ALT = Math.max(0, Math.min(2, parseInt(slide.dataset.alt || '0', 10) || 0));
    const CARD_SET = {{
      sketch: ['tilt', 'swing', 'bounce'], notebook: ['tilt', 'rise', 'glide'],
      chalk: ['swing', 'tilt', 'bounce'], split: ['rise', 'glide', 'riseBlur'],
      magazine: ['glide', 'rise', 'slide'], band: ['drop', 'slide', 'rise'],
      glass: ['flip', 'zoom', 'pop'], bento: ['pop', 'zoom', 'flip'],
      poster: ['slide', 'stamp', 'drop'], pop: ['stamp', 'bounce', 'swing'],
      cinema: ['zoom', 'riseBlur', 'glide'], terminal: ['type', 'slide', 'type'],
    }};
    const TITLE_SET = {{
      sketch: ['tilt', 'riseBlur', 'tilt'], notebook: ['riseBlur', 'tilt', 'riseBlur'],
      chalk: ['riseBlur', 'swing', 'riseBlur'], split: ['riseBlur', 'rise', 'glide'],
      magazine: ['slide', 'riseBlur', 'drop'], band: ['slide', 'drop', 'rise'],
      glass: ['rise', 'zoom', 'riseBlur'], bento: ['drop', 'pop', 'rise'],
      poster: ['slide', 'stamp', 'drop'], pop: ['stamp', 'bounce', 'stamp'],
      cinema: ['zoom', 'riseBlur', 'zoom'], terminal: ['type', 'type', 'slide'],
    }};
    const CARD_KIND = (CARD_SET[FAM] || [])[ALT] || 'card';
    const TITLE_KIND = (TITLE_SET[FAM] || [])[ALT] || 'riseBlur';
    groups.forEach((g) => {{
      if (g.kind === 'card') g.kind = CARD_KIND;
      if (g.sel === 'h2') g.kind = TITLE_KIND;
      const els = [...slide.querySelectorAll(g.sel)];
      els.forEach((el, i) => {{
        // HyperFrames-style overrides: data-anim-from / data-anim-dur (seconds).
        const fromAttr = parseFloat(el.getAttribute('data-anim-from'));
        const durAttr = parseFloat(el.getAttribute('data-anim-dur'));
        const from = Number.isFinite(fromAttr)
          ? fromAttr
          : g.from + (g.stagger ? g.stagger * i : 0);
        const dur = Number.isFinite(durAttr) ? durAttr : g.dur;
        targets.push({{ el, from, dur, kind: g.kind }});
        el.style.willChange = 'transform, opacity, filter, width';
      }});
    }});
    slide.__timeline = targets;
    // Focusable items get highlighted one-by-one in sync with the narration.
    slide.__focus = [...slide.querySelectorAll(
      '.bullets li, .steps .step, .stat-card, .cmp-col, .hub-node, .panel-body .pl, .flow-node, .tr-chip, .bar-row, .mx-card, .v-tile, .v-card, .v-rail li, .v-agenda li, .v-col li, .v-chip, .lx-c'
    )];
    // Weight each item's dwell time by how much text it shows, so a long bullet
    // stays highlighted longer than a short one — a much closer match to the
    // narration than dividing the time evenly. Cumulative fractions in [0,1].
    const weights = slide.__focus.map((el) => {{
      const t = (el.textContent || '').trim();
      return Math.max(6, t.length);
    }});
    const wtotal = weights.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    slide.__focusCum = weights.map((w) => {{ acc += w; return acc / wtotal; }});
    slide.classList.add('sync');
    // Caption progress ticks (one per focus item) under the subtitle text.
    const cap = slide.querySelector('.caption');
    if (cap && slide.__focus.length > 1 && !cap.querySelector('.cap-ticks')) {{
      const ticks = document.createElement('span');
      ticks.className = 'cap-ticks';
      slide.__focus.forEach(() => ticks.appendChild(document.createElement('i')));
      cap.appendChild(ticks);
    }}
    return targets;
  }}

  {lx_js}
  function applyPose(t, frame) {{
    // frame is LOCAL to the slide (0-based), FPS-scaled offsets -> frames.
    const f0 = t.from * FPS;
    const f1 = f0 + t.dur * FPS;
    const op = interpolate(frame, [f0, f1], [0, 1], easings.outCubic);
    let transform = '', filter = '';
    if (t.kind === 'p') {{
      // Hand-drawn progress: paths draw themselves, marker sweeps behind words.
      const p = interpolate(frame, [f0, f1], [0, 1], easings.inOutCubic);
      t.el.style.setProperty('--p', p.toFixed(3));
      t.el.style.opacity = '1';
      return;
    }}
    if (t.kind === 'fade') {{
      // Opacity-only: for elements whose transform is layout-critical
      // (radial nodes, centered labels) so we never disturb positioning.
    }} else if (t.kind === 'rise') {{
      const y = interpolate(frame, [f0, f1], [36, 0], easings.outExpo);
      transform = `translateY(${{y}}px)`;
    }} else if (t.kind === 'riseBlur') {{
      // Manim-like Write: rise + blur clear.
      const y = interpolate(frame, [f0, f1], [40, 0], easings.outExpo);
      const b = interpolate(frame, [f0, f1], [3, 0], easings.outCubic);
      transform = `translateY(${{y}}px)`; filter = `blur(${{b}}px)`;
    }} else if (t.kind === 'card') {{
      // Glide in from the left with a slight lift + gentle overshoot scale.
      const x = interpolate(frame, [f0, f1], [-40, 0], easings.outBack);
      const y = interpolate(frame, [f0, f1], [12, 0], easings.outCubic);
      const s = 0.94 + 0.06 * interpolate(frame, [f0, f1], [0, 1], easings.outBack);
      const b = interpolate(frame, [f0, f1], [2, 0], easings.outCubic);
      transform = `translate(${{x}}px, ${{y}}px) scale(${{s}})`; filter = `blur(${{b}}px)`;
    }} else if (t.kind === 'pop') {{
      // GrowFromCenter spring (Manim / Remotion springify).
      const p = spring(frame, f0, {{ stiffness: 140, damping: 14 }});
      const s = 0.86 + 0.14 * Math.min(1.05, p);
      const y = interpolate(frame, [f0, f1], [26, 0], easings.outExpo);
      const b = interpolate(frame, [f0, f1], [2.5, 0], easings.outCubic);
      transform = `translateY(${{y}}px) scale(${{s}})`; filter = `blur(${{b}}px)`;
    }} else if (t.kind === 'tilt') {{
      // Pinned-on-the-board: swing in with a little rotation and overshoot.
      const r = interpolate(frame, [f0, f1], [-8, 0], easings.outBack);
      const y = interpolate(frame, [f0, f1], [30, 0], easings.outExpo);
      const s = 0.88 + 0.12 * interpolate(frame, [f0, f1], [0, 1], easings.outBack);
      transform = `translateY(${{y}}px) rotate(${{r}}deg) scale(${{s}})`;
    }} else if (t.kind === 'slide') {{
      const x = interpolate(frame, [f0, f1], [-140, 0], easings.outExpo);
      transform = `translateX(${{x}}px)`;
    }} else if (t.kind === 'drop') {{
      const y = interpolate(frame, [f0, f1], [-70, 0], easings.outBack);
      transform = `translateY(${{y}}px)`;
    }} else if (t.kind === 'stamp') {{
      // Stamped onto the page: big and tilted, slams down with a little overshoot.
      const k = interpolate(frame, [f0, f1], [0, 1], easings.outBack);
      const s = 1.7 - 0.7 * k;
      const r = -7 * (1 - k);
      transform = `scale(${{s}}) rotate(${{r}}deg)`;
    }} else if (t.kind === 'zoom') {{
      // Slow cinematic push-in with the blur clearing.
      const s = interpolate(frame, [f0, f1], [1.16, 1], easings.outCubic);
      const b = interpolate(frame, [f0, f1], [3, 0], easings.outCubic);
      transform = `scale(${{s}})`; filter = `blur(${{b}}px)`;
    }} else if (t.kind === 'flip') {{
      // Card flips up from the table.
      const r = interpolate(frame, [f0, f1], [-72, 0], easings.outBack);
      const y = interpolate(frame, [f0, f1], [24, 0], easings.outExpo);
      transform = `perspective(900px) translateY(${{y}}px) rotateX(${{r}}deg)`;
    }} else if (t.kind === 'swing') {{
      // Hangs from a corner and swings to rest.
      const r = interpolate(frame, [f0, f1], [14, 0], easings.outBounce);
      const y = interpolate(frame, [f0, f1], [-40, 0], easings.outExpo);
      transform = `translateY(${{y}}px) rotate(${{r}}deg)`;
    }} else if (t.kind === 'bounce') {{
      // Drops from above and bounces.
      const y = interpolate(frame, [f0, f1], [-120, 0], easings.outBounce);
      transform = `translateY(${{y}}px)`;
    }} else if (t.kind === 'glide') {{
      // Long, calm slide in from the right.
      const x = interpolate(frame, [f0, f1], [90, 0], easings.outExpo);
      const b = interpolate(frame, [f0, f1], [2, 0], easings.outCubic);
      transform = `translateX(${{x}}px)`; filter = `blur(${{b}}px)`;
    }} else if (t.kind === 'type') {{
      // Typed in from the left: a clip reveal, no squashing of the text.
      const w = interpolate(frame, [f0, f1], [0, 100], easings.outCubic);
      t.el.style.clipPath = `inset(-8px ${{100 - w}}% -8px -8px)`;
    }} else if (t.kind === 'lxfly') {{
      const pose = lxPose(t, frame, f0, f1);
      transform = pose.transform; filter = pose.filter;
    }} else if (t.kind === 'wipe') {{
      const sx = interpolate(frame, [f0, f1], [0, 1], easings.outExpo);
      transform = `scaleX(${{sx}})`;
      t.el.style.transformOrigin = 'left center';
    }} else if (t.kind === 'cap') {{
      // Lower-third must keep translateX(-50%) for centering.
      const y = interpolate(frame, [f0, f1], [24, 0], easings.outExpo);
      transform = `translate(-50%, ${{y}}px)`;
    }} else if (t.kind === 'bar') {{
      // Grow the fill child seek-safely (Remotion-style pure function of frame).
      const fill = t.el.querySelector('.bar-fill');
      const targetW = fill
        ? (getComputedStyle(fill).getPropertyValue('--w') || '50%').trim()
        : '50%';
      const pct = parseFloat(targetW) || 50;
      const w = interpolate(frame, [f0, f1], [0, pct], easings.outCubic);
      if (fill) fill.style.width = w + '%';
      const y = interpolate(frame, [f0, f1], [18, 0], easings.outExpo);
      transform = `translateY(${{y}}px)`;
    }}
    // Drop residual blur before the entrance finishes so a held frame stays readable.
    if (filter && frame >= f0 + (f1 - f0) * 0.72) filter = '';
    // Once the entrance is fully settled, clear inline transform/filter so the
    // CSS highlight states (.is-active / .is-dim) can drive motion instead.
    // Opacity stays explicit (set to 1) because body.capture starts targets at
    // opacity:0; the highlight walk in seekSlide adjusts focus-item opacity.
    if (frame >= f1) {{
      if (t.kind === 'cap') {{
        t.el.style.transform = 'translateX(-50%)';
      }} else {{
      t.el.style.transform = '';
      }}
      t.el.style.filter = '';
      t.el.style.opacity = '1';
      if (t.kind === 'type') t.el.style.clipPath = '';
      if (t.kind === 'bar') {{
        const fill = t.el.querySelector('.bar-fill');
        if (fill) {{
          const targetW = (getComputedStyle(fill).getPropertyValue('--w') || '50%').trim();
          fill.style.width = targetW;
        }}
      }}
    }} else {{
      t.el.style.opacity = String(Math.max(0, Math.min(1, op)));
      t.el.style.transform = transform;
      t.el.style.filter = filter;
    }}
  }}

  function seekSlide(slide, frame, totalFrames) {{
    const targets = buildTimeline(slide);
    if (!targets) return;
    slide.style.setProperty('--tt', (frame / FPS).toFixed(3));
    targets.forEach((t) => applyPose(t, frame));
    // Ambient drift on hero/background scenes: slow, subtle, seek-safe.
    const amb = slide.querySelector('.scene .drift, .bg-orb');
    if (amb && totalFrames) {{
      const phase = (frame / totalFrames) * Math.PI * 2;
      amb.style.transform = `translate(${{Math.sin(phase) * 18}}px, ${{Math.cos(phase) * 14}}px)`;
    }}
    // Seek-safe Ken Burns (CSS keyframes are disabled during capture).
    const bg = slide.querySelector('.bg');
    if (bg && totalFrames > 1) {{
      const t = Math.min(1, Math.max(0, frame / totalFrames));
      const ease = easings.outCubic(t);
      const scale = 1.07 - 0.07 * ease;
      bg.style.transform = `scale(${{scale}})`;
      bg.style.transformOrigin = '50% 45%';
    }}
    // ---- Narration-synced highlight walk -------------------------------
    // After a SHORT entrance settles, step the "focus" through each item so the
    // active bullet/step/stat matches what the voice-over is explaining. The
    // narration starts at t=0, so we keep the lead-in small (the entrance is
    // mostly done within ~0.8s) and give the walk a tiny anticipation lead so
    // the highlight lands on an item slightly BEFORE the voice finishes the
    // previous one — this reads as "in sync" far better than lagging behind.
    const focus = slide.__focus || [];
    if (focus.length && totalFrames > 0) {{
      // Audio is the master clock; visuals scrub to the same normalized t.
      // Lead/anticipation MUST match Python ``sync.focus_lead_frames``.
      const lead = Math.min(totalFrames * SYNC.leadFrac, SYNC.leadMaxSec * FPS);
      let activeIdx = -1;
      if (frame >= lead && totalFrames > lead + 1) {{
        const raw = (frame - lead) / (totalFrames - lead);
        const prog = Math.min(0.999, raw + SYNC.anticipation);
        const cum = slide.__focusCum || [];
        activeIdx = cum.findIndex((c) => prog < c);
        if (activeIdx < 0) activeIdx = focus.length - 1;
      }} else if (frame >= lead * 0.5) {{
        activeIdx = 0;
      }}
      focus.forEach((el, i) => {{
        const active = i === activeIdx;
        const dim = activeIdx >= 0 && !active;
        el.classList.toggle('is-active', active);
        el.classList.toggle('is-dim', dim);
        // Synthesized cells fade in during their entrance; don't force them opaque.
        if (el.__lxEnd && frame < el.__lxEnd) return;
        // Explicit opacity beats the body.capture opacity:0 rule once revealed.
        el.style.opacity = dim ? '0.42' : '1';
        // Nested marks inherit parent opacity; clear leftover CSS animation state.
        el.querySelectorAll('.b-mark').forEach((m) => {{
          m.style.opacity = '1';
          m.style.transform = '';
          m.style.filter = '';
        }});
      }});
      const ticks = slide.querySelectorAll('.cap-ticks i');
      ticks.forEach((t, i) => t.classList.toggle('on', activeIdx >= 0 && i <= activeIdx));
    }}
    // Keep the narration caption strip visible for every captured frame.
    const cap = slide.querySelector('.caption');
    if (cap) {{
      cap.style.opacity = '1';
      // Preserve Y offset only while entrance is mid-flight; otherwise center.
      if (!cap.style.transform || !cap.style.transform.includes('translate(-50%')) {{
        cap.style.transform = 'translateX(-50%)';
      }}
      const ct = cap.querySelector('.cap-text');
      if (ct) {{ ct.style.opacity = '1'; ct.style.transform = 'none'; }}
    }}
  }}

  // Capture worker entry point: position the active slide at an absolute frame.
  // Also used to render the settled final pose (seek to the last frame).
  window.__settleFrame = () => {{
    const s = slides.find((x) => x.classList.contains('active'));
    if (!s) return;
    const reveal = 'h2, .kicker, .paper, .paper-img, .stat-card, .stat-value, .stat-label, .mx-card, .mx-label, .mx-detail, .flow-node, .flow-label, .flow-sub, .flow-arrow, .hook-value, .hook-label, .hook-punch, .diagram, .diagram svg, .lead, .sub, .steps .step, .bullets li, .v-t, .tr-src, .tr-dest, .tr-center, .tr-chip, .tr-node-label, .tr-src-title, .tr-src-note, .tr-foot, .tr-arrow, .hub-center, .hub-center-label, .hub-center-sub, .hub-card, .hub-label, .hub-sub';
    s.querySelectorAll(reveal).forEach((el) => {{
      if (el.classList.contains('is-dim') || el.closest('.is-dim')) return;
      el.style.opacity = '1';
      if ((el.style.filter || '').includes('blur')) el.style.filter = 'none';
    }});
    s.querySelectorAll('.deco, .deco path, .h-under path, h2 .accent').forEach((el) => {{
      el.style.setProperty('--p', '1');
      el.style.opacity = '1';
    }});
  }};

  window.__seekFrame = (frame, totalFrames) => {{
    const s = slides.find((x) => x.classList.contains('active'));
    if (!s) return;
    const f = Math.max(0, frame | 0);
    const total = totalFrames | 0;
    seekSlide(s, f, total);
    const entrance = Number(window.__entranceSeconds || 1.6);
    if (FPS > 0 && f / FPS >= entrance - 0.05) window.__settleFrame();
  }};

  {edu_fit_js}

  async function show(n) {{
    n = clamp(n);
    slides.forEach((s, k) => s.classList.toggle('active', k === n));
    idxEl.textContent = (n + 1) + ' / ' + slides.length;
    if (progressEl) progressEl.style.width = ((n + 1) / slides.length * 100) + '%';
    window.__slideReady = false;
    await renderDiagram(slides[n]);
    // Typeset LaTeX math before signaling ready so captured frames show real
    // equations (KaTeX loads deferred; wait a bounded time for it).
    if (slides[n].querySelector('.slide-has-math, .math')
        || (slides[n].textContent || '').indexOf('$') !== -1) {{
      const katexReady = await waitForKatex(4000);
      if (!katexReady) plainMath(slides[n]);
    }}
    renderMath(slides[n]);
    // Ensure any images on this slide (e.g. the document cover page) are fully
    // decoded before we signal capture-ready, so screenshots aren't blank.
    try {{
      const imgs = [...slides[n].querySelectorAll('img')];
      await Promise.all(imgs.map(im => (im.complete && im.naturalWidth)
        ? Promise.resolve()
        : (im.decode ? im.decode().catch(() => {{}})
          : new Promise(r => {{ im.onload = im.onerror = r; }}))));
    }} catch (e) {{ /* best-effort */ }}
    // In seek-capture mode, motion is driven deterministically by
    // window.__seekFrame; CSS keyframe entrances (wall-clock) are disabled via
    // body.capture so they don't fight the timeline. Build the timeline and
    // reset to frame 0 so the worker can seek from a known state.
    try {{ lxFit(slides[n]); }} catch (e) {{ /* best-effort */ }}
    try {{ await eduFit(slides[n]); }} catch (e) {{ /* best-effort */ }}
    if (document.body.classList.contains('capture')) {{
      buildTimeline(slides[n]);
      window.__seekFrame(0, 1);
    }} else {{
      // Interactive/preview: let the CSS entrance animations play, then settle.
      await new Promise(r => setTimeout(r, 1100));
    }}
    window.__slideReady = true;
  }}

  // Exposed for the headless capture worker and keyboard nav.
  window.gotoSlide = (n) => show(n);
  window.slideCount = slides.length;
  // Capture worker hides the HUD by adding .capture to <body>. It also disables
  // CSS keyframe entrances so the frame-driven timeline is the single source of
  // truth for motion during deterministic seek capture.
  window.enterCaptureMode = () => document.body.classList.add('capture');
  document.getElementById('next').onclick = () => {{ const u = new URL(location); u.searchParams.set('slide', clamp(current() + 1)); location.href = u; }};
  document.getElementById('prev').onclick = () => {{ const u = new URL(location); u.searchParams.set('slide', clamp(current() - 1)); location.href = u; }};
  document.addEventListener('keydown', e => {{ if (e.key === 'ArrowRight') document.getElementById('next').click(); if (e.key === 'ArrowLeft') document.getElementById('prev').click(); }});

  // Interactive preview: keep the --tt clock running so ambient doodles drift.
  if (!document.body.classList.contains('capture')) {{
    const t0 = performance.now();
    (function loop() {{
      const a = slides.find((x) => x.classList.contains('active'));
      if (a && !document.body.classList.contains('capture')) a.style.setProperty('--tt', ((performance.now() - t0) / 1000).toFixed(3));
      requestAnimationFrame(loop);
    }})();
  }}

  show(current());
</script>
</body>
</html>
"""


def generate_animated_html(
    raw_text: str, out_path: Path, options: dict | None = None,
    cover_image: str | None = None,
) -> tuple[dict, bool]:
    """Build the slide model, render+write the HTML, return (model, used_llm)."""
    opts = options if isinstance(options, dict) else {}
    model, used_llm = build_slide_model(raw_text, opts, cover_image)
    html_str = render_slideshow_html(model, opts)
    out_path.write_text(html_str, encoding="utf-8")
    return model, used_llm


# --------------------------------------------------------------- narration ----

def derive_narration(raw_text: str) -> str:
    """Full-lesson narration (kept for the editable-text UI / fallback engine)."""
    model, _ = build_slide_model(raw_text)
    return "\n\n".join(s["narration"] for s in model["slides"]).strip()
