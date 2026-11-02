"""Thumbnail image generation via Muse Image (cloud).

Local diffusion backends (Boogu / SANA / Z-Image) were removed — re-add later
via a separate optional install. ``auto`` uses Muse Image when
``MODEL_API_KEY`` is set; callers may fall back to a slide-frame capture.
"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging_setup import log


def build_prompt(title: str, summary: str = "") -> str:
    """Alias for the Nano Banana thumbnail brief."""
    return build_nano_banana_prompt(title, summary)


def build_nano_banana_prompt(title: str, summary: str = "") -> str:
    """Prompt tuned for Nano Banana Pro (can render legible on-image text)."""
    title = (title or "Lesson").strip()
    summary = (summary or "").strip()
    parts = [
        "Create a bold YouTube thumbnail, 16:9 landscape, high contrast.",
        f'Large readable title text on the image: "{title}".',
        "Modern tech explainer style: dark cinematic background, vivid accent color,",
        "one clear focal subject, clean composition, professional YouTube click-worthy look.",
        "No watermarks, no UI chrome, no tiny unreadable text.",
    ]
    if summary:
        parts.append(f"Theme / subject: {summary[:180]}.")
    return " ".join(parts)


def _probe_nano_banana() -> tuple[bool, str]:
    s = get_settings()
    if not (s.model_api_key or "").strip():
        return False, "Muse Image needs MODEL_API_KEY in .env."
    return True, ""


def probe_backends() -> dict[str, Any]:
    """Return availability + human-readable reasons for each thumbnail backend."""
    nb_ok, nb_why = _probe_nano_banana()
    return {
        "nano_banana": nb_ok,
        "nano_banana_reason": nb_why,
        "muse_image_model": (get_settings().muse_image_model or "muse-image-1.0"),
        "any_image": nb_ok,
    }


def _generate_nano_banana(prompt: str, out_path: Path) -> tuple[Path | None, str]:
    try:
        from . import llm_client

        path = llm_client.generate_image(prompt, out_path)
        return path, ""
    except Exception as e:  # noqa: BLE001
        return None, f"Muse Image unavailable: {e}"


def _load_font(size: int):
    from PIL import ImageFont

    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
        "/Library/Fonts/Arial Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
    ]
    for path in candidates:
        try:
            if Path(path).is_file():
                return ImageFont.truetype(path, size)
        except Exception:
            continue
    try:
        return ImageFont.truetype("DejaVuSans-Bold.ttf", size)
    except Exception:
        return ImageFont.load_default()


def _wrap_text(draw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    cur = ""
    for w in words:
        trial = f"{cur} {w}".strip()
        width = draw.textbbox((0, 0), trial, font=font)[2]
        if width <= max_width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def overlay_title(image_path: Path, title: str) -> tuple[Path | None, str]:
    """Draw a large, readable title onto a generated thumbnail image."""
    title = (title or "").strip()
    if not title:
        return image_path, "No title to overlay."
    try:
        from PIL import Image, ImageDraw

        img = Image.open(image_path).convert("RGB")
        W, H = img.size
        draw = ImageDraw.Draw(img, "RGBA")

        margin = int(W * 0.05)
        max_text_w = W - 2 * margin
        font_size = int(H * 0.14) if len(title) <= 40 else int(H * 0.11)
        font = _load_font(font_size)
        lines = _wrap_text(draw, title, font, max_text_w)
        while len(lines) > 3 and font_size > int(H * 0.06):
            font_size = int(font_size * 0.9)
            font = _load_font(font_size)
            lines = _wrap_text(draw, title, font, max_text_w)

        line_h = draw.textbbox((0, 0), "Ag", font=font)[3] + int(font_size * 0.18)
        block_h = line_h * len(lines)

        scrim_top = max(0, H - block_h - int(H * 0.14))
        scrim = Image.new("RGBA", (W, H - scrim_top), (0, 0, 0, 0))
        sdraw = ImageDraw.Draw(scrim)
        sh = H - scrim_top
        for y in range(sh):
            alpha = int(210 * (y / sh) ** 1.4)
            sdraw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
        img.paste(scrim, (0, scrim_top), scrim)

        draw = ImageDraw.Draw(img, "RGBA")
        y = H - block_h - int(H * 0.06)
        stroke = max(2, int(font_size * 0.06))
        accent = (255, 214, 10)
        for idx, ln in enumerate(lines):
            color = accent if (idx == len(lines) - 1 and len(lines) > 1) else (255, 255, 255)
            draw.text(
                (margin, y), ln, font=font, fill=color,
                stroke_width=stroke, stroke_fill=(0, 0, 0),
            )
            y += line_h

        img.save(image_path)
        return image_path, "Title overlaid on thumbnail."
    except Exception as e:  # noqa: BLE001
        log.bind(task="thumbnail").warning(f"title overlay skipped: {e}")
        return image_path, f"Title overlay skipped ({e})."


def _backend_order(backend: str) -> list[str]:
    backend = (backend or "auto").strip().lower()
    if backend in ("off", "none", "disabled"):
        return []
    # Legacy local backends removed — map to Nano Banana so old .env values work.
    if backend in (
        "boogu", "boogu_edit", "edit_turbo", "sana", "diffusers",
        "zimage", "z-image", "ollama",
    ):
        log.bind(task="thumbnail").warning(
            f"thumbnail backend '{backend}' removed; using nano_banana"
        )
        return ["nano_banana"]
    if backend in ("nano_banana", "muse", "muse_image", "nano-banana", "nanobanana", "auto", ""):
        return ["nano_banana"]
    return ["nano_banana"]


def _copy_thumb_src(src: Path, out_path: Path, msg: str) -> tuple[Path | None, str]:
    try:
        if not src.is_file() or src.stat().st_size < 256:
            return None, ""
        out_path.parent.mkdir(parents=True, exist_ok=True)
        if src.resolve() != out_path.resolve():
            shutil.copyfile(src, out_path)
        return out_path, msg
    except Exception:
        return None, ""


def fallback_slide_thumbnail(
    work: Path, job_id: str, artifacts: dict, content: dict, out_path: Path
) -> tuple[Path | None, str]:
    """Best-effort thumbnail when image backends fail (works after pages cleanup)."""
    # Already-generated thumbnail (e.g. prior run / pipeline).
    path, msg = _copy_thumb_src(out_path, out_path, "Thumbnail already present.")
    if path is not None:
        return path, msg
    for name in ("thumbnail.png", "cover.png", "cover.jpg", "cover.jpeg", "cover.webp"):
        path, msg = _copy_thumb_src(
            work / name, out_path, f"Thumbnail fallback: {name}."
        )
        if path is not None:
            return path, msg

    # Live page / shot folders (pre-finalize).
    for folder_name in ("pages", "pages_shots", "shots"):
        folder = work / folder_name
        if not folder.is_dir():
            continue
        images = sorted(folder.glob("page_*.png")) + sorted(folder.glob("page_*.jpg"))
        if not images:
            images = sorted(folder.glob("*.png")) + sorted(folder.glob("*.jpg"))
        for src in images:
            path, msg = _copy_thumb_src(
                src, out_path, f"Thumbnail fallback: {folder_name}/{src.name}."
            )
            if path is not None:
                return path, msg

    candidates: list[str] = []
    for url in artifacts.get("pages_shots") or []:
        if isinstance(url, str):
            candidates.append(url)
    for rel in content.get("shot_files") or []:
        if isinstance(rel, str):
            candidates.append(f"/files/{job_id}/{rel.lstrip('/')}")

    prefix = f"/files/{job_id}/"
    work_resolved = work.resolve()
    for url in candidates:
        if not url.startswith(prefix):
            continue
        rel = url[len(prefix):]
        src = (work / rel).resolve()
        try:
            if not str(src).startswith(str(work_resolved)):
                continue
        except Exception:
            continue
        path, msg = _copy_thumb_src(src, out_path, "Thumbnail fallback: first slide frame.")
        if path is not None:
            return path, msg

    # Last resort: grab a frame from the finished video.
    video = work / "final.mp4"
    if not video.is_file():
        video = work / "raw.mp4"
    if video.is_file():
        try:
            import subprocess

            out_path.parent.mkdir(parents=True, exist_ok=True)
            proc = subprocess.run(
                [
                    "ffmpeg", "-y", "-ss", "1", "-i", str(video),
                    "-frames:v", "1", "-q:v", "2", str(out_path),
                ],
                capture_output=True,
                timeout=60,
            )
            if proc.returncode == 0 and out_path.is_file() and out_path.stat().st_size > 256:
                return out_path, "Thumbnail fallback: video frame."
        except Exception:
            pass

    return None, "No slide frame available for thumbnail fallback."


def generate_thumbnail(
    title: str,
    summary: str,
    out_path: Path,
    *,
    prompt_override: str | None = None,
    backend_override: str | None = None,
) -> tuple[Path | None, str]:
    """Generate a thumbnail image, returning ``(path_or_None, message)``."""
    settings = get_settings()
    if not settings.generate_thumbnail and backend_override is None:
        return None, "Thumbnail generation is disabled."

    backend = (backend_override or settings.thumbnail_backend or "auto").strip().lower()
    if backend in ("off", "none", "disabled"):
        return None, "Thumbnail generation is disabled."

    nano_prompt = prompt_override or build_nano_banana_prompt(title, summary)
    order = _backend_order(backend)
    messages: list[str] = []

    for b in order:
        ok, why = _probe_nano_banana()
        if not ok:
            messages.append(why)
            log.bind(task="thumbnail").warning(f"Image backend {b} unavailable: {why}")
            continue
        log.bind(task="thumbnail").info(f"Image backend '{b}' available; generating")
        path, msg = _generate_nano_banana(nano_prompt, out_path)
        if path is not None:
            log.bind(task="thumbnail").success(f"thumbnail via {b}: {path.name}")
            # Nano Banana can render title text in-image — skip Pillow overlay.
            return path, "Thumbnail generated via Nano Banana Pro (nano_banana)."
        messages.append(msg)
        log.bind(task="thumbnail").warning(msg)

    return None, " ".join(messages) or "No thumbnail backend available."
