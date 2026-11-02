"""Standalone Playwright capture worker.

Run as a subprocess so Playwright's sync API gets a clean, subprocess-capable
event loop (avoids Windows NotImplementedError when launched from the server's
async context).

Two capture modes:

* STILL (default): one screenshot per slide. Slides are static; their on-screen
  time is governed by the matching narration audio downstream. Simplest and
  fastest.
* ANIMATED (seek-frame): for each slide, drive the page's deterministic frame
  timeline via ``window.__seekFrame(frame, totalFrames)`` and screenshot every
  frame IN THE MOTION WINDOW only, then capture ONE settled frame. The slide's
  entrance animation lasts ~``motion_seconds``; after that the slide is static,
  so there is no point screenshotting thousands of identical "settled" frames.
  The assembler (ffmpeg) holds the settled frame for the remaining audio time.
  This keeps real in-slide motion (Remotion/HyperFrames-style seek rendering)
  while cutting the screenshot count from thousands to a few dozen per slide.

Parallelism:
  A manifest may include ``slide_indices`` — the subset of slides THIS worker
  should render. The orchestrator launches several workers over disjoint index
  ranges (each with its own browser) so capture scales across CPU cores. Output
  paths are keyed by absolute slide index, so batches never collide.

Usage:
    # still (legacy positional form)
    python -m app.pipeline.capture_worker <html_uri> <out_dir> <count> [w] [h] [scale]
    # either mode via a JSON manifest
    python -m app.pipeline.capture_worker --manifest <manifest.json>

Manifest JSON:
    {
      "html_uri": "file:///.../presentation.html",
      "out_dir": "/.../shots",
      "count": 12,
      "width": 1920, "height": 1080, "scale": 2.0,
      "mode": "animated",            # or "still"
      "fps": 24,
      "motion_frames_per_slide": [40, 40, ...],  # animated: frames to capture
      "slide_indices": [0, 1, 2]     # optional subset for this worker
    }

STILL mode writes out_dir/slide_000.png ... slide_{count-1}.png
ANIMATED mode writes out_dir/slide_{i:03d}/frame_{f:05d}.png for each slide i,
plus out_dir/slide_{i:03d}/settled.png (the final settled pose).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _parse_args() -> dict:
    argv = sys.argv[1:]
    if argv and argv[0] == "--manifest":
        data = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
        return data
    # Legacy positional form (still mode).
    if len(argv) not in (3, 5, 6):
        print(
            "usage: capture_worker <html_uri> <out_dir> <count> [width] [height] "
            "[scale]  OR  --manifest <manifest.json>",
            file=sys.stderr,
        )
        raise SystemExit(2)
    return {
        "html_uri": argv[0],
        "out_dir": argv[1],
        "count": int(argv[2]),
        "width": int(argv[3]) if len(argv) >= 5 else 1920,
        "height": int(argv[4]) if len(argv) >= 5 else 1080,
        "scale": float(argv[5]) if len(argv) == 6 else 1.0,
        "mode": "still",
    }


def _prepare_slide(page, n: int) -> None:
    """Navigate to slide n and wait until it signals capture-ready."""
    page.evaluate("(n) => window.gotoSlide(n)", n)
    try:
        page.wait_for_function("() => window.__slideReady === true", timeout=12000)
    except Exception:
        page.wait_for_timeout(800)


def main() -> int:
    cfg = _parse_args()
    html_uri = cfg["html_uri"]
    out_dir = Path(cfg["out_dir"])
    count = int(cfg["count"])
    width = int(cfg.get("width", 1920))
    height = int(cfg.get("height", 1080))
    scale = float(cfg.get("scale", 1.0))
    mode = cfg.get("mode", "still")
    fps = int(cfg.get("fps", 24))
    entrance_seconds = float(cfg.get("entrance_seconds", 1.4))
    motion_frames_per_slide = cfg.get("motion_frames_per_slide") or []
    capture_indices_per_slide = cfg.get("capture_indices_per_slide") or []
    full_slide = bool(cfg.get("full_slide"))
    # Subset of slides this worker renders (for parallel batches). Default: all.
    slide_indices = cfg.get("slide_indices")
    if not slide_indices:
        slide_indices = list(range(count))
    out_dir.mkdir(parents=True, exist_ok=True)

    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage", "--disable-gpu"],
        )
        # device_scale_factor renders the page at a higher pixel density so the
        # captured PNGs are crisp when used for 2K/4K video (the logical CSS
        # layout stays the same; only the pixel resolution increases).
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=scale if scale and scale > 0 else 1.0,
        )
        # Expose the capture fps to the page timeline BEFORE it initializes so
        # frame->time math matches the worker.
        page.add_init_script(f"window.__captureFps = {fps};")
        page.add_init_script(f"window.__entranceSeconds = {entrance_seconds};")
        # "load" waits for Google Fonts and the CDN stylesheets. On Cloud Run
        # that request often never finishes, so the capture stage spins forever.
        # DOM-ready is enough; fonts get a short extra wait and then we shoot.
        page.set_default_navigation_timeout(25000)
        page.set_default_timeout(20000)
        page.goto(html_uri, wait_until="domcontentloaded", timeout=25000)
        # Wait until the page module finished loading and exposed gotoSlide
        # (the Mermaid ESM import is async). Then render each slide on demand.
        try:
            page.wait_for_function(
                "() => typeof window.gotoSlide === 'function'", timeout=15000
            )
        except Exception:
            page.wait_for_timeout(1500)
        try:
            page.wait_for_function(
                "() => !document.fonts || document.fonts.status === 'loaded'",
                timeout=4000,
            )
        except Exception:
            pass
        # Hide the on-screen nav HUD (and disable wall-clock CSS entrances in the
        # page) so captured frames are clean and deterministic.
        try:
            page.evaluate("() => window.enterCaptureMode && window.enterCaptureMode()")
        except Exception:
            pass
        page.wait_for_timeout(600)  # let mermaid + fonts settle

        animated = (
            mode == "animated"
            and page.evaluate("() => typeof window.__seekFrame === 'function'")
        )

        if animated:
            for n in slide_indices:
                _prepare_slide(page, n)
                seek_total = (
                    int(motion_frames_per_slide[n])
                    if n < len(motion_frames_per_slide) else fps * 2
                )
                seek_total = max(1, seek_total)
                if capture_indices_per_slide and n < len(capture_indices_per_slide):
                    frame_indices = [
                        max(0, min(seek_total - 1, int(f)))
                        for f in capture_indices_per_slide[n]
                    ] or [0]
                else:
                    frame_indices = list(range(seek_total))
                slide_dir = out_dir / f"slide_{n:03d}"
                slide_dir.mkdir(parents=True, exist_ok=True)
                sparse = len(frame_indices) < seek_total
                for out_i, f in enumerate(frame_indices):
                    page.evaluate(
                        "(a) => window.__seekFrame(a.f, a.t)",
                        {"f": f, "t": seek_total},
                    )
                    page.screenshot(path=str(slide_dir / f"frame_{out_i:05d}.png"))
                page.evaluate(
                    """(a) => {
                      document.body.classList.add('settled');
                      if (window.__seekFrame) window.__seekFrame(a.f, a.t);
                      if (window.__settleFrame) window.__settleFrame();
                    }""",
                    {"f": seek_total - 1, "t": seek_total},
                )
                page.screenshot(path=str(slide_dir / "settled.png"))
                page.evaluate("() => document.body.classList.remove('settled')")
                # Always write keyframes metadata so assemble can hold settled
                # for remaining audio with correct seek-timeline durations.
                keyframes = []
                for out_i, f in enumerate(frame_indices):
                    next_f = (
                        frame_indices[out_i + 1]
                        if out_i + 1 < len(frame_indices)
                        else seek_total
                    )
                    keyframes.append({
                        "file": f"frame_{out_i:05d}.png",
                        "duration": max(1.0 / fps, (next_f - f) / float(fps)),
                    })
                (slide_dir / "keyframes.json").write_text(
                    json.dumps({
                        "seek_total": seek_total,
                        "motion_fps": fps,
                        "sparse": sparse,
                        "keyframes": keyframes,
                    }),
                    encoding="utf-8",
                )
        else:
            for n in slide_indices:
                _prepare_slide(page, n)
                page.wait_for_timeout(150)
                page.screenshot(path=str(out_dir / f"slide_{n:03d}.png"))

        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
