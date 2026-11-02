"""Pydantic-backed LLM JSON parsing with repair retries.

LLM calls often return almost-valid JSON (trailing commas, missing fields,
extra prose). This module:

1. Parses leniently into a dict
2. Validates / coerces through a Pydantic model
3. On validation failure, asks the model once more with the error details

Callers get a typed model or a clear exception — never a half-broken dict that
crashes later in the pipeline.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from ..config import get_settings
from ..logging_setup import log

T = TypeVar("T", bound=BaseModel)


def strip_code_fences(text: str) -> str:
    text = (text or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.DOTALL | re.I)
    if fenced:
        return fenced.group(1).strip()
    return text


def loads_json_lenient(text: str) -> dict | list:
    """Parse the first JSON object/array from messy LLM output."""
    text = strip_code_fences(text)
    if not text:
        raise ValueError("empty LLM response")

    # Models often emit curly quotes / BOM / trailing prose around JSON.
    text = (
        text.replace("\ufeff", "")
        .replace("\u201c", '"').replace("\u201d", '"')
        .replace("\u2018", "'").replace("\u2019", "'")
        .replace("\u00a0", " ")
    )

    def _try(raw: str) -> dict | list | None:
        try:
            data = json.loads(raw)
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            return None
        return None

    direct = _try(text)
    if direct is not None:
        return direct

    # Prefer object; only fall back to a bare top-level array when the
    # response has no "{" at all (an unclosed object must never fall through
    # to matching some unrelated nested array inside itself, e.g. a small
    # "talking_points": [...] list that happens to close before the real,
    # truncated "questions" array does).
    brace_pairs = (("{", "}"),) if "{" in text else (("[", "]"),)
    for open_ch, close_ch in brace_pairs:
        start = text.find(open_ch)
        if start < 0:
            continue
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
            elif ch == open_ch:
                depth += 1
            elif ch == close_ch:
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            continue
        candidate = text[start : end + 1]
        for attempt in (
            candidate,
            re.sub(r",(\s*[}\]])", r"\1", candidate),
            # Soften single-quoted keys/strings when the model forgot JSON rules.
            re.sub(r"(?<![\\w])'([^'\\]*(?:\\.[^'\\]*)*)'", r'"\1"', candidate),
        ):
            data = _try(attempt)
            if data is not None:
                return data

    # Last resort: locate a {"topics": ...} blob even if braces were mangled.
    m = re.search(r'\{\s*"topics"\s*:\s*\[', text)
    if m:
        start = m.start()
        depth = 0
        in_str = False
        esc = False
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
                    data = _try(re.sub(r",(\s*[}\]])", r"\1", text[start : i + 1]))
                    if data is not None:
                        return data
                    break

    repaired = _repair_broken_json(text)
    if repaired is not None:
        return repaired

    raise ValueError("no parseable JSON in LLM response")


def _repair_broken_json(text: str) -> dict | list | None:
    """Salvage a partial dict/list from JSON that got cut off (output-token
    truncation) or corrupted (an unescaped ``"`` inside an embedded HTML/
    mermaid snippet threw off string tracking so the brace-matcher above never
    found a balanced end).

    Strategy: walk the text once, and every time we cross a "safe" boundary —
    a closed ``}``/``]`` or a top-level-ish comma — remember that cut point and
    the bracket stack at that moment. At the end, roll back to the last safe
    cut point and synthesize the missing closing brackets. This trades a few
    trailing items (the ones that were broken/truncated) for a response that
    actually parses, instead of throwing away 30K chars of otherwise-good data.
    """
    start = text.find("{")
    alt = text.find("[")
    if alt >= 0 and (start < 0 or alt < start):
        start = alt
    if start < 0:
        return None
    body = text[start:]

    stack: list[str] = []
    closers = {"{": "}", "[": "]"}
    in_str = False
    esc = False
    last_cut = -1
    last_stack: list[str] = []
    for i, ch in enumerate(body):
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
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]":
            if stack:
                stack.pop()
            last_cut = i + 1
            last_stack = list(stack)
        elif ch == "," and stack:
            last_cut = i
            last_stack = list(stack)

    if last_cut <= 0 or not last_stack:
        return None

    candidate = body[:last_cut].rstrip().rstrip(",")
    candidate += "".join(closers[c] for c in reversed(last_stack))
    candidate = re.sub(r",(\s*[}\]])", r"\1", candidate)
    try:
        data = json.loads(candidate)
    except Exception:
        return None
    if isinstance(data, (dict, list)):
        return data
    return None


def validate_model(data: object, model: type[T]) -> T:
    """Validate ``data`` into ``model``, accepting dict or already-typed."""
    if isinstance(data, model):
        return data
    fields = getattr(model, "model_fields", {}) or {}
    # Lite models often return a bare list when the schema is ``{"topics":[...]}``
    # or ``{"claims":[...]}`` / ``{"jobs":[...]}``.
    if isinstance(data, list):
        for key in ("topics", "claims", "jobs", "questions", "sections"):
            if key in fields:
                data = {key: data}
                break
        else:
            # Single list-typed field fallback
            list_fields = [
                k
                for k, f in fields.items()
                if "list" in str(getattr(f, "annotation", "")).lower()
            ]
            if len(list_fields) == 1:
                data = {list_fields[0]: data}
    return model.model_validate(data)


def generate_structured(
    prompt: str,
    model: type[T],
    *,
    task: str = "llm",
    want_json: bool = True,
    model_name: str | None = None,
    max_output_tokens: int | None = None,
) -> T:
    """Call the LLM and return a validated Pydantic instance.

    Retries on transport / parse / validation failures. On validation errors,
    a repair pass includes the Pydantic error summary so the model can fix
    missing fields instead of the pipeline crashing mid-stage. On plain JSON
    parse failures (truncated output or an unescaped quote inside an embedded
    HTML/mermaid snippet breaking string tracking) the repair pass instead
    reminds the model of strict-JSON rules, since a schema dump doesn't help
    when the model already tried to follow the schema and just emitted
    invalid JSON syntax.

    ``model_name`` optionally overrides the active LLM id (3.8 Flash or 4 Argon).
    ``max_output_tokens`` raises the provider output cap so large asks (many
    questions with long markdown answers) don't get cut off mid-object.
    """
    from . import llm_client

    attempts = max(1, int(get_settings().llm_max_retries))
    last_exc: Exception | None = None
    schema_hint = json.dumps(model.model_json_schema(), indent=2)[:3500]

    for i in range(attempts):
        p = prompt
        if i > 0 and last_exc is not None:
            is_json_syntax_error = isinstance(last_exc, (ValueError, json.JSONDecodeError)) and not isinstance(
                last_exc, ValidationError
            )
            if is_json_syntax_error:
                p = (
                    prompt
                    + "\n\nIMPORTANT: Your previous reply could not be parsed as JSON "
                    f"({last_exc}). Likely causes: output got cut off before the JSON "
                    "closed, or a snippet you embedded (HTML/mermaid/code) contained a "
                    'literal " or newline that broke the surrounding JSON string.\n'
                    "STRICT JSON RULES for the retry:\n"
                    "- Reply with ONLY one valid JSON object. No markdown fences, no commentary.\n"
                    '- Escape every " and newline inside string values as \\" and \\n.\n'
                    "- If a field would contain HTML, use single quotes for HTML attributes "
                    "(e.g. class='box') so you never need to escape a double quote.\n"
                    "- Keep every value only as long as needed — do not pad. Finish the "
                    "entire JSON object; a cut-off reply is worse than a shorter one.\n"
                )
            else:
                p = (
                    prompt
                    + "\n\nIMPORTANT: Your previous reply was invalid.\n"
                    f"Error: {last_exc}\n"
                    "Reply with ONLY a single valid JSON object matching this schema:\n"
                    f"{schema_hint}\n"
                    "No markdown, no code fences, no commentary."
                )
        try:
            raw = llm_client.generate_text(
                p, want_json=want_json, model=model_name, max_output_tokens=max_output_tokens
            )
            data = loads_json_lenient(raw or "")
            return validate_model(data, model)
        except (ValidationError, ValueError, TypeError, json.JSONDecodeError) as e:
            last_exc = e
            if i < attempts - 1:
                log.bind(task=task).warning(
                    f"structured parse failed ({e}); retry {i + 1}/{attempts - 1}"
                )
        except Exception as e:  # noqa: BLE001 — transport / provider
            last_exc = e
            if i < attempts - 1:
                log.bind(task=task).warning(
                    f"LLM call failed ({e}); retry {i + 1}/{attempts - 1}"
                )
    raise last_exc if last_exc else ValueError("structured LLM parse failed")
