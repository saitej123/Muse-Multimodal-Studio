"""Age group + knowledge-level audience for slide generation.

Studio can pick an age group and a knowledge/understanding level, which loads a
custom teaching prompt. Pasting a prompt can also infer those two selects.
"""
from __future__ import annotations

import re
from typing import Any

AGE_GROUPS: dict[str, dict[str, str]] = {
    "auto": {
        "label": "Auto — from document or prompt",
        "short": "inferred audience",
        "hint": "Infer who this is for from the source (or from a pasted prompt).",
        "years": "",
    },
    "kids": {
        "label": "Kids (5–8)",
        "short": "young children ages 5–8",
        "hint": "Playful, concrete, tiny words. Stories and pictures over jargon.",
        "years": "5-8",
    },
    "tweens": {
        "label": "Tweens (9–12)",
        "short": "tweens ages 9–12",
        "hint": "Curious and hands-on. Analogies, challenges, no talking-down.",
        "years": "9-12",
    },
    "teens": {
        "label": "Teens (13–17)",
        "short": "teenagers ages 13–17",
        "hint": "Direct, slightly witty, real-world stakes. Respect their intelligence.",
        "years": "13-17",
    },
    "young_adults": {
        "label": "Young adults (18–24)",
        "short": "young adults 18–24",
        "hint": "Career-curious, practical, a bit informal. Show why it matters now.",
        "years": "18-24",
    },
    "adults": {
        "label": "Adults",
        "short": "adult learners",
        "hint": "Clear, warm, time-efficient. Skip filler; keep the ‘so what’.",
        "years": "25+",
    },
    "professionals": {
        "label": "Professionals",
        "short": "working professionals",
        "hint": "Practitioners. Trade-offs, named tools, decisions they can use Monday.",
        "years": "25+",
    },
    "all_ages": {
        "label": "All ages / family",
        "short": "a mixed-age family audience",
        "hint": "Plain language that kids can follow and adults still find sharp.",
        "years": "",
    },
}

KNOWLEDGE_LEVELS: dict[str, dict[str, str]] = {
    "auto": {
        "label": "Auto — from document or prompt",
        "short": "inferred prior knowledge",
        "hint": "Infer how much they already know from the source (or pasted prompt).",
    },
    "beginner": {
        "label": "Beginner",
        "short": "complete beginners",
        "hint": "First principles. Define every term. Analogies before formalism.",
    },
    "intermediate": {
        "label": "Intermediate",
        "short": "learners with some background",
        "hint": "Assume the basics. Unpack new mechanisms; skip ‘what is a computer’.",
    },
    "advanced": {
        "label": "Advanced",
        "short": "advanced learners",
        "hint": "Skip 101. Go into mechanisms, edge cases, and why alternatives fail.",
    },
    "expert": {
        "label": "Expert",
        "short": "experts and practitioners",
        "hint": "Dense and precise. Named papers/tools, trade-offs, no hand-holding.",
    },
}

_AGE_ALIASES = {
    "kid": "kids",
    "child": "kids",
    "children": "kids",
    "elementary": "kids",
    "primary": "kids",
    "tween": "tweens",
    "preteen": "tweens",
    "middle school": "tweens",
    "teen": "teens",
    "teenager": "teens",
    "high school": "teens",
    "young adult": "young_adults",
    "college": "young_adults",
    "undergrad": "young_adults",
    "university student": "young_adults",
    "adult": "adults",
    "general": "adults",
    "professional": "professionals",
    "practitioner": "professionals",
    "expert audience": "professionals",
    "family": "all_ages",
    "all ages": "all_ages",
    "mixed age": "all_ages",
}

_KNOW_ALIASES = {
    "intro": "beginner",
    "introductory": "beginner",
    "novice": "beginner",
    "no background": "beginner",
    "first time": "beginner",
    "101": "beginner",
    "some background": "intermediate",
    "familiar": "intermediate",
    "working knowledge": "intermediate",
    "deep": "advanced",
    "graduate": "advanced",
    "practitioner": "expert",
    "specialist": "expert",
}


def normalize_age_group(raw: str | None) -> str:
    t = re.sub(r"[\s_]+", " ", (raw or "").strip().lower())
    if t in AGE_GROUPS:
        return t
    t2 = t.replace(" ", "_")
    if t2 in AGE_GROUPS:
        return t2
    for alias, key in _AGE_ALIASES.items():
        if alias in t:
            return key
    if re.search(r"\b(5|6|7|8)\b", t) and "age" in t:
        return "kids"
    if re.search(r"\b(9|10|11|12)\b", t):
        return "tweens"
    if re.search(r"\b(13|14|15|16|17)\b", t):
        return "teens"
    return "auto"


def normalize_knowledge(raw: str | None) -> str:
    t = re.sub(r"[\s_]+", " ", (raw or "").strip().lower())
    if t in KNOWLEDGE_LEVELS:
        return t
    for alias, key in _KNOW_ALIASES.items():
        if alias in t:
            return key
    for key in ("beginner", "intermediate", "advanced", "expert"):
        if key in t:
            return key
    return "auto"


def infer_from_prompt(text: str) -> dict[str, str]:
    """Best-effort age + knowledge from a freeform custom prompt."""
    blob = (text or "").strip().lower()
    if not blob:
        return {"age_group": "auto", "knowledge_level": "auto"}
    return {
        "age_group": normalize_age_group(blob),
        "knowledge_level": normalize_knowledge(blob),
    }


def _age_prompt(age: str) -> str:
    if age == "kids":
        return (
            "Speak like a kind storyteller sitting on the floor with 5–8 year olds. "
            "Use tiny words, animals, toys, food, and playground analogies. "
            "One idea per slide. Celebrate curiosity. Never scare, never shame. "
            "Narration is short, musical, and repeatable. Avoid abstract nouns."
        )
    if age == "tweens":
        return (
            "Teach 9–12 year olds who are smart and hate being babied. "
            "Use games, ‘wait, what?’, challenges, and everyday gadgets as analogies. "
            "Keep energy up. Explain new words in one breath. Make them feel capable."
        )
    if age == "teens":
        return (
            "Talk to teenagers as peers. Be direct, slightly witty, never cringe-tryhard. "
            "Tie ideas to identity, fairness, future skills, and real-world stakes. "
            "Respect their intelligence; skip moralizing. Punchy hooks, honest caveats."
        )
    if age == "young_adults":
        return (
            "Address 18–24 year olds building skills and careers. Informal but sharp. "
            "Show why this matters for internships, projects, interviews, and first jobs. "
            "Concrete examples over theory dumps. ‘You can use this tomorrow’ energy."
        )
    if age == "professionals":
        return (
            "Address working professionals who are short on time. No 101 unless needed. "
            "Lead with the decision, the trade-off, the named tool. Monday-morning useful. "
            "Skip pep talks. Keep warmth, drop the TED-talk cadence."
        )
    if age == "all_ages":
        return (
            "Family-friendly: a child can follow the pictures and a parent still learns. "
            "Plain language, no in-jokes, no gore or adult asides. Explain jargon once, "
            "then use it. Keep wonder without dumbing down the idea."
        )
    if age == "adults":
        return (
            "Teach busy adult learners. Warm, clear, time-respecting. "
            "Open with why it matters, then the mechanism, then a takeaway they can retell. "
            "No filler, no corporate voice."
        )
    return ""


def _knowledge_prompt(level: str) -> str:
    if level == "beginner":
        return (
            "Assume ZERO prior knowledge. Define every term the first time it appears. "
            "Intuition and a tiny example BEFORE any formalism. Never say ‘obviously’. "
            "If a formula appears, say it in words first."
        )
    if level == "intermediate":
        return (
            "Assume they know the basics of the field. Do not restart from atoms. "
            "Spend slides on the new mechanism, the common mistake, and the ‘so what’. "
            "Gloss only the jargon that is actually new here."
        )
    if level == "advanced":
        return (
            "Assume strong background. Skip definitions of 101 terms. "
            "Go into internals, failure modes, alternatives, and why the naive version breaks. "
            "Prefer compare/flow/matrix layouts over ‘what is X’ bullets."
        )
    if level == "expert":
        return (
            "Expert-to-expert. Dense, precise, citation-faithful. Named components, "
            "complexity/cost trade-offs, and the interesting edge. No analogies that "
            "insult the audience. No recap of undergraduate material."
        )
    return ""


def custom_prompt_for(age_group: str, knowledge_level: str) -> str:
    """Loaded teaching prompt for the current age + knowledge selects."""
    age = normalize_age_group(age_group)
    know = normalize_knowledge(knowledge_level)
    age_meta = AGE_GROUPS.get(age) or AGE_GROUPS["auto"]
    know_meta = KNOWLEDGE_LEVELS.get(know) or KNOWLEDGE_LEVELS["auto"]
    bits = [
        "Write it straight. No lesson plan, no 'key takeaways', no brand-video voice.",
        "Short labels on the slide. The spoken line can carry the detail, with a pause "
        "and a change of pace. Never sound like a flat robot or a classroom.",
        "Keep on-screen labels short; put depth in the narration. Tie spoken beats "
        "to on-screen items in the SAME ORDER so highlights stay in sync with the voice.",
        "Never duplicate a previous slide’s heading, layout+points, or narration. "
        "If two ideas overlap, merge them or change the angle.",
    ]
    age_block = _age_prompt(age)
    know_block = _knowledge_prompt(know)
    if age != "auto":
        bits.append(f"AGE GROUP: {age_meta['label']} ({age_meta['short']}). {age_block}")
    else:
        bits.append(
            "AGE GROUP: infer from the source. If unclear, default to curious adult learners."
        )
    if know != "auto":
        bits.append(
            f"KNOWLEDGE / UNDERSTANDING: {know_meta['label']} ({know_meta['short']}). {know_block}"
        )
    else:
        bits.append(
            "KNOWLEDGE LEVEL: infer from the source. Prefer slightly more explanation "
            "than too little, unless the document is clearly expert-only."
        )
    if age in {"kids", "tweens"} and know in {"advanced", "expert"}:
        bits.append(
            "Conflict note: keep the AGE voice (simple, kind) even if the idea is advanced. "
            "Teach the deep idea with toys/games — do not switch to lecture tone."
        )
    return "\n".join(f"- {b}" for b in bits)


def catalog() -> dict[str, Any]:
    """Public catalog for the Studio UI."""
    ages = [
        {"key": k, **{kk: vv for kk, vv in v.items()}}
        for k, v in AGE_GROUPS.items()
    ]
    levels = [
        {"key": k, **{kk: vv for kk, vv in v.items()}}
        for k, v in KNOWLEDGE_LEVELS.items()
    ]
    prompts: dict[str, str] = {}
    for a in AGE_GROUPS:
        for kn in KNOWLEDGE_LEVELS:
            prompts[f"{a}:{kn}"] = custom_prompt_for(a, kn)
    return {
        "age_groups": ages,
        "knowledge_levels": levels,
        "prompts": prompts,
        "default_prompt": custom_prompt_for("auto", "auto"),
    }


def resolve_audience(options: dict | None) -> dict[str, str]:
    """Normalize age, knowledge, and custom prompt from job options."""
    opts = options if isinstance(options, dict) else {}
    custom = str(opts.get("custom_prompt") or "").strip()[:4000]
    age = normalize_age_group(opts.get("age_group"))
    know = normalize_knowledge(opts.get("knowledge_level"))
    inferred = infer_from_prompt(custom) if custom else {
        "age_group": "auto",
        "knowledge_level": "auto",
    }
    # Selects win when explicit; otherwise a pasted prompt can set them.
    if age == "auto" and inferred["age_group"] != "auto":
        age = inferred["age_group"]
    if know == "auto" and inferred["knowledge_level"] != "auto":
        know = inferred["knowledge_level"]
    loaded = custom or custom_prompt_for(age, know)
    return {
        "age_group": age,
        "knowledge_level": know,
        "custom_prompt": loaded,
        "prompt_source": "user" if custom else "template",
    }


def audience_prompt_block(options: dict | None) -> str:
    """Extra instruction block injected into the slides LLM prompt."""
    resolved = resolve_audience(options)
    age = resolved["age_group"]
    know = resolved["knowledge_level"]
    age_meta = AGE_GROUPS.get(age) or AGE_GROUPS["auto"]
    know_meta = KNOWLEDGE_LEVELS.get(know) or KNOWLEDGE_LEVELS["auto"]
    prompt = resolved["custom_prompt"]
    return (
        "- AUDIENCE & UNDERSTANDING (user-selected — follow closely):\n"
        f"  * Age group: {age_meta['label']} — {age_meta['short']}.\n"
        f"  * Knowledge / understanding: {know_meta['label']} — {know_meta['short']}.\n"
        "  * Make the content ENGAGING for that audience: a hook they care about, "
        "concrete examples from their world, varied layouts, human voice. "
        "Do not lecture at them.\n"
        "  * CUSTOM TEACHING PROMPT (loaded from the age/knowledge picks, or pasted "
        "by the user — obey it):\n"
        f"{prompt}\n"
        "- DEDUP: every slide must teach a NEW beat. No repeated headings, no cloned "
        "bullet lists, no restating the same narration with synonyms.\n"
        "- VOICE SYNC: explain on-screen items in the order they appear; do not skip "
        "a visual beat in the narration or add a long spoken aside with nothing on screen.\n"
    )


def stamp_options(
    options: dict | None,
    *,
    age_group: str | None = None,
    knowledge_level: str | None = None,
    custom_prompt: str | None = None,
    review_notes: str | None = None,
) -> dict:
    """Write normalized audience fields onto a job options dict."""
    opts = dict(options or {})
    if age_group is not None:
        opts["age_group"] = normalize_age_group(age_group)
    if knowledge_level is not None:
        opts["knowledge_level"] = normalize_knowledge(knowledge_level)
    if custom_prompt is not None:
        opts["custom_prompt"] = str(custom_prompt).strip()[:4000]
    if review_notes is not None:
        opts["review_notes"] = str(review_notes).strip()[:1500]
    resolved = resolve_audience(opts)
    opts["age_group"] = resolved["age_group"]
    opts["knowledge_level"] = resolved["knowledge_level"]
    # Keep the user's pasted prompt if they provided one; otherwise persist the loaded template.
    if not (opts.get("custom_prompt") or "").strip():
        opts["custom_prompt"] = resolved["custom_prompt"]
    opts["audience_prompt_source"] = resolved["prompt_source"]
    return opts


def overlay_analysis(analysis: dict | None, options: dict | None) -> dict:
    """Stamp user audience onto document analysis so later prompt blocks agree."""
    data = dict(analysis or {})
    resolved = resolve_audience(options)
    age = resolved["age_group"]
    know = resolved["knowledge_level"]
    if age != "auto":
        data["audience"] = AGE_GROUPS[age]["short"]
        data["age_group"] = age
    else:
        data.setdefault("audience", data.get("audience") or "general learners")
        data["age_group"] = age
    if know != "auto":
        data["knowledge_level"] = know
        tone = {
            "beginner": "friendly and plain",
            "intermediate": "clear and practical",
            "advanced": "precise and curious",
            "expert": "dense and professional",
        }.get(know, data.get("tone") or "clear and practical")
        data["tone"] = tone
    else:
        data["knowledge_level"] = know
    return data
