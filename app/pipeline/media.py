"""Stage 3-5: per-slide voiceover + capture, then per-slide A/V segments
concatenated into a final, perfectly synced video.

Sync strategy (HTML first, then audio)
--------------------------------------
1. Generate builds seek-safe HTML with a normalized visual timeline.
2. Narrate synthesizes one TTS clip per slide; short clips are padded so the
   entrance + highlight walk always have room.
3. Capture scrubs ``__seekFrame(f, total)`` across that timeline sized to the
   audio duration (audio = master clock; visuals scrub to it — Remotion/GSAP
   seek pattern). Sparse keyframes use the same lead + text weights as JS.
4. Merge muxes each segment so video length == audio length.
"""
from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from ..capabilities import ffmpeg_path
from ..config import BASE_DIR, get_settings
from ..logging_setup import log
from . import tts
from ..video_options import get_video_spec


# ---------------------------------------------------------------- ffmpeg ----

def _run_ffmpeg(args: list[str]) -> None:
    exe = ffmpeg_path() or "ffmpeg"
    proc = subprocess.run([exe, *args], capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-6:]
        raise RuntimeError("FFmpeg failed: " + " | ".join(tail))


def _x264_args() -> list[str]:
    """Quality-tuned libx264 args from settings (CRF + preset)."""
    s = get_settings()
    crf = str(getattr(s, "video_crf", 20))
    preset = str(getattr(s, "video_preset", "medium"))
    return ["-c:v", "libx264", "-preset", preset, "-crf", crf, "-pix_fmt", "yuv420p"]


def _ffprobe_duration(path: Path) -> float:
    """Audio/clip duration in seconds via ffprobe; falls back to ffmpeg parse."""
    exe = ffmpeg_path() or "ffmpeg"
    probe = Path(exe).with_name("ffprobe" + (".exe" if exe.endswith(".exe") else ""))
    if probe.exists():
        proc = subprocess.run(
            [str(probe), "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True,
        )
        try:
            return float(proc.stdout.strip())
        except (ValueError, AttributeError):
            pass
    # Fallback: parse ffmpeg -i stderr "Duration: HH:MM:SS.xx"
    proc = subprocess.run([exe, "-i", str(path)], capture_output=True, text=True)
    import re
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)", proc.stderr or "")
    if m:
        h, mnt, s = m.groups()
        return int(h) * 3600 + int(mnt) * 60 + float(s)
    return 0.0


def _atempo_chain(factor: float) -> str:
    """Build an ffmpeg atempo filter chain for an arbitrary speed ``factor``.

    A single ``atempo`` only accepts 0.5–2.0, so larger factors are split into
    a product of in-range steps. Pitch is preserved (atempo is time-stretch).
    """
    factor = max(0.5, float(factor))
    steps: list[float] = []
    remaining = factor
    while remaining > 2.0:
        steps.append(2.0)
        remaining /= 2.0
    steps.append(round(remaining, 4))
    return ",".join(f"atempo={s}" for s in steps)


def fit_audio_to_target(
    audios: list[Path | None],
    target_seconds: float,
    per_slide_overhead: float = 0.45,
    max_speedup: float = 1.18,
    tolerance: float = 1.06,
) -> float:
    """Time-stretch narration clips in place so the video tracks ``target``.

    TTS pace varies by engine/voice, so the summed narration often overshoots
    the requested duration. When the total (plus a small per-slide fade/pad
    overhead) exceeds ``target * tolerance`` we uniformly speed every clip up
    with ``atempo`` (pitch-preserving) by a single factor, capped at
    ``max_speedup`` so it never sounds unnatural. Returns the applied factor
    (1.0 when no change was made).
    """
    clips = [a for a in audios if a is not None and a.exists()]
    if not clips or target_seconds <= 0:
        return 1.0
    total = sum(_ffprobe_duration(a) for a in clips)
    overhead = per_slide_overhead * len(clips)
    speak_target = max(1.0, target_seconds - overhead)
    if total <= speak_target * tolerance:
        return 1.0
    factor = min(max_speedup, total / speak_target)
    if factor <= 1.01:
        return 1.0
    chain = _atempo_chain(factor)
    for a in clips:
        tmp = a.with_name(a.stem + "__fit" + a.suffix)
        try:
            _run_ffmpeg(["-y", "-i", str(a), "-filter:a", chain, "-vn", str(tmp)])
            tmp.replace(a)
        except Exception:
            tmp.unlink(missing_ok=True)
    return factor



# ---------------------------------------------------------------- TTS ----

def generate_voiceover(
    script_text: str, out_path: Path, voice: str | None = None
) -> tuple[Path, str]:
    """Whole-script voiceover (used as a fallback / for the audio artifact)."""
    engine = tts.synthesize(script_text, out_path, voice=voice)
    actual = out_path if out_path.exists() else out_path.with_suffix(".wav")
    return actual, engine


def synthesize_many(
    items: list[tuple[str, Path]],
    voice: str | None = None,
    workers: int = 3,
    on_done=None,
) -> list[str]:
    """Synthesize ``(text, out_path)`` clips in parallel (staggered starts).

    Returns the engine name per item, in input order. The first failure is
    re-raised after every clip has been attempted.
    """
    from concurrent.futures import ThreadPoolExecutor

    if not items:
        return []
    workers = max(1, min(int(workers), len(items)))

    def _one_raw(item: tuple[str, Path]) -> str:
        text, out = item
        return tts.synthesize(text or "...", out, voice=voice)

    from .. import costs

    _one = costs.bind_context(_one_raw)  # keep the job id on worker threads

    def _mark(i: int) -> None:
        if on_done:
            try:
                on_done(i + 1, len(items))
            except Exception:
                pass

    if workers == 1:
        out = []
        for i, it in enumerate(items):
            out.append(_one(it))
            _mark(i)
        return out
    results: list = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = []
        for it in items:
            futs.append(ex.submit(_one, it))
            time.sleep(0.4)  # small gap so calls overlap without bursting
        for i, f in enumerate(futs):
            try:
                results[i] = f.result()
            except Exception as e:  # noqa: BLE001
                results[i] = e
            else:
                _mark(i)
    for r in results:
        if isinstance(r, Exception):
            raise r
    return results


def synthesize_slide_audio(
    narrations: list[str],
    audio_dir: Path,
    voice: str | None = None,
    on_done=None,
) -> tuple[list[Path], str]:
    """Synthesize one narration clip per slide in parallel. Returns (paths, engine)."""
    audio_dir.mkdir(parents=True, exist_ok=True)
    suffix = tts.output_suffix()
    outs = [audio_dir / f"slide_{i:03d}{suffix}" for i in range(len(narrations))]
    engines = synthesize_many(
        [(t or "...", o) for t, o in zip(narrations, outs)],
        voice=voice,
        workers=get_settings().effective_llm_parallel(),
        on_done=on_done,
    )
    paths = [o if o.exists() else o.with_suffix(".wav") for o in outs]
    return paths, (engines[-1] if engines else "none")


# ---------------------------------------------------------------- capture ----

def _n_capture_workers(n_slides: int) -> int:
    """Number of parallel Playwright workers to split slides across."""
    s = get_settings()
    configured = int(getattr(s, "capture_workers", 0) or 0)
    if configured > 0:
        n = configured
    else:
        cpu = os.cpu_count() or 4
        # Each worker launches a Chromium; keep it modest to bound RAM.
        n = max(1, min(4, cpu // 2))
    return max(1, min(n, n_slides))


def _split_indices(count: int, n_workers: int) -> list[list[int]]:
    """Split [0..count) into ``n_workers`` roughly-equal contiguous batches."""
    if n_workers <= 1 or count <= 1:
        return [list(range(count))]
    per = math.ceil(count / n_workers)
    batches = [list(range(i, min(i + per, count))) for i in range(0, count, per)]
    return [b for b in batches if b]


def _capture_timeout_s(manifest_path: Path) -> int:
    """Hard stop so a hung browser becomes an error instead of a stuck stage.

    Sized from the screenshot count, then capped under the Cloud Run request
    limit so the stage can report the failure before the instance is killed.
    """
    try:
        cfg = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        return 600
    indices = cfg.get("slide_indices") or list(range(int(cfg.get("count") or 1)))
    n = max(1, len(indices))
    if cfg.get("mode") == "animated":
        frames = cfg.get("capture_indices_per_slide") or []
        shots = 0
        for i in indices:
            if isinstance(frames, list) and i < len(frames) and isinstance(frames[i], list):
                shots += max(1, len(frames[i]))
            else:
                shots += 24
        # ~6s per screenshot plus browser startup, never past 45 minutes.
        return max(180, min(2700, 90 + shots * 6))
    return max(180, min(1800, 90 + n * 45))


def _run_capture_worker(manifest_path: Path) -> None:
    worker_cmd = [
        sys.executable, "-m", "app.pipeline.capture_worker",
        "--manifest", str(manifest_path),
    ]
    timeout = _capture_timeout_s(manifest_path)
    proc = subprocess.Popen(
        worker_cmd,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        _out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        raise RuntimeError(
            f"Capture timed out after {timeout // 60} min. "
            "The browser did not finish filming. Use Re-capture to try again."
        )
    if proc.returncode != 0:
        text = (err or "").strip()
        if "playwright install" in text.lower() or "executable doesn't exist" in text.lower():
            raise RuntimeError(
                "Capture failed: the Playwright browser is missing for this install. "
                "From the project folder run: playwright install chromium"
            )
        tail = text.splitlines()[-4:]
        raise RuntimeError("Capture failed: " + " | ".join(tail))


def capture_slides(
    html_path: Path,
    out_dir: Path,
    count: int,
    width: int = 1920,
    height: int = 1080,
    scale: float = 1.0,
) -> list[Path]:
    """Screenshot each of the `count` slides once, in parallel batches.

    Slides are split across several Playwright workers (each its own browser)
    so capture scales with CPU cores. ``scale`` is the browser device pixel
    ratio: the CSS layout stays at ``width`` x ``height`` but the PNG is
    rendered at ``scale``x that size, so text/vectors stay sharp at 2K/4K.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    n_workers = _n_capture_workers(count)
    batches = _split_indices(count, n_workers)
    manifests: list[Path] = []
    for bi, indices in enumerate(batches):
        m = _write_manifest(
            out_dir / f"manifest_still_{bi}.json",
            {
                "html_uri": html_path.resolve().as_uri(),
                "out_dir": str(out_dir),
                "count": count,
                "width": width,
                "height": height,
                "scale": scale,
                "mode": "still",
                "slide_indices": indices,
            },
        )
        manifests.append(m)

    if len(manifests) == 1:
        _run_capture_worker(manifests[0])
    else:
        with ThreadPoolExecutor(max_workers=len(manifests)) as ex:
            list(ex.map(_run_capture_worker, manifests))

    images = sorted(out_dir.glob("slide_*.png"))
    if not images:
        raise RuntimeError("Capture produced no slide images")
    return images


def _write_manifest(path: Path, cfg: dict) -> Path:
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def compute_sparse_capture_frames(
    seek_total: int,
    entrance_frames: int,
    focus_count: int,
    motion_fps: int,
    max_frames: int = 96,
    focus_weights: list[float] | None = None,
) -> tuple[int, list[int]]:
    """Return ``(seek_total, frame_indices)`` for animated capture.

    ``seek_total`` is passed to the page's ``__seekFrame(f, total)`` so highlight
    timing stays synced with narration. ``frame_indices`` is the sparse set of
    frames we actually screenshot — entrance motion, highlight transitions, and
    the final pose — capped at ``max_frames`` so long slides don't produce
    thousands of identical PNGs.

    Focus transition frames use the same lead + text-weighted bands as the HTML
    ``seekSlide`` walk (see ``app.pipeline.sync``).
    """
    from . import sync as sync_mod

    seek_total = max(1, int(seek_total))
    max_frames = max(8, int(max_frames))
    if seek_total <= max_frames:
        return seek_total, list(range(seek_total))

    indices: set[int] = {0, seek_total - 1}
    ent = max(1, min(int(entrance_frames), seek_total))
    step = 1 if ent <= 24 else max(1, ent // 20)
    for f in range(0, ent, step):
        indices.add(f)
    indices.add(min(ent - 1, seek_total - 1))

    if focus_count >= 2:
        weights = focus_weights
        if not weights or len(weights) != focus_count:
            weights = [1.0] * focus_count
        for fi in sync_mod.focus_transition_frames(seek_total, motion_fps, weights):
            indices.add(fi)

    sorted_idx = sorted(indices)
    if len(sorted_idx) > max_frames:
        keep = {0, seek_total - 1, min(ent - 1, seek_total - 1)}
        pool = [i for i in sorted_idx if i not in keep]
        budget = max_frames - len(keep)
        if budget > 0 and pool:
            pick_step = len(pool) / budget
            for j in range(budget):
                keep.add(pool[min(len(pool) - 1, int(j * pick_step))])
        sorted_idx = sorted(keep)

    return seek_total, sorted_idx


def pad_audio_to_duration(audio: Path, min_seconds: float) -> float:
    """If ``audio`` is shorter than ``min_seconds``, append silence (in place).

    Returns the resulting duration. Used so short TTS clips still cover the
    visual entrance + highlight walk instead of cutting motion short.
    """
    if not audio.exists():
        return 0.0
    dur = _ffprobe_duration(audio)
    need = float(min_seconds) - dur
    if need < 0.08:
        return dur
    ffmpeg = ffmpeg_path() or "ffmpeg"
    tmp = audio.with_suffix(audio.suffix + ".padtmp" + audio.suffix)
    # apad extends with silence; -t trims to exact target.
    target = dur + need
    cmd = [
        str(ffmpeg), "-y", "-i", str(audio),
        "-af", f"apad=pad_dur={need:.3f}",
        "-t", f"{target:.3f}",
        str(tmp),
    ]
    try:
        subprocess.run(cmd, capture_output=True, check=False)
        if tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(audio)
            return _ffprobe_duration(audio)
    except Exception:
        pass
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
    return dur


def capture_slides_animated(
    html_path: Path,
    out_dir: Path,
    motion_frames_per_slide: list[int],
    fps: int,
    width: int = 1920,
    height: int = 1080,
    scale: float = 1.0,
    full_slide: bool = False,
    entrance_seconds: float = 1.4,
    capture_indices_per_slide: list[list[int]] | None = None,
) -> list[Path]:
    """Seek-capture each slide's MOTION WINDOW into a per-slide frame folder.

    Returns the per-slide directories (``out_dir/slide_000`` ...), each with
    ``frame_00000.png`` ... covering the entrance motion, plus ``settled.png``
    for the static remainder. The assembler holds ``settled.png`` for the rest
    of the slide's audio, so real motion is preserved without screenshotting
    thousands of identical settled frames.

    Slides are split across several parallel Playwright workers.
    """
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    count = len(motion_frames_per_slide)
    motion = [max(1, int(f)) for f in motion_frames_per_slide]
    indices = capture_indices_per_slide or [list(range(m)) for m in motion]
    n_workers = _n_capture_workers(count)
    batches = _split_indices(count, n_workers)
    manifests: list[Path] = []
    for bi, batch_indices in enumerate(batches):
        m = _write_manifest(
            out_dir / f"manifest_{bi}.json",
            {
                "html_uri": html_path.resolve().as_uri(),
                "out_dir": str(out_dir),
                "count": count,
                "width": width,
                "height": height,
                "scale": scale,
                "mode": "animated",
                "fps": fps,
                "motion_frames_per_slide": motion,
                "capture_indices_per_slide": indices,
                "slide_indices": batch_indices,
                "full_slide": bool(full_slide),
                "entrance_seconds": float(entrance_seconds),
            },
        )
        manifests.append(m)

    if len(manifests) == 1:
        _run_capture_worker(manifests[0])
    else:
        with ThreadPoolExecutor(max_workers=len(manifests)) as ex:
            list(ex.map(_run_capture_worker, manifests))

    slide_dirs = sorted(d for d in out_dir.glob("slide_*") if d.is_dir())
    if not slide_dirs:
        raise RuntimeError("Animated capture produced no frames")
    return slide_dirs


# ---------------------------------------------------------------- segments ----

def _scale_pad_filter(width: int, height: int, pad_color: str = "black") -> str:
    """Letterbox/pillarbox without flashy white bars (dark decks stay dark)."""
    color = (pad_color or "black").strip() or "black"
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=decrease:flags=lanczos,"
        f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:{color},setsar=1"
    )


def build_slide_segment(
    image: Path,
    audio: Path | None,
    out_path: Path,
    fps: int,
    min_seconds: float = 2.5,
    pad_seconds: float = 0.12,
    fade: float = 0.08,
    width: int = 1920,
    height: int = 1080,
) -> Path:
    """Build one slide's video segment.

    If audio is given, the still image is shown for the audio duration plus a
    tiny tail pad (so speech never gets cut off) and muxed with the audio.
    Without audio, the image is shown for `min_seconds`. A short fade in/out is
    applied to video (and audio when present) so slide transitions feel smooth.
    """
    scale_pad = _scale_pad_filter(width, height)
    if audio is not None and audio.exists():
        audio_dur = _ffprobe_duration(audio)
        # Match audio closely — large pads stacked across many slides desync
        # and make the assemble feel sluggish / off.
        dur = max(0.8, audio_dur + pad_seconds)
        fade_use = min(fade, max(0.08, dur * 0.12))
        fo_start = max(0.0, dur - fade_use)
        vf = (
            f"{scale_pad},"
            f"fade=t=in:st=0:d={fade_use},fade=t=out:st={fo_start:.3f}:d={fade_use}"
        )
        # Pad audio to the video length so -t is exact (avoid -shortest cutting
        # the last frames when AAC padding differs from video duration).
        af = (
            f"afade=t=in:st=0:d={fade_use},afade=t=out:st={fo_start:.3f}:d={fade_use},"
            f"apad=whole_dur={dur:.3f},aresample=48000"
        )
        _run_ffmpeg([
            "-y",
            "-loop", "1", "-framerate", str(fps), "-i", str(image),
            "-i", str(audio),
            "-t", f"{dur:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
            "-vf", vf,
            "-af", af,
            str(out_path),
        ])
    else:
        dur = min_seconds
        fade_use = min(fade, max(0.08, dur * 0.12))
        fo_start = max(0.0, dur - fade_use)
        vf = (
            f"{scale_pad},"
            f"fade=t=in:st=0:d={fade_use},fade=t=out:st={fo_start:.3f}:d={fade_use}"
        )
        _run_ffmpeg([
            "-y",
            "-loop", "1", "-framerate", str(fps), "-i", str(image),
            "-t", f"{dur:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            "-vf", vf,
            str(out_path),
        ])
    return out_path


def concat_segments(segments: list[Path], out_path: Path) -> Path:
    """Concatenate slide segments into the final video.

    Prefer a fast stream-copy concat, then verify A/V durations stay aligned.
    If copy produces VFR drift or A/V mismatch, re-encode to constant fps.
    """
    if not segments:
        raise RuntimeError("No segments to concatenate")
    list_file = out_path.parent / "segments.txt"
    list_file.write_text(
        "".join(f"file '{s.resolve().as_posix()}'\n" for s in segments),
        encoding="utf-8",
    )

    def _reencode() -> None:
        out_fps = int(get_settings().capture_fps or 24)
        _run_ffmpeg([
            "-y", "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            *_x264_args(),
            "-r", str(out_fps),
            "-vsync", "cfr",
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
            "-movflags", "+faststart",
            str(out_path),
        ])

    try:
        _run_ffmpeg([
            "-y", "-fflags", "+genpts",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-c", "copy",
            "-movflags", "+faststart",
            str(out_path),
        ])
        # Stream-copy can leave tiny A/V skew; re-encode when drift is large.
        v_dur = _ffprobe_duration(out_path)
        # Probe audio stream duration separately when possible.
        try:
            exe = ffmpeg_path() or "ffmpeg"
            probe = Path(exe).with_name("ffprobe" + (".exe" if exe.endswith(".exe") else ""))
            if probe.exists():
                proc = subprocess.run(
                    [str(probe), "-v", "error", "-select_streams", "a:0",
                     "-show_entries", "stream=duration",
                     "-of", "default=noprint_wrappers=1:nokey=1", str(out_path)],
                    capture_output=True, text=True,
                )
                a_dur = float((proc.stdout or "").strip() or "0") or v_dur
            else:
                a_dur = v_dur
        except Exception:  # noqa: BLE001
            a_dur = v_dur
        if a_dur > 0 and abs(v_dur - a_dur) > 0.35:
            log.bind(task="merge").warning(
                f"A/V drift {v_dur - a_dur:+.2f}s after copy; re-encoding CFR"
            )
            _reencode()
    except Exception as e:  # noqa: BLE001 - fall back to a safe re-encode
        log.bind(task="merge").warning(f"stream-copy concat failed ({e}); re-encoding")
        _reencode()
    list_file.unlink(missing_ok=True)
    return out_path


def build_video_from_slides(
    images: list[Path],
    audios: list[Path | None],
    work: Path,
    fps: int,
    width: int = 1920,
    height: int = 1080,
    on_progress=None,
) -> Path:
    """Build per-slide segments (in parallel) and concatenate into final.mp4."""
    seg_dir = work / "segments"
    if seg_dir.exists():
        shutil.rmtree(seg_dir)
    seg_dir.mkdir(parents=True, exist_ok=True)

    total = len(images)
    done = 0
    lock = threading.Lock()

    def _seg(i_img: tuple[int, Path]) -> tuple[int, Path]:
        nonlocal done
        i, image = i_img
        audio = audios[i] if i < len(audios) else None
        seg = seg_dir / f"seg_{i:03d}.mp4"
        build_slide_segment(image, audio, seg, fps, width=width, height=height)
        if on_progress:
            with lock:
                done += 1
                on_progress(done, total)
        return i, seg

    n = min(_n_capture_workers(len(images)), max(1, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
        built = sorted(ex.map(_seg, list(enumerate(images))), key=lambda t: t[0])
    segments = [s for _, s in built]

    final = work / "final.mp4"
    if on_progress:
        on_progress(total, total, merging=True)
    concat_segments(segments, final)
    shutil.rmtree(seg_dir, ignore_errors=True)
    return final


def _build_frame_segment_keyframes(
    frames_dir: Path,
    audio: Path | None,
    out_path: Path,
    fps: int,
    width: int = 1920,
    height: int = 1080,
    fade: float = 0.08,
    min_seconds: float = 2.5,
    pad_seconds: float = 0.12,
) -> Path:
    """Assemble a slide segment from sparse keyframes + per-frame hold durations."""
    meta = json.loads((frames_dir / "keyframes.json").read_text(encoding="utf-8"))
    keyframes: list[dict] = meta.get("keyframes") or []
    if not keyframes:
        raise RuntimeError(f"Empty keyframes in {frames_dir}")

    cap_fps = float(meta.get("motion_fps") or fps)
    seek_total = int(meta.get("seek_total") or 0)
    natural_dur = (seek_total / cap_fps) if seek_total > 0 else sum(
        float(kf["duration"]) for kf in keyframes
    )

    if audio is not None and audio.exists():
        audio_dur = _ffprobe_duration(audio)
        total = max(0.8, audio_dur + pad_seconds)
    else:
        total = max(min_seconds, natural_dur)

    # Play the captured timeline at natural speed; never stretch/compress to fill
    # long narration — hold the final settled pose for any remaining time.
    hold_dur = max(0.0, total - natural_dur)
    if total < natural_dur * 0.97:
        # Audio shorter than the motion timeline: compress slightly (cap 12%).
        scale = max(0.88, total / natural_dur)
        for kf in keyframes:
            kf["duration"] = float(kf["duration"]) * scale
        hold_dur = 0.0

    settled = frames_dir / "settled.png"
    concat_txt = frames_dir / "_concat.txt"
    lines: list[str] = []
    for kf in keyframes:
        img = frames_dir / kf["file"]
        if not img.is_file():
            continue
        lines.append(f"file '{img.resolve().as_posix()}'")
        lines.append(f"duration {float(kf['duration']):.6f}")
    tail_img = settled if settled.is_file() else frames_dir / keyframes[-1]["file"]
    if hold_dur > 1.0 / cap_fps and tail_img.is_file():
        lines.append(f"file '{tail_img.resolve().as_posix()}'")
        lines.append(f"duration {hold_dur:.6f}")
    # ffmpeg concat demuxer needs the last file repeated without duration.
    lines.append(f"file '{tail_img.resolve().as_posix()}'")
    concat_txt.write_text("\n".join(lines) + "\n", encoding="utf-8")

    scale_pad = _scale_pad_filter(width, height)
    fade_use = min(fade, max(0.08, total * 0.1))
    fo_start = max(0.0, total - fade_use)
    vf = (
        f"{scale_pad},"
        f"fade=t=in:st=0:d={fade_use},fade=t=out:st={fo_start:.3f}:d={fade_use}"
    )

    args = ["-y", "-f", "concat", "-safe", "0", "-i", str(concat_txt)]
    if audio is not None and audio.exists():
        af = (
            f"afade=t=in:st=0:d={fade_use},afade=t=out:st={fo_start:.3f}:d={fade_use},"
            f"apad=whole_dur={total:.3f},aresample=48000"
        )
        args += [
            "-i", str(audio),
            "-filter_complex",
            f"[0:v]fps={fps},format=yuv420p,{vf}[vout];[1:a]{af}[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
            str(out_path),
        ]
    else:
        args += [
            "-filter_complex", f"[0:v]fps={fps},format=yuv420p,{vf}[vout]",
            "-map", "[vout]",
            "-t", f"{total:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            str(out_path),
        ]
    _run_ffmpeg(args)
    concat_txt.unlink(missing_ok=True)
    return out_path


def build_frame_segment(
    frames_dir: Path,
    audio: Path | None,
    out_path: Path,
    fps: int,
    width: int = 1920,
    height: int = 1080,
    fade: float = 0.08,
    min_seconds: float = 2.5,
    pad_seconds: float = 0.12,
    motion_fps: int | None = None,
    full_slide: bool = False,
) -> Path:
    """Build one slide segment from its captured frames + audio.

    Two shapes depending on how the slide was captured:

    * ``full_slide`` — the frames span the WHOLE slide (captured at
      ``motion_fps``) so the per-item highlight walk stays in sync with the
      narration. We play them at ``motion_fps`` and hold the final frame for any
      residual time so the segment length == the audio length (+ tail pad).
    * entrance-only — the frames are just the entrance motion; ``settled.png``
      is held for the rest of the slide's audio (cheap static remainder).

    Sparse keyframe captures write ``keyframes.json``; durations are derived
    from the seek timeline so highlight sync is preserved without thousands of
    PNGs.
    """
    keyframes_path = frames_dir / "keyframes.json"
    if keyframes_path.exists():
        return _build_frame_segment_keyframes(
            frames_dir, audio, out_path, fps, width, height, fade, min_seconds, pad_seconds
        )
    cap_fps = int(motion_fps or fps)
    motion_frames = sorted(frames_dir.glob("frame_*.png"))
    settled = frames_dir / "settled.png"
    if not settled.exists() and motion_frames:
        settled = motion_frames[-1]

    motion_dur = max(0.0, len(motion_frames) / float(cap_fps))
    if audio is not None and audio.exists():
        total = max(0.8, _ffprobe_duration(audio) + pad_seconds)
    else:
        total = max(min_seconds, motion_dur)
    # Hold settled for remaining audio; keep a tiny hold so concat always has
    # a second input even when audio ≈ motion window.
    hold = max(1.0 / float(cap_fps), total - motion_dur)
    total = motion_dur + hold

    scale_pad = _scale_pad_filter(width, height)
    fade_use = min(fade, max(0.08, total * 0.1))
    fo_start = max(0.0, total - fade_use)
    vf = (
        f"{scale_pad},"
        f"fade=t=in:st=0:d={fade_use},fade=t=out:st={fo_start:.3f}:d={fade_use}"
    )

    # Build video input: concat the motion frame sequence with a looped settled
    # still. Using a filtergraph concat avoids an intermediate file per slide.
    inputs: list[str] = []
    frames_glob = str(frames_dir / "frame_%05d.png")
    has_motion = bool(motion_frames)
    if has_motion:
        inputs += ["-framerate", str(cap_fps), "-i", frames_glob]
    inputs += ["-loop", "1", "-framerate", str(cap_fps), "-t", f"{hold:.3f}", "-i", str(settled)]

    if has_motion:
        # [motion][settled-hold] concatenated then resampled to the OUTPUT fps.
        vconcat = (
            f"[0:v]setsar=1,format=yuv420p[m];"
            f"[1:v]fps={cap_fps},setsar=1,format=yuv420p[h];"
            "[m][h]concat=n=2:v=1:a=0[vv];"
            f"[vv]fps={fps},{vf}[vout]"
        )
    else:
        vconcat = f"[0:v]fps={fps},format=yuv420p,{vf}[vout]"

    args = ["-y", *inputs]
    if audio is not None and audio.exists():
        args += ["-i", str(audio)]
        af = (
            f"afade=t=in:st=0:d={fade_use},afade=t=out:st={fo_start:.3f}:d={fade_use},"
            f"apad=whole_dur={total:.3f},aresample=48000"
        )
        args += [
            "-filter_complex", vconcat + f";[{2 if has_motion else 1}:a]{af}[aout]",
            "-map", "[vout]", "-map", "[aout]",
            "-t", f"{total:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-ac", "2",
            str(out_path),
        ]
    else:
        args += [
            "-filter_complex", vconcat,
            "-map", "[vout]",
            "-t", f"{total:.3f}",
            "-r", str(fps),
            "-vsync", "cfr",
            *_x264_args(),
            str(out_path),
        ]
    _run_ffmpeg(args)
    return out_path


def build_video_from_frame_sequences(
    slide_dirs: list[Path],
    audios: list[Path | None],
    work: Path,
    fps: int,
    width: int = 1920,
    height: int = 1080,
    motion_fps: int | None = None,
    full_slide: bool = False,
    per_slide_full: list[bool] | None = None,
    on_progress=None,
) -> Path:
    """Assemble animated per-slide frame folders + audio into final.mp4.

    Segments are built in parallel (ffmpeg is single-threaded per segment for
    determinism, but many segments can encode at once) then concatenated.
    """
    seg_dir = work / "segments"
    if seg_dir.exists():
        shutil.rmtree(seg_dir)
    seg_dir.mkdir(parents=True, exist_ok=True)

    total = len(slide_dirs)
    done = 0
    lock = threading.Lock()

    def _seg(i_dir: tuple[int, Path]) -> tuple[int, Path]:
        nonlocal done
        i, frames_dir = i_dir
        audio = audios[i] if i < len(audios) else None
        seg = seg_dir / f"seg_{i:03d}.mp4"
        slide_full = full_slide
        if per_slide_full and i < len(per_slide_full):
            slide_full = bool(per_slide_full[i])
        try:
            build_frame_segment(
                frames_dir, audio, seg, fps, width=width, height=height,
                motion_fps=motion_fps, full_slide=slide_full,
            )
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"assemble slide {i:03d} failed ({frames_dir.name}): {e}") from e
        if on_progress:
            with lock:
                done += 1
                on_progress(done, total)
        return i, seg

    n = min(_n_capture_workers(len(slide_dirs)), max(1, (os.cpu_count() or 4)))
    with ThreadPoolExecutor(max_workers=max(1, n)) as ex:
        try:
            built = sorted(ex.map(_seg, list(enumerate(slide_dirs))), key=lambda t: t[0])
        except Exception as e:  # noqa: BLE001
            log.bind(task="merge").error(f"parallel segment encode failed: {e}")
            raise
    segments = [s for _, s in built]
    missing = [s for s in segments if not s.is_file() or s.stat().st_size < 256]
    if missing:
        raise RuntimeError(f"assemble produced empty segments: {[p.name for p in missing]}")

    final = work / "final.mp4"
    if on_progress:
        on_progress(total, total, merging=True)
    concat_segments(segments, final)
    shutil.rmtree(seg_dir, ignore_errors=True)
    return final
