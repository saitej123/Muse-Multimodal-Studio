"""Narration for slide videos.

Meta Model API does not synthesize speech. Kokoro (ONNX, local) speaks each
studio voice. If Kokoro is not installed, Kyutai pocket-tts is the fallback.
Muse Wonder still writes the script. Muse Voice Transcribe only listens.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

from ..config import get_settings
from ..logging_setup import log
from . import ratelimit

# Studio voice cards. ``edge`` is the neural voice used to speak that card.
MUSE_VOICES: list[dict] = [
    {"id": "Kore", "label": "Kore", "gender": "female", "vibe": "Firm · Clear", "tag": "Recommended", "hue": 262, "edge": "en-US-AriaNeural", "rate": "+0%", "pitch": "+0Hz"},
    {"id": "Aoede", "label": "Aoede", "gender": "female", "vibe": "Breezy · Warm", "tag": "Popular", "hue": 190, "edge": "en-US-JennyNeural", "rate": "+2%", "pitch": "+2Hz"},
    {"id": "Charon", "label": "Charon", "gender": "male", "vibe": "Informative · Deep", "tag": "Explainers", "hue": 215, "edge": "en-US-GuyNeural", "rate": "-4%", "pitch": "-4Hz"},
    {"id": "Puck", "label": "Puck", "gender": "male", "vibe": "Upbeat · Dynamic", "tag": "Engaging", "hue": 45, "edge": "en-US-DavisNeural", "rate": "+6%", "pitch": "+1Hz"},
    {"id": "Zephyr", "label": "Zephyr", "gender": "female", "vibe": "Bright · Crisp", "tag": "Live", "hue": 160, "edge": "en-GB-SoniaNeural", "rate": "+0%", "pitch": "+4Hz"},
    {"id": "Leda", "label": "Leda", "gender": "female", "vibe": "Youthful · Clear", "tag": "Live", "hue": 330, "edge": "en-US-EmmaNeural", "rate": "+8%", "pitch": "+6Hz"},
    {"id": "Fenrir", "label": "Fenrir", "gender": "male", "vibe": "Excitable · Fast", "tag": "Live", "hue": 0, "edge": "en-US-JasonNeural", "rate": "+10%", "pitch": "+0Hz"},
    {"id": "Orus", "label": "Orus", "gender": "male", "vibe": "Firm · Confident", "tag": "Live", "hue": 250, "edge": "en-GB-RyanNeural", "rate": "-2%", "pitch": "-2Hz"},
    {"id": "Callirrhoe", "label": "Callirrhoe", "gender": "female", "vibe": "Easy-going", "tag": "", "hue": 280, "edge": "en-AU-NatashaNeural", "rate": "+0%", "pitch": "+0Hz"},
    {"id": "Autonoe", "label": "Autonoe", "gender": "female", "vibe": "Bright", "tag": "", "hue": 140, "edge": "en-US-MichelleNeural", "rate": "+4%", "pitch": "+3Hz"},
    {"id": "Sulafat", "label": "Sulafat", "gender": "female", "vibe": "Warm", "tag": "", "hue": 20, "edge": "en-IN-NeerjaNeural", "rate": "-2%", "pitch": "-1Hz"},
    {"id": "Achernar", "label": "Achernar", "gender": "female", "vibe": "Soft", "tag": "", "hue": 310, "edge": "en-US-AnaNeural", "rate": "-6%", "pitch": "+2Hz"},
    {"id": "Despina", "label": "Despina", "gender": "female", "vibe": "Smooth", "tag": "", "hue": 200, "edge": "en-IE-EmilyNeural", "rate": "+0%", "pitch": "+1Hz"},
    {"id": "Erinome", "label": "Erinome", "gender": "female", "vibe": "Clear", "tag": "", "hue": 175, "edge": "en-NZ-MollyNeural", "rate": "+2%", "pitch": "+0Hz"},
    {"id": "Gacrux", "label": "Gacrux", "gender": "female", "vibe": "Mature", "tag": "", "hue": 300, "edge": "en-GB-LibbyNeural", "rate": "-4%", "pitch": "-3Hz"},
    {"id": "Laomedeia", "label": "Laomedeia", "gender": "female", "vibe": "Upbeat", "tag": "", "hue": 50, "edge": "en-US-AvaNeural", "rate": "+8%", "pitch": "+2Hz"},
    {"id": "Pulcherrima", "label": "Pulcherrima", "gender": "female", "vibe": "Forward", "tag": "", "hue": 340, "edge": "en-ZA-LeahNeural", "rate": "+4%", "pitch": "+0Hz"},
    {"id": "Vindemiatrix", "label": "Vindemiatrix", "gender": "female", "vibe": "Gentle", "tag": "", "hue": 150, "edge": "en-CA-ClaraNeural", "rate": "-2%", "pitch": "+2Hz"},
    {"id": "Achird", "label": "Achird", "gender": "male", "vibe": "Friendly", "tag": "", "hue": 30, "edge": "en-US-AndrewNeural", "rate": "+2%", "pitch": "+0Hz"},
    {"id": "Algenib", "label": "Algenib", "gender": "male", "vibe": "Gravelly", "tag": "", "hue": 10, "edge": "en-US-TonyNeural", "rate": "-8%", "pitch": "-6Hz"},
    {"id": "Algieba", "label": "Algieba", "gender": "male", "vibe": "Smooth", "tag": "", "hue": 220, "edge": "en-GB-ThomasNeural", "rate": "-2%", "pitch": "-2Hz"},
    {"id": "Alnilam", "label": "Alnilam", "gender": "male", "vibe": "Firm", "tag": "", "hue": 240, "edge": "en-AU-WilliamNeural", "rate": "+0%", "pitch": "-3Hz"},
    {"id": "Enceladus", "label": "Enceladus", "gender": "male", "vibe": "Breathy", "tag": "", "hue": 180, "edge": "en-CA-LiamNeural", "rate": "-4%", "pitch": "-1Hz"},
    {"id": "Iapetus", "label": "Iapetus", "gender": "male", "vibe": "Clear", "tag": "", "hue": 195, "edge": "en-IN-PrabhatNeural", "rate": "+0%", "pitch": "+0Hz"},
    {"id": "Rasalgethi", "label": "Rasalgethi", "gender": "male", "vibe": "Informative", "tag": "", "hue": 205, "edge": "en-US-BrianNeural", "rate": "-2%", "pitch": "-2Hz"},
    {"id": "Sadachbia", "label": "Sadachbia", "gender": "male", "vibe": "Lively", "tag": "", "hue": 55, "edge": "en-US-ChristopherNeural", "rate": "+8%", "pitch": "+2Hz"},
    {"id": "Sadaltager", "label": "Sadaltager", "gender": "male", "vibe": "Knowledgeable", "tag": "", "hue": 230, "edge": "en-IE-ConnorNeural", "rate": "+0%", "pitch": "-1Hz"},
    {"id": "Schedar", "label": "Schedar", "gender": "male", "vibe": "Even", "tag": "", "hue": 210, "edge": "en-NZ-MitchellNeural", "rate": "+0%", "pitch": "+0Hz"},
    {"id": "Umbriel", "label": "Umbriel", "gender": "male", "vibe": "Easy-going", "tag": "", "hue": 170, "edge": "en-GB-RyanNeural", "rate": "+4%", "pitch": "+1Hz"},
    {"id": "Zubenelgenubi", "label": "Zubenelgenubi", "gender": "male", "vibe": "Casual", "tag": "", "hue": 25, "edge": "en-US-EricNeural", "rate": "+6%", "pitch": "+0Hz"},
]

# Names the rest of the app already imports.

_VOICE_BY_ID = {v["id"].lower(): v for v in MUSE_VOICES}
PRIMARY_LIVE_VOICES = {
    "kore": "Kore",
    "aoede": "Aoede",
    "charon": "Charon",
    "puck": "Puck",
    "fenrir": "Fenrir",
    "leda": "Leda",
    "orus": "Orus",
    "zephyr": "Zephyr",
}


def _has_module(name: str) -> bool:
    import importlib.util

    return importlib.util.find_spec(name) is not None


def narration_available() -> bool:
    return _has_module("kokoro_onnx") or _has_module("pocket_tts")


def selected_engine() -> str:
    if _has_module("kokoro_onnx"):
        return "kokoro"
    if _has_module("pocket_tts"):
        return "kyutai"
    return "none"


def list_voices() -> list[dict]:
    public = []
    for voice in MUSE_VOICES:
        row = {k: v for k, v in voice.items() if k not in {"edge", "rate", "pitch", "kokoro", "pocket", "speed"}}
        public.append(row)
    return public


def muse_voice_ids() -> set[str]:
    return {v["id"] for v in MUSE_VOICES}


def default_voice() -> str:
    raw = (get_settings().muse_tts_voice or "Kore").strip() or "Kore"
    return resolve_voice(raw)


def resolve_voice(name: str | None) -> str:
    key = (name or "").strip()
    if not key:
        key = (get_settings().muse_tts_voice or "Kore").strip() or "Kore"
    found = _VOICE_BY_ID.get(key.lower())
    if not found:
        raise ValueError(f"Unknown narration voice: {key}. Pick one of the studio voices.")
    return found["id"]


def resolve_live_voice(name: str | None) -> str:
    """Map any studio voice onto one of the eight featured voices."""
    key = (name or "").strip().lower()
    if key in PRIMARY_LIVE_VOICES:
        return PRIMARY_LIVE_VOICES[key]
    gender = (_VOICE_BY_ID.get(key) or {}).get("gender", "female")
    return "Kore" if gender == "female" else "Charon"


def voice_from_options(options: dict | None) -> str:
    opts = options or {}
    raw = (opts.get("muse_voice") or opts.get("voice") or "").strip()
    if not raw:
        for key, value in opts.items():
            if str(key).endswith("_voice") and value:
                raw = str(value).strip()
                break
    if raw:
        return resolve_voice(raw)
    for key in ("voice_preset", "pocket_voice"):
        legacy = (opts.get(key) or "").strip()
        if legacy.lower() in _VOICE_BY_ID:
            return resolve_voice(legacy)
    return default_voice()


def output_suffix() -> str:
    return ".wav"


def _chunks(text: str, limit: int = 420) -> list[str]:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return ["..."]
    if len(cleaned) <= limit:
        return [cleaned]
    parts: list[str] = []
    buf = ""
    for sent in re.split(r"(?<=[.!?])\s+", cleaned):
        if not sent:
            continue
        if buf and len(buf) + 1 + len(sent) > limit:
            parts.append(buf)
            buf = sent
        else:
            buf = f"{buf} {sent}".strip()
        while len(buf) > limit:
            parts.append(buf[:limit].strip())
            buf = buf[limit:].strip()
    if buf:
        parts.append(buf)
    return parts or ["..."]


def _write_wav(path: Path, pcm: bytes, rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(pcm) % 2:
        pcm += b"\x00"
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate or 24000)
        wf.writeframes(pcm)


def _edge_fade(pcm: bytes, rate: int, ms: int = 12) -> bytes:
    """Fade the first and last few milliseconds so chunk joins do not click."""
    import array

    if len(pcm) < 8:
        return pcm
    samples = array.array("h")
    samples.frombytes(pcm[: len(pcm) - (len(pcm) % 2)])
    n = min(len(samples) // 4, int((rate or 24000) * ms / 1000))
    if n < 2:
        return samples.tobytes()
    for i in range(n):
        gain = i / n
        samples[i] = int(samples[i] * gain)
        samples[-1 - i] = int(samples[-1 - i] * gain)
    return samples.tobytes()


def _polish_wav(path: Path) -> None:
    """Even the level and fade the edges. Keep the Kokoro sample rate.

    This ffmpeg build upsamples loudnorm to 192 kHz unless the output rate
    is pinned, which makes speech play at the wrong speed.
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg or not path.exists() or path.stat().st_size < 64:
        return
    dur = 0.0
    rate = 24000
    try:
        probe = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=sample_rate",
                "-show_entries", "format=duration",
                "-of", "json", str(path),
            ],
            check=True, capture_output=True, text=True,
        )
        info = json.loads(probe.stdout or "{}")
        dur = float((info.get("format") or {}).get("duration") or 0)
        rate = int(((info.get("streams") or [{}])[0]).get("sample_rate") or 24000)
    except Exception:
        dur = 0.0
        rate = 24000
    fade = "afade=t=in:st=0:d=0.012"
    if dur > 0.25:
        fade += f",afade=t=out:st={max(0.0, dur - 0.05):.3f}:d=0.04"
    tmp = path.with_name(path.stem + ".polish.wav")
    filters = (
        f"highpass=f=80,loudnorm=I=-16:TP=-1.5:LRA=11,{fade},aformat=sample_rates={rate}:channel_layouts=mono",
        f"loudnorm=I=-16:TP=-1.5:LRA=11,aformat=sample_rates={rate}:channel_layouts=mono",
    )
    for af in filters:
        try:
            subprocess.run(
                [
                    ffmpeg, "-y", "-i", str(path), "-af", af,
                    "-ar", str(rate), "-c:a", "pcm_s16le", "-ac", "1", str(tmp),
                ],
                check=True, capture_output=True,
            )
            if tmp.exists() and tmp.stat().st_size > 64:
                tmp.replace(path)
            return
        except Exception:
            tmp.unlink(missing_ok=True)
    tmp.unlink(missing_ok=True)


def _read_wav(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path), "rb") as wf:
        rate = int(wf.getframerate() or 24000)
        return wf.readframes(wf.getnframes()), rate


# Kokoro ids that ship in voices-v1.0.bin. Unknown ids fall back by gender.
_KOKORO_VOICE = {
    "kore": "af_kore",
    "aoede": "af_aoede",
    "zephyr": "af_bella",
    "leda": "af_sky",
    "callirrhoe": "af_heart",
    "autonoe": "af_nova",
    "sulafat": "af_nicole",
    "achernar": "af_sarah",
    "despina": "bf_emma",
    "erinome": "bf_isabella",
    "gacrux": "bf_lily",
    "laomedeia": "af_jessica",
    "pulcherrima": "af_river",
    "vindemiatrix": "bf_alice",
    "charon": "am_michael",
    "puck": "am_puck",
    "fenrir": "am_fenrir",
    "orus": "am_onyx",
    "achird": "am_adam",
    "algenib": "am_echo",
    "algieba": "bm_george",
    "alnilam": "bm_lewis",
    "enceladus": "am_liam",
    "iapetus": "bm_daniel",
    "rasalgethi": "am_eric",
    "sadachbia": "am_santa",
    "sadaltager": "bm_fable",
    "schedar": "bm_george",
    "umbriel": "am_adam",
    "zubenelgenubi": "am_echo",
}
_POCKET_VOICE = {
    "kore": "alba",
    "aoede": "anna",
    "zephyr": "azelma",
    "leda": "eve",
    "callirrhoe": "jane",
    "autonoe": "mary",
    "sulafat": "cosette",
    "achernar": "fantine",
    "despina": "eponine",
    "erinome": "caro_davy",
    "gacrux": "alba",
    "laomedeia": "anna",
    "pulcherrima": "eve",
    "vindemiatrix": "jane",
    "charon": "michael",
    "puck": "charles",
    "fenrir": "george",
    "orus": "paul",
    "achird": "bill_boerst",
    "algenib": "jean",
    "algieba": "javert",
    "alnilam": "marius",
    "enceladus": "peter_yearsley",
    "iapetus": "stuart_bell",
    "rasalgethi": "michael",
    "sadachbia": "charles",
    "sadaltager": "paul",
    "schedar": "george",
    "umbriel": "jean",
    "zubenelgenubi": "bill_boerst",
}
_KOKORO_ONNX_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
)
_KOKORO_VOICES_URL = (
    "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"
)
_kokoro_lock = threading.RLock()
_kokoro_model = None
_pocket_lock = threading.Lock()
_pocket_model = None
_pocket_states: dict = {}


def _download(url: str, dest: Path) -> None:
    import subprocess

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    log.bind(task="TTS").info(f"downloading {dest.name}")
    # IPv4: GitHub release downloads stall on IPv6 from some networks.
    proc = subprocess.run(
        [
            "curl", "-L", "--fail", "-4", "--retry", "3",
            "--connect-timeout", "20", "--max-time", "600",
            "-o", str(tmp), url,
        ],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0 or not tmp.is_file() or tmp.stat().st_size < 1000:
        tmp.unlink(missing_ok=True)
        err = (proc.stderr or b"").decode("utf-8", errors="replace")[-300:]
        raise RuntimeError(f"could not download {dest.name}: {err}")
    tmp.replace(dest)


def _kokoro_files() -> tuple[Path, Path]:
    from ..config import BASE_DIR

    root = BASE_DIR / "models" / "kokoro"
    onnx = root / "kokoro-v1.0.onnx"
    voices = root / "voices-v1.0.bin"
    if not onnx.is_file() or onnx.stat().st_size < 1_000_000:
        _download(_KOKORO_ONNX_URL, onnx)
    if not voices.is_file() or voices.stat().st_size < 100_000:
        _download(_KOKORO_VOICES_URL, voices)
    return onnx, voices


def _kokoro():
    global _kokoro_model
    with _kokoro_lock:
        if _kokoro_model is None:
            from kokoro_onnx import Kokoro

            onnx, voices = _kokoro_files()
            _kokoro_model = Kokoro(str(onnx), str(voices))
        return _kokoro_model


def _samples_to_pcm(samples) -> bytes:
    import numpy as np

    audio = np.asarray(samples, dtype="float32").reshape(-1)
    if audio.size == 0:
        return b""
    audio = np.clip(audio, -1.0, 1.0)
    return (audio * 32767.0).astype("<i2").tobytes()


def _kokoro_voice(voice_id: str) -> tuple[str, str]:
    spec = _VOICE_BY_ID[voice_id.lower()]
    name = _KOKORO_VOICE.get(voice_id.lower()) or ("af_heart" if spec["gender"] == "female" else "am_michael")
    lang = "en-gb" if name.startswith("b") else "en-us"
    return name, lang


def _speak_kokoro(text: str, voice_id: str) -> tuple[bytes, int]:
    name, lang = _kokoro_voice(voice_id)
    model = _kokoro()
    known = set()
    try:
        known = set(model.get_voices())
    except Exception:
        known = set()
    if known and name not in known:
        spec = _VOICE_BY_ID[voice_id.lower()]
        name = "af_heart" if spec["gender"] == "female" else "am_michael"
        if name not in known:
            name = next(iter(known))
        lang = "en-gb" if str(name).startswith("b") else "en-us"
    with _kokoro_lock:
        try:
            samples, rate = model.create(text, voice=name, speed=1.0, lang=lang)
        except TypeError:
            samples, rate = model.create(text, voice=name, speed=1.0)
    pcm = _samples_to_pcm(samples)
    if not pcm:
        raise RuntimeError(f"Kokoro voice {name} returned empty audio")
    return pcm, int(rate or 24000)


def _pocket():
    global _pocket_model
    with _pocket_lock:
        if _pocket_model is None:
            from pocket_tts import TTSModel

            _pocket_model = TTSModel.load_model()
        return _pocket_model


def _speak_pocket(text: str, voice_id: str) -> tuple[bytes, int]:
    spec = _VOICE_BY_ID[voice_id.lower()]
    name = _POCKET_VOICE.get(voice_id.lower()) or ("alba" if spec["gender"] == "female" else "michael")
    model = _pocket()
    with _pocket_lock:
        state = _pocket_states.get(name)
        if state is None:
            state = model.get_state_for_audio_prompt(name)
            _pocket_states[name] = state
        audio = model.generate_audio(state, text)
    if hasattr(audio, "detach"):
        audio = audio.detach().cpu().numpy()
    pcm = _samples_to_pcm(audio)
    if not pcm:
        raise RuntimeError(f"Kyutai voice {name} returned empty audio")
    rate = int(getattr(model, "sample_rate", 24000) or 24000)
    return pcm, rate


def _speak_piece(text: str, voice_id: str) -> tuple[bytes, int, str]:
    errors: list[str] = []
    if _has_module("kokoro_onnx"):
        try:
            pcm, rate = _speak_kokoro(text, voice_id)
            return pcm, rate, "kokoro"
        except Exception as e:  # noqa: BLE001
            errors.append(f"kokoro: {e}")
            log.bind(task="TTS").warning(f"Kokoro failed ({e}); trying Kyutai")
    if _has_module("pocket_tts"):
        try:
            pcm, rate = _speak_pocket(text, voice_id)
            return pcm, rate, "kyutai"
        except Exception as e:  # noqa: BLE001
            errors.append(f"kyutai: {e}")
    detail = "; ".join(errors) or "install kokoro-onnx"
    raise RuntimeError(f"Narration failed ({detail})")


def synthesize(text: str, out_path: Path, voice: str | None = None) -> str:
    """Write a mono WAV for ``text``. Returns ``kokoro`` or ``kyutai``."""
    if not narration_available():
        raise RuntimeError("Narration needs kokoro-onnx (pip install kokoro-onnx).")
    voice_id = resolve_voice(voice)
    out_path = Path(out_path)
    if out_path.suffix.lower() != ".wav":
        out_path = out_path.with_suffix(".wav")

    settings = get_settings()
    pieces = _chunks(text)
    attempts = max(1, int(settings.llm_max_retries or 1))
    base = float(settings.llm_retry_base_delay or 1.5)
    last_exc: Exception | None = None
    pcm_all = b""
    rate = 24000
    engine = selected_engine()

    for piece in pieces:
        spoken = False
        i = 0
        while i < attempts:
            ratelimit.throttle()
            try:
                pcm, rate, engine = _speak_piece(piece, voice_id)
                pcm_all += _edge_fade(pcm, rate)
                spoken = True
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                if i < attempts - 1:
                    log.bind(task="TTS").warning(f"{voice_id} attempt {i + 1} failed ({e}); retrying")
                    time.sleep(ratelimit.backoff_delay(e, i, base))
            i += 1
        if not spoken:
            raise RuntimeError(f"Narration failed: {last_exc}")

    _write_wav(out_path, pcm_all, rate)
    _polish_wav(out_path)
    log.bind(task="TTS").info(
        f"{engine} voice={voice_id} ({len(text or '')} chars, {len(pieces)} call(s), rate={rate}Hz)"
    )
    try:
        from .. import costs

        costs.record(
            provider=engine,
            model=engine,
            kind="tts",
            in_tokens=max(1, len(text or "") // 4),
            out_tokens=0,
        )
    except Exception:
        pass
    return engine


def read_pcm(path: Path) -> tuple[bytes, int]:
    """Raw PCM16 and sample rate from a narration WAV (for the live assistant)."""
    return _read_wav(Path(path))
