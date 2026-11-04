"""C.H.I.T.T.I. voice session.

Listening is Muse Voice Transcribe. The reply is Muse Wonder text, spoken
with a studio neural voice because Model API does not synthesize speech.
https://dev.meta.ai/docs/speech-to-text
"""
from __future__ import annotations

from typing import Any

from .config import get_settings
from .logging_setup import log

_LOG = log.bind(task="live-audio")

# ~25 audio tokens / second (rough estimate for live audio).
AUDIO_TOKENS_PER_SEC = 25
# 16-bit PCM mono
PCM16_BYTES_PER_SEC = 16_000 * 2
PCM24_BYTES_PER_SEC = 24_000 * 2

DEFAULT_LIVE_MODELS = (
    "muse-wonder-1.0",
)


def live_available() -> bool:
    settings = get_settings()
    return bool((settings.model_api_key or "").strip()) and settings.active_provider == "muse"


def live_model_candidates(*, primary: str | None = None) -> list[str]:
    """Ordered Live model ids for connect retries."""
    settings = get_settings()
    preferred = (primary or settings.chitti_live_model or settings.interview_live_model or "").strip()
    out: list[str] = []
    for m in (preferred, *DEFAULT_LIVE_MODELS):
        if m and m not in out:
            out.append(m)
    return out


def live_model_name() -> str:
    return live_model_candidates()[0]


# Featured studio voices. Default is a warm interviewer.
FEMALE_LIVE_VOICES = ("Aoede", "Kore", "Leda", "Zephyr")
ALL_LIVE_VOICES = FEMALE_LIVE_VOICES + ("Puck", "Charon", "Fenrir", "Orus")
DEFAULT_LIVE_VOICE = "Aoede"


def live_voice_name() -> str:
    """Studio voice for the spoken reply (Aoede unless MUSE_LIVE_VOICE is set)."""
    raw = (get_settings().muse_live_voice or DEFAULT_LIVE_VOICE).strip()
    for name in ALL_LIVE_VOICES:
        if name.lower() == raw.lower():
            return name
    return DEFAULT_LIVE_VOICE


def live_session_config(
    system: str, *, transcribe: bool = True, affective: bool = True
) -> dict[str, Any]:
    """Connect config: female voice, optional affective dialog + transcription."""
    cfg: dict[str, Any] = {
        "response_modalities": ["AUDIO"],
        "system_instruction": system,
        "speech_config": {
            "voice_config": {
                "prebuilt_voice_config": {"voice_name": live_voice_name()},
            }
        },
    }
    if affective:
        cfg["enable_affective_dialog"] = True
    if transcribe:
        cfg["input_audio_transcription"] = {}
        cfg["output_audio_transcription"] = {}
    return cfg


def merge_live_text(prev: str, nxt: str) -> str:
    """Join Live transcription deltas (or replace if the API sent a cumulative string)."""
    a = (prev or "").strip()
    b = (nxt or "").strip()
    if not b:
        return a
    if not a:
        return b
    if b.startswith(a):
        return b
    if a.startswith(b) and len(a) > len(b):
        return a
    if a.endswith(b):
        return a
    max_ov = min(len(a), len(b), 64)
    for i in range(max_ov, 0, -1):
        if a.endswith(b[:i]):
            return a + b[i:]
    glue = ""
    if a[-1].isalnum() and b[0].isalnum():
        glue = " "
    return a + glue + b


def _tx_piece(obj: Any) -> tuple[str, bool]:
    if obj is None:
        return ("", False)
    text = (getattr(obj, "text", None) or "").strip()
    finished = bool(getattr(obj, "finished", False))
    return (text, finished)


def iter_live_events(
    response: Any,
    *,
    transcribe: bool = True,
    asst_role: str = "interviewer",
) -> list[dict[str, Any]]:
    """Normalize a Live server message into audio / transcript / turn events."""
    events: list[dict[str, Any]] = []
    sc = getattr(response, "server_content", None)
    if not sc:
        return events
    saw_out_tx = False
    in_tx = getattr(sc, "input_transcription", None)
    if in_tx is not None:
        text, finished = _tx_piece(in_tx)
        if text:
            events.append(
                {"kind": "transcript", "role": "you", "text": text, "finished": finished}
            )
    out_tx = getattr(sc, "output_transcription", None)
    if out_tx is not None:
        text, finished = _tx_piece(out_tx)
        if text:
            saw_out_tx = True
            events.append(
                {
                    "kind": "transcript",
                    "role": asst_role,
                    "text": text,
                    "finished": finished,
                }
            )
    mt = getattr(sc, "model_turn", None)
    if mt:
        for part in getattr(mt, "parts", None) or []:
            inline = getattr(part, "inline_data", None)
            if inline and getattr(inline, "data", None):
                events.append({"kind": "audio", "data": inline.data})
            txt = getattr(part, "text", None)
            # Output transcription already covers spoken words — don't double-post.
            if txt and not transcribe and not saw_out_tx:
                events.append(
                    {
                        "kind": "transcript",
                        "role": asst_role,
                        "text": str(txt).strip(),
                        "finished": False,
                    }
                )
    if getattr(sc, "turn_complete", False):
        events.append({"kind": "turn_complete"})
    return events


def estimate_audio_tokens(*, in_bytes: int = 0, out_bytes: int = 0) -> tuple[int, int]:
    """Rough token estimate from PCM byte counts (16 kHz in / 24 kHz out)."""
    in_sec = max(0.0, float(in_bytes or 0) / PCM16_BYTES_PER_SEC)
    out_sec = max(0.0, float(out_bytes or 0) / PCM24_BYTES_PER_SEC)
    return (
        max(0, int(round(in_sec * AUDIO_TOKENS_PER_SEC))),
        max(0, int(round(out_sec * AUDIO_TOKENS_PER_SEC))),
    )


def record_live_usage(
    *,
    model: str,
    in_bytes: int = 0,
    out_bytes: int = 0,
    in_tokens: int | None = None,
    out_tokens: int | None = None,
    user_text: str = "",
    assistant_text: str = "",
    job_id: str = "",
    kind: str = "live_audio",
) -> None:
    """Record one Live session / turn for the admin cost dashboard."""
    from . import costs

    it, ot = estimate_audio_tokens(in_bytes=in_bytes, out_bytes=out_bytes)
    if in_tokens is not None:
        it = max(it, int(in_tokens))
    if out_tokens is not None:
        ot = max(ot, int(out_tokens))
    # Prefer text estimates when audio was silent but we still have transcripts.
    if it <= 0 and user_text:
        it = costs.estimate_tokens(user_text)
    if ot <= 0 and assistant_text:
        ot = costs.estimate_tokens(assistant_text)
    costs.record(
        provider="muse",
        model=model or live_model_name(),
        kind=kind,
        in_tokens=it,
        out_tokens=ot,
        prompt=user_text or "",
        output=assistant_text or "",
        job_id=job_id or "",
    )
    _LOG.info(
        f"live usage model={model} kind={kind} in_tok={it} out_tok={ot} "
        f"in_b={in_bytes} out_b={out_bytes}"
    )


def pull_usage_tokens(response: Any) -> tuple[int, int]:
    """Best-effort (prompt, response) tokens from a Live server message."""
    um = getattr(response, "usage_metadata", None)
    if um is None:
        return (0, 0)
    prompt = (
        getattr(um, "prompt_token_count", None)
        or getattr(um, "promptTokenCount", None)
        or 0
    )
    resp = (
        getattr(um, "response_token_count", None)
        or getattr(um, "candidates_token_count", None)
        or getattr(um, "responseTokenCount", None)
        or 0
    )
    try:
        return (int(prompt or 0), int(resp or 0))
    except Exception:
        return (0, 0)


def chitti_system_prompt(*, product: str = "multimodal", session_hint: str = "") -> str:
    """System instruction for C.H.I.T.T.I. Live voice sessions."""
    base = (
        "You are C.H.I.T.T.I. (Cognitive Heuristic Interface Trained for Task Integration), "
        "a concise voice co-pilot inside Multimodal Studio. "
        "Speak briefly and clearly. Confirm actions in one short sentence. "
        "Never invent job status, API keys, or publish outcomes. "
        "Speak in a warm, natural woman's voice — complete sentences, human cadence, never clipped fragments. "
        "If the user asks you to run a workspace action (create a video, upload a document, status, history, help), "
        "acknowledge and state what you will do."
    )
    return (
        base
        + " Product context: Multimodal Studio video pipeline. "
        "You can report job status, open History, and start an upload so the user can create a video. "
        + (f" Extra context: {session_hint}" if session_hint else "")
    )


def pcm_rms(pcm: bytes) -> float:
    """Root-mean-square of 16-bit little-endian mono PCM."""
    n = len(pcm) // 2
    if n <= 0:
        return 0.0
    total = 0
    for i in range(0, n * 2, 2):
        sample = int.from_bytes(pcm[i : i + 2], "little", signed=True)
        total += sample * sample
    return (total / n) ** 0.5


async def serve_chitti(websocket, *, system: str, job_id: str = "") -> None:
    """Turn-based voice loop: PCM in, Muse transcript, Muse reply, WAV speech out.

    The browser already sends 16 kHz PCM and plays 24 kHz PCM. A short silence
    after speech ends one turn.
    """
    import asyncio
    import tempfile
    import time
    from pathlib import Path

    from .pipeline import llm_client, muse_api, tts

    model = live_model_name()
    voice = live_voice_name()
    await websocket.send_json(
        {
            "ready": True,
            "model": model,
            "voice": voice,
            "product": "multimodal",
            "name": "C.H.I.T.T.I.",
            "transcription": True,
        }
    )

    pcm = bytearray()
    speech_seen = False
    last_voice = 0.0
    busy = False
    stop = False
    user_bits: list[str] = []
    asst_bits: list[str] = []
    in_bytes = 0
    out_bytes = 0

    async def _reply(heard: str) -> None:
        nonlocal out_bytes
        prompt = (
            f"{system}\n\nThe user just said:\n{heard}\n\n"
            "Reply in one or two short spoken sentences. No markdown, no lists."
        )
        reply = await asyncio.to_thread(
            lambda: llm_client.generate_text(prompt, model=model)
        )
        reply = " ".join((reply or "").split())
        if len(reply) > 600:
            reply = reply[:600].rsplit(" ", 1)[0]
        await websocket.send_json(
            {
                "type": "transcript",
                "role": "chitti",
                "text": reply,
                "full": reply,
                "finished": True,
            }
        )
        if reply:
            asst_bits.append(reply)
        if reply and tts.narration_available():
            with tempfile.TemporaryDirectory(prefix="chitti-") as tmp:
                wav = Path(tmp) / "reply.wav"
                await asyncio.to_thread(tts.synthesize, reply, wav, voice)
                audio, _rate = tts.read_pcm(wav)
            if audio:
                out_bytes += len(audio)
                await websocket.send_bytes(audio)
        await websocket.send_json(
            {
                "turn_complete": True,
                "ts": time.time(),
                "heard": heard,
                "reply": reply,
            }
        )

    async def handle(audio: bytes | None, text: str | None) -> None:
        nonlocal busy
        if busy:
            return
        busy = True
        try:
            heard = (text or "").strip()
            if audio and not heard:
                wav = muse_api.pcm16_to_wav(audio, 16000)
                heard, duration_ms = await asyncio.to_thread(muse_api.transcribe_wav, wav)
                heard = (heard or "").strip()
                seconds = max(1, int(round((duration_ms or 0) / 1000)) or len(audio) // 32000)
                try:
                    from . import costs

                    costs.record(
                        provider="muse",
                        model=muse_api.DEFAULT_TRANSCRIBE_MODEL,
                        kind="asr",
                        in_tokens=seconds,
                        out_tokens=0,
                        job_id=job_id,
                    )
                except Exception:
                    pass
            if not heard:
                return
            user_bits.append(heard)
            await websocket.send_json(
                {
                    "type": "transcript",
                    "role": "you",
                    "text": heard,
                    "full": heard,
                    "finished": True,
                }
            )
            await _reply(heard)
        except Exception as e:  # noqa: BLE001
            _LOG.warning(f"chitti turn failed: {e}")
            try:
                await websocket.send_json({"error": str(e)})
            except Exception:
                pass
        finally:
            busy = False

    async def watcher() -> None:
        nonlocal speech_seen, last_voice
        while not stop:
            await asyncio.sleep(0.25)
            if busy or len(pcm) < 16000:
                continue
            tail = bytes(pcm[-6400:])
            if pcm_rms(tail) > 480:
                speech_seen = True
                last_voice = time.monotonic()
                continue
            if speech_seen and (time.monotonic() - last_voice) > 0.9:
                chunk = bytes(pcm)
                pcm.clear()
                speech_seen = False
                await handle(chunk, None)

    watch = asyncio.create_task(watcher())
    try:
        while not stop:
            msg = await websocket.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            if msg.get("bytes") is not None:
                chunk = msg["bytes"] or b""
                in_bytes += len(chunk)
                pcm.extend(chunk)
                if pcm_rms(chunk) > 480:
                    speech_seen = True
                    last_voice = time.monotonic()
                continue
            if not msg.get("text"):
                continue
            try:
                import json

                payload = json.loads(msg["text"])
            except Exception:
                payload = {"text": msg["text"]}
            if payload.get("end"):
                if speech_seen and pcm and not busy:
                    chunk = bytes(pcm)
                    pcm.clear()
                    speech_seen = False
                    await handle(chunk, None)
                break
            spoken = (payload.get("text") or "").strip()
            if spoken:
                await handle(None, spoken)
    finally:
        stop = True
        watch.cancel()
        try:
            await websocket.send_json(
                {
                    "type": "usage",
                    "model": model,
                    "in_bytes": in_bytes,
                    "out_bytes": out_bytes,
                }
            )
        except Exception:
            pass
        _LOG.info(
            f"chitti session model={model} heard={len(user_bits)} replies={len(asst_bits)} "
            f"in_b={in_bytes} out_b={out_bytes}"
        )
