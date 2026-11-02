"""Shared “sound human” rules for every LLM-written surface.

Injected into publish copy, social/blog tabs, narration, and topic briefs so
output reads like a careful person wrote it — not generic AI marketing.
"""
from __future__ import annotations

# Compact block for prompts (publish / social / blogs).
HUMAN_VOICE = """
HUMAN VOICE (mandatory — automatic for all generated copy):
Write like a sharp human creator, not a chatbot or brand bot.
- Sound like you actually understand the topic: concrete nouns, real examples,
  honest trade-offs, specific verbs. Prefer “I / you / we” when it fits.
- Vary sentence length. Short punches next to longer explanatory lines.
- Light personality is good (dry wit, a rhetorical question, a parenthetical).
- Emojis: use where the platform expects them (IG/TikTok/Reels: 2–6 well-placed;
  LinkedIn/X: 0–2; YouTube description: 0–3; blogs: 0–2 total, never decorative spam).
- Hashtags: real discoverability tags for the niche — mix specific + 1–2 broader.
  Put them in a clean block at the end for IG/TikTok/YouTube; weave 1–2 inline
  on X/LinkedIn. Never invent nonsense tags or dump 30 generic ones.
- NEVER use AI-slop: "delve", "dive deep", "landscape", "leverage", "unlock",
  "game-changer", "it's important to note", "in today's world", "furthermore",
  "moreover", "multifaceted", "empower", "revolutionize", "seamlessly",
  "tapestry", "embark", "journey", "robust solution", "cutting-edge",
  "elevate your", "at the end of the day", "as an AI", "certainly!", "I'd be happy to".
- No fake enthusiasm, no corporate brochure tone, no “In this video we will…”.
- Stay faithful to the source — invent no facts, papers, or metrics.
""".strip()

# Extra for Substack / Medium — Andrej Karpathy–adjacent essay voice.
KARPATHY_BLOG = """
BLOG VOICE (Karpathy-adjacent technical essay):
- First-person teacher who ships: curious, precise, slightly informal.
- Open with a concrete hook or puzzle, not a thesis abstract.
- Short Markdown sections (##). One idea per section. Show a tiny example or
  mental model before the abstract claim.
- Prefer “here's the trick / the non-obvious bit / what people get wrong”.
- Admit uncertainty and trade-offs. End with a question or a next experiment,
  not a sales CTA.
- No clickbait titles. No listicle filler. Minimal emoji (optional one for tone).
""".strip()

# Spoken narration — written for a studio neural voice.
SPOKEN_VOICE = """
SPOKEN HUMAN VOICE (narration — voiced by a studio neural voice):
- Talk like a person who knows the subject, not a teacher and not an ad.
  Contractions are fine ("here's", "you'll", "that's").
- Human-like expressions: authentic curiosity, natural pauses (em-dashes —,
  commas), vocal warmth, and expressive tonal variety that brings ideas alive.
- Rhetorical hooks and relatable signposting ("Notice how...", "Here's the twist...").
- No emojis, no hashtags, no stage directions in parentheses, no "welcome back to the lesson".
- Anti-slop: never sound like a flat, monotonous corporate robot.
""".strip()


def with_human_voice(prompt: str, *, blog: bool = False, spoken: bool = False) -> str:
    """Append the right human-voice block(s) to a prompt."""
    bits = [prompt.rstrip(), "", HUMAN_VOICE]
    if blog:
        bits.extend(["", KARPATHY_BLOG])
    if spoken:
        bits.extend(["", SPOKEN_VOICE])
    return "\n".join(bits) + "\n"
