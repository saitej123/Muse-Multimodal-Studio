"""Orchestrates the pipeline. Stages can run as a full sequence or individually.

Design goals:
- VLM extraction first (PDF/image -> page images -> Muse vision transcription),
  falling back to plain pypdf text when the VLM is unavailable.
- Editable content: `extracted_text` and `narration` live on the job and can be
  edited by the user, then individual stages re-run to improve the result.
- Every mutation publishes an event so the API can stream live updates.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

from . import costs
from .capabilities import detect_capabilities
from .config import WORKSPACE_DIR, get_settings
from .jobs import Job, StageStatus, store
from .logging_setup import log
from .pipeline import content, extract, media, publish
from .pipeline import metadata as meta_gen
from .pipeline import thumbnail as thumb_gen
from .video_options import get_video_spec, resolve_output_dimensions


def _pulse(job: Job, key: str, prog: dict):
    """Keep a long stage's detail line moving so the UI does not look frozen."""
    stop = threading.Event()
    started = time.time()

    def _run() -> None:
        while not stop.wait(8):
            elapsed = int(time.time() - started)
            store.note(job, key, f"{prog.get('line') or 'Working'} · {elapsed}s")

    threading.Thread(target=_run, name=f"pulse-{key}", daemon=True).start()
    return stop


def _keep_files(job: Job) -> None:
    """Keep generated files in the job folder on disk."""
    try:
        from . import blob_store

        blob_store.sync_workspace_async(job.id, _work(job))
    except Exception as e:  # noqa: BLE001
        log.bind(task="pipeline").warning(f"file sync skipped: {e}")


def _work(job: Job) -> Path:
    from .workspace_store import resolve_job_dir

    return resolve_job_dir(job.id, create=True)


def _input_path(job: Job) -> Path:
    work = _work(job)
    for name in (
        "input.pdf", "input.png", "input.jpg", "input.jpeg",
        "input.webp", "input.bmp", "input.gif",
    ):
        p = work / name
        if p.exists():
            return p
    # Fallback: any file named input.* that was saved on upload.
    for p in sorted(work.glob("input.*")):
        return p
    return work / "input.pdf"


def _ensure_cover_page_image(src: Path, work: Path) -> list[Path]:
    """Render at least page 1 for cover slides (works even when VLM is off).

    Research-paper intros need ``pages/page_000.png``. VLM normally creates
    these; without VLM we still rasterize the first PDF page (or convert Office
    → PDF via LibreOffice when available).
    """
    pages_dir = work / "pages"
    existing = sorted(pages_dir.glob("page_000.*")) or sorted(pages_dir.glob("img_000.*"))
    if existing:
        return existing

    suffix = src.suffix.lower()
    try:
        if suffix == ".pdf":
            images = extract.render_pdf_to_images(src, pages_dir, max_pages=1)
            if images:
                log.bind(task="extract").info(
                    f"cover page rendered: {images[0].name}"
                )
            return images
        if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
            return extract._copy_image_input(src, pages_dir)
        pdf = extract._office_to_pdf(src, work / "convert")
        if pdf and pdf.exists():
            return extract.render_pdf_to_images(pdf, pages_dir, max_pages=1)
    except Exception as e:
        log.bind(task="extract").warning(f"cover page render skipped: {e}")
    return []


# ---------------------------------------------------------------- stages ----

def stage_extract(job: Job) -> None:
    caps = detect_capabilities()
    work = _work(job)
    src = _input_path(job)
    log.bind(task="extract").info(
        f"job {job.id}: {src.name} (vlm={'on' if caps.vlm else 'off'}, provider={caps.provider})"
    )
    store.set_stage(job, "extract", StageStatus.RUNNING)
    try:
        images: list[Path] = []
        if caps.vlm:
            text, images = extract.extract_with_vlm(src, work)
            if images:
                store.set_artifact(
                    job, "pages",
                    [f"/files/{job.id}/pages/{p.name}" for p in images],
                )
            method = f"VLM vision ({len(images)} page image(s))"
            if not text:
                text = extract.extract_text_any(src)
                method = "VLM returned empty; used text fallback"
        else:
            text = extract.extract_text_any(src)
            method = "Plain text extraction"

        # Always try to have page_000 for paper covers (classifier decides later).
        if not images:
            images = _ensure_cover_page_image(src, work)
            if images and method == "Plain text extraction":
                method = "Plain text + cover page"
        if images and not (job.artifacts or {}).get("pages"):
            store.set_artifact(
                job, "pages",
                [f"/files/{job.id}/pages/{p.name}" for p in images],
            )

        # Flag missing / sparse content so the UI can highlight it instead of
        # silently producing a near-empty lesson.
        word_count = len((text or "").split())
        if not text:
            text = "No extractable content was found in the document."
            warning = "No text could be extracted from the input. Check the file or edit the content below."
        elif word_count < 40:
            warning = (
                f"Only {word_count} words were extracted — the lesson may be very short. "
                "Consider editing the content or uploading a clearer document."
            )
        else:
            warning = ""
        store.set_content(job, "extracted_text", text)
        store.set_content(job, "extract_warning", warning)
        if warning:
            log.bind(task="extract").warning(warning)
        store.set_content(job, "extracted_word_count", word_count)
        store.set_stage(
            job, "extract", StageStatus.DONE,
            f"{method} \u2022 {len(text):,} chars / {word_count:,} words"
            + (" \u26a0\ufe0f sparse" if warning else ""),
        )
        log.bind(task="extract").success(f"{method} -> {word_count:,} words")
    except Exception as e:
        log.bind(task="extract").error(f"extract failed: {e}")
        store.set_stage(job, "extract", StageStatus.ERROR, str(e))
        raise


def stage_generate(job: Job) -> None:
    work = _work(job)
    raw_text = job.content.get("extracted_text", "")
    store.set_stage(job, "generate", StageStatus.RUNNING)
    try:
        # Live web research for "Add topics" / topic-only jobs.
        # For uploaded document/screenshot VLM jobs, do NOT mix in external web research
        # unless explicitly enabled via enable_web_research.
        topics_raw = (job.options.get("extra_topics") or "").strip()
        section_title = (job.options.get("section_title") or "").strip()
        if section_title and section_title.lower() not in topics_raw.lower():
            topics_raw = ", ".join(filter(None, [topics_raw, section_title]))
        is_topic_job = (
            job.options.get("automation_kind") == "topic"
            or job.options.get("batch_mode") in {"per_topic", "single"}
            or not raw_text
        )
        enable_research = bool(job.options.get("enable_web_research"))
        # Topic-plan children default to web research for quality.
        if job.options.get("batch_mode") and job.options.get("enable_web_research", True):
            enable_research = True
        if topics_raw and (is_topic_job or enable_research):
            try:
                from .pipeline import topic_research

                ctx = (
                    job.content.get("slide_title")
                    or job.content.get("title")
                    or section_title
                    or job.filename
                    or ""
                )
                # Bias searches with a short slice of the source document.
                if raw_text:
                    ctx = f"{ctx} {(raw_text or '')[:280]}".strip()
                brief, meta = topic_research.research_topics(topics_raw, context=ctx)
                if brief:
                    job.options["topic_research"] = brief
                store.set_content(job, "topic_research", meta)
                backends = ", ".join(meta.get("backends") or []) or "none"
                log.bind(task="generate").info(
                    f"topic research via {backends} ({meta.get('chars', 0)} chars)"
                )
            except Exception as e:
                log.bind(task="generate").warning(f"topic research skipped: {e}")

        # Deep grounding for planned topic videos (Muse search + structured brief).
        if (
            job.options.get("use_topic_prep")
            and enable_research
            and (section_title or topics_raw)
        ):
            try:
                from .pipeline import topic_prep

                topic_name = section_title or topics_raw.split(",")[0].strip()
                prep = topic_prep.prepare_topic(topic_name)
                enriched = topic_prep.brief_to_source_text(prep)
                if enriched:
                    raw_text = (
                        f"{raw_text}\n\n---\n\n## Live web-grounded brief\n\n{enriched}"
                    )
                    store.set_content(job, "extracted_text", raw_text)
                    store.set_content(job, "topic_citations", prep.get("citations") or [])
                    store.set_content(
                        job, "topic_truthfulness", prep.get("truthfulness") or "medium"
                    )
                    store.set_content(job, "topic_prep_model", prep.get("model") or "")
                    job.options["topic_prep"] = {
                        "truthfulness": prep.get("truthfulness"),
                        "citations": prep.get("citations") or [],
                        "model": prep.get("model"),
                    }
                    log.bind(task="generate").info(
                        f"deep topic prep for {topic_name!r} via {prep.get('model')}"
                    )
            except Exception as e:  # noqa: BLE001
                log.bind(task="generate").warning(f"topic prep soft-fail: {e}")

        # If we rendered document page images during extraction, offer the first
        # page as a cover image so papers/books open by showing the real
        # document. Path is relative to the HTML file so it works under both
        # file:// (capture) and /files (browser preview).
        cover_image = None
        page_files = sorted((work / "pages").glob("page_000.*")) or \
            sorted((work / "pages").glob("img_000.*"))
        if page_files:
            cover_image = f"pages/{page_files[0].name}"

        # If extract somehow skipped pages, try once more before generate.
        if not cover_image:
            _ensure_cover_page_image(_input_path(job), work)
            page_files = sorted((work / "pages").glob("page_000.*")) or \
                sorted((work / "pages").glob("img_000.*"))
            if page_files:
                cover_image = f"pages/{page_files[0].name}"

        html_path = work / "presentation.html"
        job.options["work_dir"] = str(work)
        job.options["job_id"] = job.id
        model, used_llm = content.generate_animated_html(
            raw_text, html_path, job.options, cover_image=cover_image
        )
        store.set_artifact(job, "html", f"/files/{job.id}/presentation.html")
        if model.get("agent_receipt"):
            store.set_content(job, "agent_receipt", model["agent_receipt"])
            trace_file = work / "agent_trace.jsonl"
            if trace_file.exists():
                store.set_artifact(job, "agent_trace", f"/files/{job.id}/agent_trace.jsonl")
        store.set_content(job, "slides", model["slides"])
        store.set_content(job, "slide_title", model.get("title", "Overview"))
        if model.get("doc_type"):
            store.set_content(job, "doc_type", model["doc_type"])
        if model.get("doc_analysis"):
            store.set_content(job, "doc_analysis", model["doc_analysis"])
        if model.get("video_style"):
            job.options["video_style"] = model["video_style"]
            if model.get("video_style_label"):
                job.options["video_style_label"] = model["video_style_label"]
            if model.get("video_style_reason"):
                job.options["video_style_reason"] = model["video_style_reason"]
                store.set_content(job, "video_style_reason", model["video_style_reason"])
            elif "video_style_reason" in job.options:
                job.options.pop("video_style_reason", None)
            store.set_content(job, "video_style", model["video_style"])
            if model.get("video_style_was_auto") is not None:
                job.options["video_style_was_auto"] = bool(model["video_style_was_auto"])
        if model.get("video_theme"):
            job.options["video_theme"] = model["video_theme"]
            if model.get("video_theme_label"):
                job.options["video_theme_label"] = model["video_theme_label"]
            if model.get("video_theme_reason"):
                job.options["video_theme_reason"] = model["video_theme_reason"]
                store.set_content(job, "video_theme_reason", model["video_theme_reason"])
            elif "video_theme_reason" in job.options:
                job.options.pop("video_theme_reason", None)
            store.set_content(job, "video_theme", model["video_theme"])
            if model.get("video_theme_was_auto") is not None:
                job.options["video_theme_was_auto"] = bool(model["video_theme_was_auto"])
        # New content invalidates any previously generated publish metadata /
        # thumbnail so publish_meta regenerates them from the fresh lesson.
        for k in ("publish_title", "publish_description", "publish_tags", "thumbnail"):
            if k in job.content:
                store.set_content(job, k, None)
        # Keep an editable, joined narration for the UI text box.
        narr_list = []
        for s in model.get("slides", []):
            if isinstance(s, dict):
                narr_list.append(str(s.get("narration") or ""))
            elif isinstance(s, str):
                narr_list.append(s)
        store.set_content(
            job, "narration",
            "\n\n".join(narr_list).strip(),
        )
        try:
            from .pipeline.content_review import review_slides

            review = review_slides(
                model.get("slides") or [],
                options=job.options,
                narration=job.content.get("narration") or "",
                user_notes=str(job.options.get("review_notes") or ""),
            )
            store.set_content(job, "content_review", review)
        except Exception as e:  # noqa: BLE001
            log.bind(task="generate").warning(f"content review skipped: {e}")
        doc_note = f", {model.get('doc_type', 'doc')}" if model.get("doc_type") else ""
        style_note = ""
        if model.get("video_style"):
            style_note = f", style={model['video_style']}"
            if model.get("video_style_was_auto"):
                style_note += " (auto)"
        research_meta = job.content.get("topic_research") or {}
        research_note = ""
        if isinstance(research_meta, dict) and research_meta.get("topics"):
            n_topics = len(research_meta["topics"])
            research_note = f", web research×{n_topics}"
        review = job.content.get("content_review") or {}
        review_note = ""
        if isinstance(review, dict) and review.get("counts"):
            c = review["counts"]
            if c.get("errors") or c.get("warnings"):
                review_note = (
                    f", review: {c.get('duplicates', 0)} dup / "
                    f"{c.get('voice_sync', 0)} voice-sync flags"
                )
        store.set_stage(
            job, "generate", StageStatus.DONE,
            f"{len(model['slides'])} slides via "
            + (detect_capabilities().provider.title() if used_llm else "built-in template")
            + doc_note
            + style_note
            + research_note
            + review_note,
        )
    except Exception as e:
        store.set_stage(job, "generate", StageStatus.ERROR, str(e))
        raise


def _slide_narrations(job: Job) -> list[str]:
    """Per-slide narration list, honoring user edits to the joined narration.

    If the user edited the combined narration text and the paragraph count
    still matches the slide count, use those paragraphs; otherwise fall back to
    each slide's own narration from the model.
    """
    slides = job.content.get("slides") or []
    model_narr = []
    for s in slides:
        if isinstance(s, dict):
            model_narr.append(str(s.get("narration") or ""))
        elif isinstance(s, str):
            model_narr.append(s)
        else:
            model_narr.append("")
    edited = (job.content.get("narration") or "").strip()
    if edited:
        import re
        paras = [p.strip() for p in re.split(r"\n\s*\n", edited) if p.strip()]
        if len(paras) == len(model_narr) and model_narr:
            return paras
    return model_narr


def _slide_audios(job: Job, work: Path, n_slides: int) -> list[Path | None]:
    """Resolve per-slide audio paths, preferring narrate's ``audio_files`` list."""
    audio_dir = work / "audio"
    rels = job.content.get("audio_files") or []
    audios: list[Path | None] = []
    for i in range(n_slides):
        path: Path | None = None
        if i < len(rels):
            candidate = work / str(rels[i])
            if candidate.is_file():
                path = candidate
        if path is None and audio_dir.is_dir():
            matches = sorted(audio_dir.glob(f"slide_{i:03d}.*"))
            path = matches[0] if matches else None
        audios.append(path)
    return audios


def _clear_slide_audio(audio_dir: Path, slide_index: int) -> None:
    """Remove stale clips for a slide before writing a new one."""
    for old in audio_dir.glob(f"slide_{slide_index:03d}.*"):
        try:
            old.unlink()
        except OSError:
            pass


def stage_narrate(job: Job) -> None:
    caps = detect_capabilities()
    work = _work(job)

    # Ensure we have a slide model (generate produces it).
    if not job.content.get("slides"):
        store.set_stage(job, "narrate", StageStatus.SKIPPED, "No slides to narrate")
        return

    narrations = _slide_narrations(job)
    if not job.content.get("narration"):
        store.set_content(job, "narration", "\n\n".join(narrations).strip())

    if not caps.tts:
        store.set_stage(
            job, "narrate", StageStatus.SKIPPED,
            "Narration unavailable — pip install kokoro-onnx",
        )
        return

    store.set_stage(job, "narrate", StageStatus.RUNNING)
    voice_prog = {"line": f"Recording voiceover for {len(narrations)} slides"}
    stop_pulse = _pulse(job, "narrate", voice_prog)

    def _voiced(done: int, total: int) -> None:
        voice_prog["line"] = f"Voiced {done} of {total} slides"
        store.note(job, "narrate", voice_prog["line"])

    try:
        audio_dir = work / "audio"
        audio_dir.mkdir(parents=True, exist_ok=True)

        total_words = sum(len((n or "").split()) for n in narrations)
        # User voice recordings (from the in-UI recorder) take precedence over
        # TTS for the slides they cover. Map slide index -> recorded file path.
        recorded = job.options.get("recorded_audio") or job.content.get("recorded_audio") or {}
        recorded_paths: dict[int, Path] = {}
        for k, rel in recorded.items():
            try:
                idx = int(k)
            except (TypeError, ValueError):
                continue
            p = work / rel
            if p.exists():
                recorded_paths[idx] = p
        # A single whole-narration recording (index -1) covers slide 0.
        if -1 in recorded_paths and 0 not in recorded_paths:
            recorded_paths[0] = recorded_paths[-1]

        from .pipeline import tts as tts_mod

        try:
            muse_voice = tts_mod.voice_from_options(job.options)
        except ValueError as e:
            raise RuntimeError(str(e)) from e
        log.bind(task="narrate").info(
            f"{len(narrations)} slides, ~{total_words} words via studio voice ({muse_voice})"
            + (f" ({len(recorded_paths)} recorded clips)" if recorded_paths else "")
        )

        target = int(job.options.get("target_duration") or 0)
        if target:
            from .pipeline import content as content_mod

            _, words_per_slide, _, _ = content_mod._planning(job.options)
            per_slide_max = max(18, int(round(words_per_slide * 1.1)))
            narrations = [
                n if i in recorded_paths else content_mod._trim_narration(n, per_slide_max)
                for i, n in enumerate(narrations)
            ]

        if recorded_paths:
            # Mixed path: copy recorded clips into place, synthesize the rest.
            import shutil as _shutil

            paths: list[Path] = []
            engine = caps.tts_engine
            has_recorded = False
            has_tts = False
            todo: list[tuple[str, Path]] = []
            slots: dict[int, Path] = {}
            for i, text in enumerate(narrations):
                if i in recorded_paths:
                    src = recorded_paths[i]
                    dst = audio_dir / f"slide_{i:03d}{src.suffix.lower()}"
                    _clear_slide_audio(audio_dir, i)
                    _shutil.copyfile(src, dst)
                    slots[i] = dst
                    has_recorded = True
                else:
                    out = audio_dir / f"slide_{i:03d}{media.tts.output_suffix()}"
                    _clear_slide_audio(audio_dir, i)
                    todo.append((text or "...", out))
                    slots[i] = out
                    has_tts = True
            if todo:
                media.synthesize_many(
                    todo,
                    voice=muse_voice,
                    workers=get_settings().effective_llm_parallel(),
                    on_done=_voiced,
                )
            for i in range(len(narrations)):
                p_ = slots[i]
                paths.append(p_ if p_.exists() else p_.with_suffix(".wav"))
            if has_recorded and has_tts:
                engine = "mixed"
            elif has_recorded:
                engine = "recorded"
        else:
            for i in range(len(narrations)):
                _clear_slide_audio(audio_dir, i)
            paths, engine = media.synthesize_slide_audio(
                narrations,
                audio_dir,
                voice=muse_voice,
                on_done=_voiced,
            )
        store.set_content(
            job, "audio_files", [str(p.relative_to(work)) for p in paths]
        )
        # Enforce the requested duration at the audio layer: TTS pace varies, so
        # if the summed narration overshoots the target we uniformly speed the
        # clips up (pitch-preserving, capped) so the final video tracks the
        # requested length instead of ballooning (e.g. 1min -> 2min).
        target = int(job.options.get("target_duration") or 0)
        if target and engine != "recorded":
            from .pipeline.sync import SLIDE_OVERHEAD_SEC

            recorded_idxs = set(recorded_paths.keys())
            tts_paths = [
                p for i, p in enumerate(paths)
                if i not in recorded_idxs and p is not None and p.exists()
            ]
            if tts_paths:
                recorded_secs = sum(
                    media._ffprobe_duration(paths[i])
                    for i in recorded_idxs
                    if i < len(paths) and paths[i] is not None and paths[i].exists()
                )
                overhead = SLIDE_OVERHEAD_SEC * len(paths)
                tts_target = max(1.0, float(target) - recorded_secs - overhead)
                factor = media.fit_audio_to_target(tts_paths, tts_target)
                if factor > 1.01:
                    log.bind(task="narrate").info(
                        f"duration fit: sped TTS {factor:.2f}x to hit {target}s target"
                    )

        # A short tail only. A long silence pad stretches the highlight walk
        # past the last spoken word.
        padded = 0
        for i, p in enumerate(paths):
            if p is None or not p.exists() or i in recorded_paths:
                continue
            before = media._ffprobe_duration(p)
            after = media.pad_audio_to_duration(p, before + 0.22)
            if after > before + 0.05:
                padded += 1
        if padded:
            log.bind(task="narrate").info(
                f"padded {padded} clip(s) to cover visual entrance/highlights"
            )

        # Expose the first clip as a quick-listen artifact.
        if paths:
            rel = paths[0].relative_to(work).as_posix()
            store.set_artifact(job, "audio", f"/files/{job.id}/{rel}")
        store.set_stage(
            job, "narrate", StageStatus.DONE,
            f"{len(paths)} slide clips ({engine})",
        )
        log.bind(task="narrate").success(f"{len(paths)} clips via {engine}")
    except Exception as e:
        log.bind(task="narrate").warning(f"TTS failed: {e}")
        store.set_stage(job, "narrate", StageStatus.SKIPPED, f"TTS failed: {e}")
    finally:
        stop_pulse.set()


def stage_capture(job: Job) -> None:
    caps = detect_capabilities()
    work = _work(job)
    html_path = work / "presentation.html"
    slides = job.content.get("slides") or []

    if not (caps.playwright and caps.ffmpeg):
        missing = []
        if not caps.playwright:
            missing.append("Playwright browser")
        if not caps.ffmpeg:
            missing.append("FFmpeg")
        store.set_stage(job, "capture", StageStatus.SKIPPED, "Missing: " + ", ".join(missing))
        return
    if not html_path.exists() or not slides:
        store.set_stage(job, "capture", StageStatus.SKIPPED, "No slides to record")
        return

    store.set_stage(job, "capture", StageStatus.RUNNING)
    capture_prog = {"line": f"Filming {len(slides)} slides"}
    stop_pulse = _pulse(job, "capture", capture_prog)
    try:
        settings = get_settings()
        spec = get_video_spec(job.options.get("video_format"))
        out_w, out_h = resolve_output_dimensions(spec, settings.video_quality)
        # Layout is authored at the format's logical size; capture at the device
        # pixel ratio needed to reach (or exceed) the target output resolution
        # so the upscale to 2K/4K stays crisp. Cap at 3x to bound memory/time.
        base_long = max(int(spec["width"]), int(spec["height"]))
        out_long = max(out_w, out_h)
        # Floor at 2x so 1080p text is captured sharp and scaled down, not drawn
        # at 1 device pixel per CSS pixel (that is what made the cards look soft).
        scale = max(2.0, min(3.0, round(out_long / base_long, 3)))

        fps = settings.capture_fps
        # Animated (seek-frame) capture. Two sub-modes:
        #   * sync_highlight ON  -> capture the WHOLE slide at motion_fps so the
        #     per-item highlight walks in time with the narration. Frame count
        #     scales with duration but at a low fps (e.g. 12), so a 6s slide is
        #     only ~72 small screenshots — still cheap and parallelised.
        #   * sync_highlight OFF -> capture only the short entrance window, then
        #     hold one settled frame (fastest; no highlight walk).
        # Falls back to still capture if audio is missing or the mode is "still".
        audio_dir = work / "audio"
        per_slide_audio = _slide_audios(job, work, len(slides))
        have_audio = any(a is not None for a in per_slide_audio)
        animated = (settings.animation_mode or "animated").lower() == "animated" and have_audio

        if animated:
            sync = bool(getattr(settings, "sync_highlight", True))
            motion_fps = int(getattr(settings, "motion_fps", 12)) if sync else fps
            motion_fps = max(6, min(motion_fps, fps))
            motion_secs = float(getattr(settings, "motion_seconds", 1.6))
            entrance_frames = max(1, int(round(motion_secs * motion_fps)))

            from .pipeline import sync as sync_mod

            def _focus_count(sl: dict) -> int:
                # Mirror JS __focus items via shared helper (cover/hook = 0).
                return len(sync_mod.slide_focus_texts(sl))

            motion_frames_per_slide: list[int] = []
            capture_indices_per_slide: list[list[int]] = []
            per_slide_full: list[bool] = []
            max_capture = int(getattr(settings, "max_motion_frames", 96))
            for a, sl in zip(per_slide_audio, slides):
                secs = media._ffprobe_duration(a) if a is not None else 3.0
                texts = sync_mod.slide_focus_texts(sl)
                focus = len(texts)
                walk = sync and focus >= 2
                per_slide_full.append(walk)
                # Audio duration owns the seek timeline (HTML visuals scrub to it).
                if walk:
                    seek_total = max(
                        entrance_frames, int(round((secs + 0.3) * motion_fps))
                    )
                else:
                    seek_total = entrance_frames
                if walk:
                    weights = sync_mod.focus_weights_for_slide(sl)
                    _, indices = media.compute_sparse_capture_frames(
                        seek_total,
                        entrance_frames,
                        focus,
                        motion_fps,
                        max_capture,
                        focus_weights=weights,
                    )
                else:
                    # Entrance-only: capture every frame (small count) and hold
                    # settled for the rest of the narration — never time-stretch.
                    indices = list(range(seek_total))
                motion_frames_per_slide.append(seek_total)
                capture_indices_per_slide.append(indices)
            # A slide is full-capture if ANY needs the walk; the worker/segment
            # builder use a single flag, so we capture full only where needed by
            # padding non-walk slides to their (short) entrance window. Since the
            # frame counts already differ per slide, a global full_slide flag is
            # safe: non-walk slides simply have few frames + a settled hold.
            any_full = any(per_slide_full)
            slide_dirs = media.capture_slides_animated(
                html_path, work / "shots", motion_frames_per_slide, motion_fps,
                width=spec["width"], height=spec["height"], scale=scale,
                full_slide=any_full, entrance_seconds=motion_secs,
                capture_indices_per_slide=capture_indices_per_slide,
            )
            store.set_content(
                job, "frame_dirs", [str(p.relative_to(work)) for p in slide_dirs]
            )
            # First frame of each slide as a preview thumbnail.
            first_frames = [
                (sorted(d.glob("frame_*.png")) or [None])[0] for d in slide_dirs
            ]
            store.set_artifact(
                job, "pages_shots",
                [
                    f"/files/{job.id}/{f.relative_to(work).as_posix()}"
                    for f in first_frames if f is not None
                ],
            )
            total_frames = sum(len(ix) for ix in capture_indices_per_slide)
            seek_frames = sum(motion_frames_per_slide)
            store.set_content(job, "motion_fps", motion_fps)
            store.set_content(job, "full_slide_capture", any_full)
            store.set_content(job, "per_slide_full", per_slide_full)
            detail = (
                f"Animated {len(slide_dirs)} slides, {total_frames} frames @ {motion_fps}fps "
                f"{out_w}x{out_h} ({spec['aspect_ratio']}, {settings.video_quality}, {scale}x DPR)"
            )
            if total_frames < seek_frames:
                detail += f" (sparse keyframes; {seek_frames} timeline frames)"
            store.set_stage(job, "capture", StageStatus.DONE, detail)
        else:
            images = media.capture_slides(
                html_path, work / "shots", len(slides),
                width=spec["width"], height=spec["height"], scale=scale,
            )
            store.set_content(job, "shot_files", [str(p.relative_to(work)) for p in images])
            store.set_artifact(
                job, "pages_shots",
                [f"/files/{job.id}/{p.relative_to(work).as_posix()}" for p in images],
            )
            store.set_stage(
                job, "capture", StageStatus.DONE,
                f"Captured {len(images)} slides @ {out_w}x{out_h} "
                f"({spec['aspect_ratio']}, {settings.video_quality}, {scale}x DPR)",
            )
    except Exception as e:
        store.set_stage(job, "capture", StageStatus.ERROR, str(e))
        raise
    finally:
        stop_pulse.set()


def stage_merge(job: Job) -> None:
    caps = detect_capabilities()
    work = _work(job)
    settings = get_settings()

    shots_dir = work / "shots"
    # Animated capture writes per-slide frame folders; still capture writes flat
    # slide_*.png. Detect which is present.
    frame_dirs = sorted(d for d in shots_dir.glob("slide_*") if d.is_dir())
    shots = sorted(shots_dir.glob("slide_*.png"))
    if not caps.ffmpeg or (not frame_dirs and not shots):
        store.set_stage(job, "merge", StageStatus.SKIPPED, "No captured slides to assemble")
        return

    n_slides = len(frame_dirs) if frame_dirs else len(shots)

    # Match each slide to its audio clip (if any).
    audios = _slide_audios(job, work, n_slides)

    store.set_stage(job, "merge", StageStatus.RUNNING)
    try:
        spec = get_video_spec(job.options.get("video_format"))
        out_w, out_h = resolve_output_dimensions(spec, settings.video_quality)

        def _merge_progress(done: int, total: int, merging: bool = False) -> None:
            if merging:
                store.set_stage(
                    job, "merge", StageStatus.RUNNING,
                    f"Merging {total} segments into final video\u2026",
                )
            else:
                store.set_stage(
                    job, "merge", StageStatus.RUNNING,
                    f"Rendering segments {done}/{total}\u2026",
                )

        if frame_dirs:
            motion_fps = int(job.content.get("motion_fps") or settings.capture_fps)
            full_slide = bool(job.content.get("full_slide_capture"))
            per_slide_full = job.content.get("per_slide_full") or []
            final = media.build_video_from_frame_sequences(
                frame_dirs, audios, work, settings.capture_fps,
                width=out_w, height=out_h,
                motion_fps=motion_fps, full_slide=full_slide,
                per_slide_full=per_slide_full if isinstance(per_slide_full, list) else None,
                on_progress=_merge_progress,
            )
        else:
            final = media.build_video_from_slides(
                shots, audios, work, settings.capture_fps,
                width=out_w, height=out_h,
                on_progress=_merge_progress,
            )
        store.set_artifact(job, "video_final", f"/files/{job.id}/{final.name}")
        try:
            from . import blob_store

            blob_store.upload_one_now(job.id, final.name, final)
        except Exception as e:
            log.bind(task="merge").warning(f"final video storage upload failed: {e}")
        have_audio = any(a is not None for a in audios)
        # Report actual vs requested duration so over/under-runs are visible.
        actual = media._ffprobe_duration(final)
        target = int(job.options.get("target_duration") or 0)
        dur_txt = f"{int(actual // 60)}m {int(actual % 60)}s"
        detail = (
            f"Assembled {n_slides} synced {spec['aspect_ratio']} segments \u2022 {dur_txt}"
            if have_audio
            else f"Assembled {n_slides} {spec['aspect_ratio']} segments (no audio) \u2022 {dur_txt}"
        )
        if target and actual < target * 0.6:
            detail += (
                f" \u26a0\ufe0f shorter than the requested {target // 60}m {target % 60}s"
                " because the narration script was brief"
            )
            log.bind(task="merge").warning(
                f"final {actual:.0f}s << target {target}s"
            )
        store.set_stage(job, "merge", StageStatus.DONE, detail)
        log.bind(task="merge").success(f"final.mp4 {dur_txt} ({actual:.1f}s)")
    except Exception as e:
        store.set_stage(job, "merge", StageStatus.ERROR, str(e))
        raise


def stage_publish_meta(job: Job) -> None:
    """Fill in publish title / description / tags + matching social posts.

    Metadata is format-aware (Shorts vs long YouTube vs LinkedIn vs Reels).
    Thumbnails are NOT auto-generated — the user clicks Generate in the Publish
    UI (``POST /api/jobs/{id}/generate-thumbnail``). This stage is best-effort
    so failures never block the rest of the pipeline.
    """
    store.set_stage(job, "publish_meta", StageStatus.RUNNING)
    try:
        spec = get_video_spec(job.options.get("video_format"))
        lesson_title = job.content.get("slide_title") or "Automated Lesson"
        script = job.content.get("narration") or ""
        fmt_key = job.options.get("video_format")

        # Don't clobber user edits: only (re)generate when not already present.
        if not job.content.get("publish_title"):
            meta, meta_msg = meta_gen.generate_metadata(
                lesson_title, script, video_format=fmt_key
            )
            tags = meta.get("tags") or spec.get("tags")
            store.set_content(job, "publish_title", meta["title"])
            store.set_content(job, "publish_description", meta["description"])
            store.set_content(job, "publish_tags", tags)
        else:
            meta_msg = "Kept existing title/description."

        # Social / blog tabs (IG, X, LinkedIn, TikTok, Substack, Medium) stay
        # empty until the user clicks Generate on that tab — they reuse this
        # job's narration + any already-saved social_metadata as context.

        store.set_content(
            job, "publish_meta_message",
            f"{meta_msg} Social tabs: generate per platform when ready. Thumbnail: click Generate when ready.".strip(),
        )
        detail = f"Metadata ready ({spec['label']}; thumbnail on demand)"
        store.set_stage(job, "publish_meta", StageStatus.DONE, detail)
        log.bind(task="publish-meta").success(detail)
        # Auto-post to platforms that have credentials + auto_post enabled.
        try:
            from .pipeline import social_post as social_post_mod
            auto_results = social_post_mod.auto_post_job(job)
            if auto_results:
                store.set_content(job, "social_post_results", auto_results)
                ok_n = sum(1 for r in auto_results if r.get("ok"))
                log.bind(task="social-post").info(
                    f"auto_post finished {ok_n}/{len(auto_results)} platform(s)"
                )
        except Exception as e:  # noqa: BLE001
            log.bind(task="social-post").warning(f"auto_post skipped: {e}")
    except Exception as e:
        # Even an unexpected error here must not block upload — mark skipped.
        log.bind(task="publish-meta").warning(f"publish_meta soft-failed: {e}")
        store.set_stage(job, "publish_meta", StageStatus.SKIPPED, f"Skipped: {e}")


def generate_job_thumbnail(job: Job) -> tuple[bool, str]:
    """On-demand thumbnail for a job. Returns ``(ok, message)``."""
    with costs.job_context(job.id):
        return _generate_job_thumbnail_inner(job)


def _generate_job_thumbnail_inner(job: Job) -> tuple[bool, str]:
    work = _work(job)
    lesson_title = (
        job.content.get("publish_title")
        or job.content.get("slide_title")
        or "Automated Lesson"
    )
    script = job.content.get("narration") or ""
    summary = (script or "").strip().split("\n\n")[0][:200]
    out = work / "thumbnail.png"
    # On-demand click always runs even if GENERATE_THUMBNAIL=false (that flag
    # only meant "don't auto-run in the pipeline").
    path, thumb_msg = thumb_gen.generate_thumbnail(
        lesson_title,
        summary,
        out,
        backend_override=get_settings().thumbnail_backend or "auto",
    )
    if path is None:
        path, fb_msg = thumb_gen.fallback_slide_thumbnail(
            work, job.id, job.artifacts or {}, job.content or {}, out
        )
        if path is not None:
            if get_settings().thumbnail_text_overlay:
                thumb_gen.overlay_title(path, lesson_title)
            thumb_msg = fb_msg
    if path is not None and path.exists():
        store.set_artifact(job, "thumbnail", f"/files/{job.id}/{path.name}")
        store.set_content(job, "thumbnail", path.name)
        store.set_content(job, "publish_meta_message", f"Thumbnail ready. {thumb_msg}".strip())
        try:
            from . import blob_store

            blob_store.upload_one_now(job.id, path.name, path)
        except Exception as e:
            log.bind(task="publish-meta").warning(f"thumbnail storage upload failed: {e}")
        log.bind(task="publish-meta").success(f"thumbnail on demand: {path.name}")
        return True, thumb_msg or "Thumbnail generated."
    return False, thumb_msg or "Thumbnail generation failed."


def stage_publish(job: Job) -> None:
    caps = detect_capabilities()
    work = _work(job)
    final = work / "final.mp4"
    if not final.exists():
        final = work / "raw.mp4"

    want = bool(job.options.get("publish")) and caps.youtube
    if not want:
        reason = "Disabled" if not job.options.get("publish") else "YouTube not configured"
        store.set_stage(job, "publish", StageStatus.SKIPPED, reason)
        return
    if not final.exists():
        store.set_stage(job, "publish", StageStatus.SKIPPED, "No video to upload")
        return

    store.set_stage(job, "publish", StageStatus.RUNNING)
    try:
        spec = get_video_spec(job.options.get("video_format"))
        # Prefer the reviewed/edited publish metadata; fall back to the lesson.
        lesson_title = (
            job.content.get("publish_title")
            or job.content.get("slide_title")
            or "Automated Lesson"
        )
        description = job.content.get("publish_description") or job.content.get("narration", "")
        tags = job.content.get("publish_tags") or spec.get("tags")
        # Shorts need the #Shorts cue in title/description to be classified.
        if spec["key"] == "youtube_shorts":
            lesson_title = f"{lesson_title} #Shorts"
            description = (description + "\n\n#Shorts").strip()
        thumb_name = job.content.get("thumbnail")
        thumb_path = (work / thumb_name) if thumb_name else None
        result = publish.upload_to_youtube(
            final,
            title=lesson_title,
            description=description,
            tags=tags,
            thumbnail=thumb_path if thumb_path and thumb_path.exists() else None,
        )
        store.set_artifact(job, "youtube", result)
        store.set_stage(job, "publish", StageStatus.DONE, f"Uploaded: {result['url']}")
    except Exception as e:
        store.set_stage(job, "publish", StageStatus.ERROR, str(e))


STAGE_FUNCS = {
    "extract": stage_extract,
    "generate": stage_generate,
    "narrate": stage_narrate,
    "capture": stage_capture,
    "merge": stage_merge,
    "publish_meta": stage_publish_meta,
    "publish": stage_publish,
}

# When re-running a stage, these later stages become stale and are reset.
DOWNSTREAM = {
    "extract": ["generate", "narrate", "capture", "merge", "publish_meta", "publish"],
    "generate": ["narrate", "capture", "merge", "publish_meta", "publish"],
    "narrate": ["capture", "merge", "publish_meta", "publish"],
    "capture": ["merge", "publish"],
    "merge": ["publish"],
    "publish_meta": ["publish"],
    "publish": [],
}


# ---------------------------------------------------------------- runners ----

def _raise_if_stage_errors(job: Job) -> None:
    """Abort the run when any stage recorded an error (don't mark job done)."""
    failed = [s.key for s in job.stages if s.status == StageStatus.ERROR]
    if failed:
        raise RuntimeError(f"Stage failed: {failed[0]}")


def run_pipeline(job: Job, *, finalize: bool = True) -> None:
    """Run all stages in order.

    ``finalize=False`` skips workspace cleanup/rename so callers (e.g. automation
    packaging) can copy pages/audio before they are deleted.
    """
    if not store.try_acquire(job):
        log.bind(task="pipeline").warning(f"skipped pipeline for {job.id}: already busy")
        return
    with costs.job_context(job.id):
        try:
            for key, _ in [(s.key, s.label) for s in job.stages]:
                try:
                    STAGE_FUNCS[key](job)
                finally:
                    _keep_files(job)
            _raise_if_stage_errors(job)
            store.set_result(job, "done")
            if finalize:
                try:
                    from .workspace_store import finalize_job_workspace

                    finalize_job_workspace(job)
                except Exception as e:  # noqa: BLE001
                    log.bind(task="pipeline").warning(f"workspace finalize soft-fail: {e}")
        except Exception as e:
            store.set_result(job, "error", str(e))
        finally:
            store.release(job)


def run_single_stage(job: Job, key: str) -> None:
    """Re-run one stage (after a content edit), resetting downstream stages."""
    if key not in STAGE_FUNCS:
        return
    if not store.try_acquire(job):
        log.bind(task="pipeline").warning(f"skipped stage {key} for {job.id}: already busy")
        return
    store.reset_stages(job, DOWNSTREAM.get(key, []))
    store.set_result(job, "running")
    with costs.job_context(job.id):
        try:
            try:
                STAGE_FUNCS[key](job)
            finally:
                _keep_files(job)
            _raise_if_stage_errors(job)
            store.set_result(job, "done")
            if key in {"merge", "publish_meta", "publish", "capture"}:
                try:
                    from .workspace_store import finalize_job_workspace

                    finalize_job_workspace(job)
                except Exception as e:  # noqa: BLE001
                    log.bind(task="pipeline").warning(f"workspace finalize soft-fail: {e}")
        except Exception as e:
            store.set_result(job, "error", str(e))
        finally:
            store.release(job)


def run_from_stage(job: Job, key: str) -> None:
    """Run a stage and all subsequent stages (useful after editing content)."""
    keys = [s.key for s in job.stages]
    if key not in keys:
        return
    if not store.try_acquire(job):
        log.bind(task="pipeline").warning(f"skipped run-from {key} for {job.id}: already busy")
        return
    start = keys.index(key)
    store.reset_stages(job, keys[start:])
    store.set_result(job, "running")
    with costs.job_context(job.id):
        try:
            for k in keys[start:]:
                try:
                    STAGE_FUNCS[k](job)
                finally:
                    _keep_files(job)
            _raise_if_stage_errors(job)
            store.set_result(job, "done")
            try:
                from .workspace_store import finalize_job_workspace

                finalize_job_workspace(job)
            except Exception as e:  # noqa: BLE001
                log.bind(task="pipeline").warning(f"workspace finalize soft-fail: {e}")
        except Exception as e:
            store.set_result(job, "error", str(e))
        finally:
            store.release(job)
