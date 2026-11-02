"""Muse client for text, vision, and images.

The rest of the pipeline calls :func:`generate_text`, :func:`generate_from_images`,
and :func:`generate_image`. Those talk to the Meta Model API
(``https://api.meta.ai/v1/responses``) with ``MODEL_API_KEY``.

* Text and page images: ``muse-wonder-1.0`` (or ``muse-spark-1.3`` for briefs)
* Thumbnails: ``muse-image-1.0``
* PDF, audio, and video inputs: :func:`generate_multimodal`
"""
from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from pathlib import Path

from ..config import get_settings
from ..logging_setup import log
from . import muse_api, ratelimit


class LLMError(RuntimeError):
    """Raised when an LLM/VLM call fails after all retries."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def normalize_muse_model(model: str | None) -> str:
    return muse_api.normalize_text_model(model)


def _rate_limited(exc: BaseException | None) -> bool:
    return ratelimit.is_rate_limited(exc)


def _retry_wait(exc: BaseException | None, attempt: int, base: float) -> float:
    return ratelimit.backoff_delay(exc, attempt, base)


def _as_llm_error(exc: Exception) -> Exception:
    if isinstance(exc, LLMError):
        return exc
    if isinstance(exc, muse_api.MuseAPIError):
        return LLMError(str(exc), status_code=exc.status_code)
    return exc


def _retryable(fn, *, task: str, provider: str, model: str):
    """Run ``fn`` with backoff on transient failures."""
    settings = get_settings()
    attempts = max(1, int(settings.llm_max_retries))
    base = float(settings.llm_retry_base_delay)
    last_exc: Exception | None = None
    i = 0
    while i < attempts:
        ratelimit.throttle()
        try:
            out = fn()
            if out and str(out).strip():
                return out
            last_exc = LLMError("model returned empty content")
            if i < attempts - 1:
                log.bind(task=task).warning(
                    f"empty response ({provider}/{model}), retry {i + 1}"
                )
        except Exception as e:  # noqa: BLE001
            last_exc = _as_llm_error(e)
            attempts = ratelimit.attempts_for(e, attempts)
            if i < attempts - 1:
                log.bind(task=task).warning(
                    f"{provider}/{model} attempt {i + 1} failed ({e}); retrying"
                )
        if i < attempts - 1:
            delay = _retry_wait(last_exc, i, base)
            if _rate_limited(last_exc):
                ratelimit.note_limit(delay)
                log.bind(task=task).warning(
                    f"{provider}/{model} rate limited; all calls pause {delay:.0f}s"
                )
            time.sleep(delay)
        i += 1
    if isinstance(last_exc, Exception):
        if _rate_limited(last_exc):
            raise LLMError(
                "Muse rate limit. The build paused and retried several times. "
                "Start it again in a minute, or lower LLM_MAX_PARALLEL."
            ) from last_exc
        raise last_exc
    raise LLMError(f"{provider}/{model} produced no content")


_usage_tls = threading.local()


def _stash_usage(data: dict | None) -> None:
    got = muse_api.usage_tokens(data or {})
    _usage_tls.usage = got


def _take_usage() -> tuple[int, int] | None:
    got = getattr(_usage_tls, "usage", None)
    _usage_tls.usage = None
    return got


def _parts_for(paths: list[Path]) -> list[dict]:
    return [muse_api.content_part(Path(p)) for p in paths]


def generate_text(
    prompt: str,
    want_json: bool = False,
    *,
    model: str | None = None,
    use_search: bool = False,
    max_output_tokens: int | None = None,
) -> str:
    """Generate text with Muse Wonder (or the model passed in).

    ``want_json=True`` sets Responses ``text.format`` to ``json_object``.
    ``use_search=True`` enables the ``web_search`` tool (not combined with JSON mode).
    """
    settings = get_settings()
    provider = "muse"
    model_id = normalize_muse_model(model or settings.llm_text_model)
    log.bind(task="LLM").info(f"text generation -> {provider} / {model_id} (search={use_search})")

    def _call() -> str:
        text, data = muse_api.generate_text(
            prompt,
            model=model_id,
            want_json=want_json,
            use_search=use_search,
            search_context_size="high" if use_search else "medium",
            max_output_tokens=max_output_tokens,
        )
        _stash_usage(data)
        return text

    try:
        out = _retryable(_call, task="LLM", provider=provider, model=model_id)
        log.bind(task="LLM").success(f"text ok ({provider}/{model_id}, {len(out):,} chars)")
        _record_cost(provider, model_id, "text", prompt, out)
        if use_search:
            _record_search(model_id)
        return out
    except Exception as e:
        log.bind(task="LLM").error(f"text failed ({provider}/{model_id}): {e}")
        raise


def generate_from_images(
    prompt: str,
    image_paths: list[Path],
    *,
    model: str | None = None,
) -> str:
    """Send page images plus a prompt to Muse Wonder (``input_image`` data URLs)."""
    return generate_multimodal(prompt, image_paths=image_paths, model=model)


def generate_multimodal(
    prompt: str,
    *,
    image_paths: list[Path] | None = None,
    file_paths: list[Path] | None = None,
    audio_paths: list[Path] | None = None,
    video_paths: list[Path] | None = None,
    model: str | None = None,
    want_json: bool = False,
    max_output_tokens: int | None = None,
) -> str:
    """Understand images, PDFs, audio, and video in one Muse Wonder call.

    Images become ``input_image``, wav/mp3 become ``input_audio``, video becomes
    ``input_video``, and other files (including PDF) become ``input_file``.
    """
    settings = get_settings()
    provider = "muse"
    model_id = normalize_muse_model(model or settings.llm_vision_model)
    paths: list[Path] = []
    for group in (image_paths, file_paths, audio_paths, video_paths):
        paths.extend(Path(p) for p in (group or []))
    log.bind(task="VLM").info(
        f"multimodal -> {provider} / {model_id} ({len(paths)} file(s))"
    )

    def _call() -> str:
        text, data = muse_api.generate_with_parts(
            prompt,
            _parts_for(paths),
            model=model_id,
            want_json=want_json,
            max_output_tokens=max_output_tokens,
        )
        _stash_usage(data)
        return text

    try:
        out = _retryable(_call, task="VLM", provider=provider, model=model_id)
        log.bind(task="VLM").success(f"multimodal ok ({provider}/{model_id}, {len(out):,} chars)")
        images = len(image_paths or [])
        _record_cost(provider, model_id, "vision", prompt, out, extra_in=258 * images)
        return out
    except Exception as e:
        log.bind(task="VLM").error(f"multimodal failed ({provider}/{model_id}): {e}")
        raise


def embed_texts(texts: list[str], *, model: str | None = None) -> list[list[float]]:
    """Local hashed embeddings.

    Meta Model API has no embeddings endpoint. Interview Prep semantic search
    still receives unit vectors of ``muse_embedding_dims`` (default 768).
    """
    del model  # the hosted API does not embed
    if not texts:
        return []
    dim = int(getattr(get_settings(), "muse_embedding_dims", 768) or 768)
    dim = max(32, dim)
    out: list[list[float]] = []
    for text in texts:
        vec = [0.0] * dim
        tokens = re.findall(r"[a-z0-9]+", (text or "").lower()) or ["empty"]
        for tok in tokens:
            digest = hashlib.sha256(tok.encode("utf-8")).digest()
            idx = int.from_bytes(digest[:4], "little") % dim
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vec[idx] += sign
        norm = math.sqrt(sum(x * x for x in vec)) or 1.0
        out.append([x / norm for x in vec])
    return out


def generate_image(prompt: str, out_path: Path) -> Path:
    """Thumbnail (or any still) via Muse Image. Not used for slide copy."""
    settings = get_settings()
    model = muse_api.normalize_image_model(settings.muse_image_model)
    log.bind(task="IMG").info(f"Muse Image thumbnail -> muse / {model}")
    if not muse_api.api_key():
        raise LLMError("MODEL_API_KEY required for Muse Image thumbnails")

    attempts = max(1, int(settings.llm_max_retries))
    base = float(settings.llm_retry_base_delay)
    last_exc: Exception | None = None
    i = 0
    while i < attempts:
        ratelimit.throttle()
        try:
            path = muse_api.generate_image(prompt, Path(out_path), model=model)
            if path and Path(path).is_file() and Path(path).stat().st_size > 0:
                log.bind(task="IMG").success(f"image ok (muse/{model} -> {Path(path).name})")
                _record_cost("muse", model, "image", prompt, "", extra_in=0)
                return Path(path)
            last_exc = LLMError("Muse Image returned an empty image file")
        except Exception as e:  # noqa: BLE001
            last_exc = _as_llm_error(e)
            attempts = ratelimit.attempts_for(e, attempts)
            if i < attempts - 1:
                log.bind(task="IMG").warning(f"muse/{model} attempt {i + 1} failed ({e}); retrying")
        if i < attempts - 1:
            delay = ratelimit.backoff_delay(last_exc, i, base)
            if ratelimit.is_rate_limited(last_exc):
                ratelimit.note_limit(delay)
            time.sleep(delay)
        i += 1

    log.bind(task="IMG").error(f"image failed (muse/{model}): {last_exc}")
    if isinstance(last_exc, Exception):
        raise last_exc
    raise LLMError(f"muse/{model} produced no image")


def _record_cost(
    provider: str, model: str, kind: str, prompt: str, output: str, extra_in: int = 0
) -> None:
    try:
        from .. import costs

        real = _take_usage() if kind in ("text", "vision") else None
        if real:
            it, ot = real
            it += int(extra_in or 0)
        else:
            it = costs.estimate_tokens(prompt) + int(extra_in)
            ot = costs.estimate_tokens(output)
        costs.record(provider=provider, model=model, kind=kind, in_tokens=it, out_tokens=ot)
    except Exception:  # noqa: BLE001
        pass


def _record_search(model: str) -> None:
    try:
        from .. import costs

        costs.record(provider="muse", model=model, kind="search", in_tokens=0, out_tokens=0)
    except Exception:  # noqa: BLE001
        pass


def parallel_map(fn, items: list, ordered: bool = True) -> list:
    """Run ``fn`` over ``items`` up to ``llm_max_parallel`` at a time.

    Exceptions from individual items are returned in-slot so callers can degrade
    per item. Order matches ``items``.
    """
    del ordered
    if not items:
        return []
    workers = max(1, get_settings().effective_llm_parallel())
    results: list = [None] * len(items)
    gap = 0.45
    from .. import costs

    fn = costs.bind_context(fn)
    if workers <= 1 or len(items) == 1:
        for i, it in enumerate(items):
            try:
                results[i] = fn(it)
            except Exception as e:  # noqa: BLE001
                results[i] = e
            if i + 1 < len(items):
                time.sleep(gap)
        return results
    from concurrent.futures import ThreadPoolExecutor, as_completed

    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {}
        for i, it in enumerate(items):
            futs[ex.submit(fn, it)] = i
            if i + 1 < len(items):
                time.sleep(gap)
        for fut in as_completed(futs):
            i = futs[fut]
            try:
                results[i] = fut.result()
            except Exception as e:  # noqa: BLE001
                results[i] = e
    return results
