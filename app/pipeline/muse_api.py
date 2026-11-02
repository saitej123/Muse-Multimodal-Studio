"""Meta Model API client (Muse).

Text, vision, audio, video, and PDF understanding use ``POST /v1/responses``
with ``muse-wonder-1.0`` (or another Muse text model). Thumbnails use
``muse-image-1.0`` on the same endpoint. Speech-to-text uses
``POST /v1/asr/transcribe`` with ``muse-voice-transcribe-1.0``.

Docs: https://dev.meta.ai/docs/protocols/responses
      https://dev.meta.ai/docs/image-understanding
      https://dev.meta.ai/docs/image-generation
      https://dev.meta.ai/docs/speech-to-text

Model API does not synthesize speech. Narration is handled in ``tts.py``.
"""
from __future__ import annotations

import base64
import io
import json
import wave
from pathlib import Path
from typing import Any

import httpx

from ..config import get_settings

API_BASE = "https://api.meta.ai/v1"
RESPONSES_URL = f"{API_BASE}/responses"
TRANSCRIBE_URL = f"{API_BASE}/asr/transcribe"

DEFAULT_TEXT_MODEL = "muse-wonder-1.0"
DEFAULT_LITE_MODEL = "muse-spark-1.3"
DEFAULT_IMAGE_MODEL = "muse-image-1.0"
DEFAULT_TRANSCRIBE_MODEL = "muse-voice-transcribe-1.0"

_TEXT_MODELS = frozenset(
    {
        "muse-wonder-1.0",
        "muse-spark-1.3",
        "muse-spark-1.3-contributor",
        "muse-spark-1.2",
        "muse-spark-1.2-contributor",
        "muse-spark-1.1",
    }
)

_IMAGE_EXTS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".bmp": "image/bmp"}
_VIDEO_EXTS = {".mp4": "video/mp4", ".webm": "video/webm", ".mov": "video/quicktime"}


class MuseAPIError(RuntimeError):
    """HTTP or protocol failure from the Meta Model API."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def api_key() -> str:
    settings = get_settings()
    key = (getattr(settings, "model_api_key", None) or "").strip()
    if not key:
        key = (getattr(settings, "model_api_key", None) or "").strip()
    return key


def require_key() -> str:
    key = api_key()
    if not key:
        raise MuseAPIError("MODEL_API_KEY is not set")
    return key


def normalize_text_model(model: str | None) -> str:
    """Keep a Muse text id. Retired Muse ids become Muse Wonder."""
    key = (model or "").strip().lower()
    if not key:
        return DEFAULT_TEXT_MODEL
    if key in _TEXT_MODELS or key.startswith("muse-spark") or key.startswith("muse-wonder"):
        return key
    return DEFAULT_TEXT_MODEL


def normalize_image_model(model: str | None) -> str:
    key = (model or "").strip().lower()
    if key.startswith("muse-image"):
        return key
    return DEFAULT_IMAGE_MODEL


def normalize_muse_model(model: str | None) -> str:
    """Alias used by the rest of the pipeline for text and vision ids."""
    return normalize_text_model(model)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {require_key()}",
        "Content-Type": "application/json",
    }


def _timeout() -> httpx.Timeout:
    seconds = float(getattr(get_settings(), "llm_timeout_seconds", 600.0) or 600.0)
    return httpx.Timeout(seconds, connect=30.0)


def _raise_for_status(response: httpx.Response) -> None:
    if response.status_code < 400:
        return
    body = (response.text or "").strip().replace("\n", " ")
    if len(body) > 700:
        body = body[:700] + "…"
    retry_after = (response.headers.get("retry-after") or "").strip()
    extra = f" retry in {retry_after}s" if retry_after else ""
    raise MuseAPIError(
        f"HTTP {response.status_code} from Meta Model API{extra}: {body or response.reason_phrase}",
        status_code=response.status_code,
    )


def create_response(payload: dict[str, Any]) -> dict[str, Any]:
    """POST /v1/responses and return the JSON body."""
    body = dict(payload)
    body.setdefault("stream", False)
    body.setdefault("store", False)
    with httpx.Client(timeout=_timeout()) as client:
        response = client.post(RESPONSES_URL, headers=_headers(), json=body)
    _raise_for_status(response)
    data = response.json()
    if not isinstance(data, dict):
        raise MuseAPIError("Meta Model API returned a non-object response")
    status = str(data.get("status") or "")
    if status in {"failed", "cancelled", "incomplete"} and not output_text(data) and not image_b64(data):
        err = data.get("error") or data.get("incomplete_details") or {}
        if isinstance(err, dict):
            detail = err.get("message") or err.get("reason") or err
        else:
            detail = err or status
        raise MuseAPIError(f"Muse response {status}: {detail}")
    return data


def output_text(data: dict[str, Any]) -> str:
    """Join assistant ``output_text`` parts. Reasoning summaries are not the answer."""
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct
    chunks: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"} and part.get("text"):
                chunks.append(str(part["text"]))
    return "".join(chunks)


def usage_tokens(data: dict[str, Any]) -> tuple[int, int] | None:
    usage = data.get("usage") or {}
    if not isinstance(usage, dict):
        return None
    try:
        pin = int(usage.get("input_tokens") or 0)
        out = int(usage.get("output_tokens") or 0)
    except (TypeError, ValueError):
        return None
    if pin or out:
        return pin, out
    return None


def search_hits(data: dict[str, Any]) -> list[dict[str, str]]:
    """Sources from raw ``web_search_call.results`` and ``url_citation`` annotations.

    Raw hits are present only when the request includes ``web_search_call.results``.
    Citations are attached to ``output_text`` even when that include is omitted.
    """
    hits: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(url: str, title: str, snippet: str) -> None:
        url = (url or "").strip()
        if not url or url in seen:
            return
        seen.add(url)
        hits.append(
            {
                "title": (title or "Search result").strip() or "Search result",
                "url": url,
                "snippet": (snippet or "").strip(),
            }
        )

    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "web_search_call":
            for result in item.get("results") or []:
                if not isinstance(result, dict):
                    continue
                _add(
                    str(result.get("url") or ""),
                    str(result.get("title") or ""),
                    str(result.get("snippet") or ""),
                )
        if item.get("type") != "message":
            continue
        for part in item.get("content") or []:
            if not isinstance(part, dict):
                continue
            text = str(part.get("text") or "")
            for ann in part.get("annotations") or []:
                if not isinstance(ann, dict) or ann.get("type") != "url_citation":
                    continue
                snippet = ""
                try:
                    start = int(ann.get("start_index") or 0)
                    end = int(ann.get("end_index") or 0)
                    if end > start:
                        snippet = text[start:end]
                except (TypeError, ValueError):
                    snippet = ""
                _add(str(ann.get("url") or ""), str(ann.get("title") or ""), snippet)
    return hits


def image_b64(data: dict[str, Any]) -> str:
    for item in data.get("output") or []:
        if not isinstance(item, dict) or item.get("type") != "image_generation_call":
            continue
        raw = item.get("result")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
    return ""


def decode_image(raw: str) -> bytes:
    text = (raw or "").strip()
    if text.startswith("data:") and "," in text:
        text = text.split(",", 1)[1]
    text = "".join(text.split())
    try:
        return base64.b64decode(text, validate=False)
    except Exception as e:  # noqa: BLE001
        raise MuseAPIError(f"Muse image payload was not valid base64: {e}") from e


def save_image_bytes(data: bytes, out_path: Path) -> Path:
    """Write image bytes, converting when the container does not match the suffix."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    kind = _sniff_image(data)
    want = out_path.suffix.lower().lstrip(".")
    if want == "jpg":
        want = "jpeg"
    if kind == want or want not in {"png", "jpeg", "webp"} or kind == "bin":
        out_path.write_bytes(data)
        return out_path
    try:
        from PIL import Image
    except Exception as e:
        raise MuseAPIError(
            f"Muse Image returned {kind}, and pillow is required to save .{want} ({e})"
        ) from e
    image = Image.open(io.BytesIO(data))
    if want == "jpeg" and image.mode in {"RGBA", "LA", "P"}:
        image = image.convert("RGB")
    image.save(out_path, format="JPEG" if want == "jpeg" else want.upper())
    return out_path


def _sniff_image(data: bytes) -> str:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    if data[:6] in {b"GIF87a", b"GIF89a"}:
        return "gif"
    return "bin"


def _b64(path: Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode("ascii")


def image_part(path: Path, *, detail: str | None = None) -> dict[str, Any]:
    path = Path(path)
    mime = _IMAGE_EXTS.get(path.suffix.lower(), "image/png")
    part: dict[str, Any] = {
        "type": "input_image",
        "image_url": f"data:{mime};base64,{_b64(path)}",
    }
    if detail in {"low", "high", "auto"}:
        part["detail"] = detail
    return part


def file_part(path: Path) -> dict[str, Any]:
    path = Path(path)
    return {
        "type": "input_file",
        "filename": path.name,
        "file_data": _b64(path),
    }


def audio_part(path: Path) -> dict[str, Any]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".mp3":
        fmt = "mp3"
    elif ext == ".wav":
        fmt = "wav"
    else:
        raise MuseAPIError(f"Muse audio input accepts wav or mp3, not {path.name}")
    return {
        "type": "input_audio",
        "input_audio": {"data": _b64(path), "format": fmt},
    }


def video_part(path: Path) -> dict[str, Any]:
    path = Path(path)
    mime = _VIDEO_EXTS.get(path.suffix.lower(), "video/mp4")
    return {
        "type": "input_video",
        "video_url": f"data:{mime};base64,{_b64(path)}",
    }


def content_part(path: Path) -> dict[str, Any]:
    """Pick ``input_image`` / ``input_audio`` / ``input_video`` / ``input_file``."""
    ext = Path(path).suffix.lower()
    if ext in _IMAGE_EXTS:
        return image_part(path)
    if ext in {".wav", ".mp3"}:
        return audio_part(path)
    if ext in _VIDEO_EXTS:
        return video_part(path)
    return file_part(path)


def user_message(prompt: str, parts: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt or ""}]
    content.extend(parts or [])
    return {"role": "user", "content": content}


def text_payload(
    prompt: str,
    *,
    model: str,
    parts: list[dict[str, Any]] | None = None,
    want_json: bool = False,
    use_search: bool = False,
    search_context_size: str = "medium",
    max_output_tokens: int | None = None,
    instructions: str | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": normalize_text_model(model),
        "input": [user_message(prompt, parts)] if parts else prompt,
        "store": False,
        "reasoning": {"effort": reasoning_effort or ("low" if want_json else "medium")},
    }
    if instructions:
        payload["instructions"] = instructions
    if want_json:
        # Responses API structured output. json_object matches the old
        # "reply with JSON" calls that do not carry a full schema.
        payload["text"] = {"format": {"type": "json_object"}}
    if use_search and not want_json:
        # Search grounding is Responses-only. Muse Image rejects this tool.
        size = search_context_size if search_context_size in {"low", "medium", "high"} else "medium"
        payload["tools"] = [{"type": "web_search", "search_context_size": size}]
        payload["include"] = ["web_search_call.results"]
    if max_output_tokens:
        cap = max(256, min(int(max_output_tokens), 128000))
        payload["max_output_tokens"] = cap
    return payload


def generate_text(
    prompt: str,
    *,
    model: str,
    want_json: bool = False,
    use_search: bool = False,
    search_context_size: str = "medium",
    max_output_tokens: int | None = None,
    instructions: str | None = None,
) -> tuple[str, dict[str, Any]]:
    payload = text_payload(
        prompt,
        model=model,
        want_json=want_json,
        use_search=use_search,
        search_context_size=search_context_size,
        max_output_tokens=max_output_tokens,
        instructions=instructions,
    )
    try:
        data = create_response(payload)
    except MuseAPIError as e:
        if want_json and e.status_code == 400:
            payload.pop("text", None)
            data = create_response(payload)
        else:
            raise
    text = output_text(data)
    if not text and str(data.get("status") or "").lower() == "incomplete":
        raise MuseAPIError(
            f"Muse response truncated at max_output_tokens ({data.get('incomplete_details') or data.get('status')})"
        )
    return text, data


def generate_with_parts(
    prompt: str,
    parts: list[dict[str, Any]],
    *,
    model: str,
    want_json: bool = False,
    max_output_tokens: int | None = None,
) -> tuple[str, dict[str, Any]]:
    payload = text_payload(
        prompt,
        model=model,
        parts=parts,
        want_json=want_json,
        max_output_tokens=max_output_tokens,
        reasoning_effort="low",
    )
    data = create_response(payload)
    text = output_text(data)
    if not text and str(data.get("status") or "").lower() == "incomplete":
        raise MuseAPIError(
            f"Muse response truncated ({data.get('incomplete_details') or data.get('status')})"
        )
    return text, data


def generate_image(prompt: str, out_path: Path, *, model: str | None = None) -> Path:
    """One-shot image from Muse Image. ``result`` is base64 on ``image_generation_call``."""
    model_id = normalize_image_model(model or getattr(get_settings(), "muse_image_model", "") or DEFAULT_IMAGE_MODEL)
    data = create_response(
        {
            "model": model_id,
            "input": prompt,
            "store": False,
        }
    )
    raw = image_b64(data)
    if not raw:
        raise MuseAPIError(f"Muse Image ({model_id}) returned no image")
    return save_image_bytes(decode_image(raw), Path(out_path))


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    if len(pcm) % 2:
        pcm += b"\x00"
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(int(rate or 16000))
        wf.writeframes(pcm)
    return buf.getvalue()


def transcribe_wav(wav_bytes: bytes, *, model: str | None = None) -> tuple[str, int]:
    """Transcribe a 16 kHz or 24 kHz mono PCM WAV. Returns (text, duration_ms)."""
    model_id = (model or DEFAULT_TRANSCRIBE_MODEL).strip() or DEFAULT_TRANSCRIBE_MODEL
    request = {
        "model": model_id,
        "audioEncoding": "WAV",
        "mode": "PUSH_TO_TALK",
        "languageBias": ["English"],
    }
    headers = {"Authorization": f"Bearer {require_key()}"}
    files = {
        "request": (None, json.dumps(request), "application/json"),
        "audio": ("speech.wav", wav_bytes, "audio/wav"),
    }
    with httpx.Client(timeout=_timeout()) as client:
        response = client.post(TRANSCRIBE_URL, headers=headers, files=files)
    _raise_for_status(response)
    data = response.json()
    if not isinstance(data, dict):
        raise MuseAPIError("Muse Voice Transcribe returned a non-object response")
    text = str(data.get("transcript") or "").strip()
    try:
        duration_ms = int(data.get("audioDurationMs") or 0)
    except (TypeError, ValueError):
        duration_ms = 0
    return text, duration_ms
