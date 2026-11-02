"""Plan large uploads into topics and spawn one or many Studio videos."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .jobs import Job, store
from .logging_setup import log
from .orchestrator import run_from_stage
from .pipeline import document_topics as dtopics
from .pipeline import extract
from .video_options import normalize_video_options
from .workspace_store import resolve_job_dir

_LOG = log.bind(task="batch-jobs")


def _extract_text_for_plan(src: Path, work: Path) -> tuple[str, str]:
    """Prefer plain text for long books; VLM page caps miss most of a 400-page PDF."""
    try:
        text = extract.extract_text_any(src)
        method = "plain text"
    except Exception as e:  # noqa: BLE001
        _LOG.warning(f"plain extract failed ({e}); trying VLM")
        text, _imgs = extract.extract_with_vlm(src, work)
        method = "VLM"
    return (text or "").strip(), method


def create_plan_job(
    *,
    filename: str,
    data: bytes,
    user_id: str,
    options: dict | None = None,
) -> dict[str, Any]:
    """Upload → extract → classify topics. Does not run the full video pipeline."""
    suffix = Path(filename or "doc.pdf").suffix.lower() or ".bin"
    opts = dict(options or {})
    opts["plan_only"] = True
    opts["lock_visual_preset"] = True
    job = store.create(filename, options=opts, user_id=user_id)
    work = resolve_job_dir(job.id, create=True)
    dest = work / f"input{suffix}"
    dest.write_bytes(data)
    from .jobs import StageStatus

    store.set_stage(job, "extract", StageStatus.RUNNING)
    try:
        text, method = _extract_text_for_plan(dest, work)
        if not text:
            raise ValueError("No text could be extracted from the upload")
        store.set_content(job, "extracted_text", text)
        store.set_content(job, "extracted_word_count", len(text.split()))
        store.set_stage(
            job,
            "extract",
            StageStatus.DONE,
            f"{method} · {len(text):,} chars (plan)",
        )
    except Exception as e:
        store.set_stage(job, "extract", StageStatus.ERROR, str(e))
        store.set_result(job, "error", str(e))
        raise

    breakdown = dtopics.classify_document_topics(text, filename=filename)
    store.set_content(job, "document_topics", breakdown)
    store.set_content(job, "slide_title", breakdown.get("title") or Path(filename).stem)
    store.set_content(job, "doc_type", breakdown.get("doc_type") or "")
    store.set_result(job, "planned")
    return {
        "ok": True,
        "plan_id": job.id,
        "job_id": job.id,
        "filename": filename,
        "words": breakdown.get("words") or len(text.split()),
        "chars": breakdown.get("chars") or len(text),
        "should_plan": dtopics.should_plan_topics(text),
        "topics": breakdown,
    }


def get_plan(job_id: str) -> dict[str, Any] | None:
    job = store.get(job_id)
    if not job:
        return None
    topics = (job.content or {}).get("document_topics")
    if not topics:
        return None
    return {
        "plan_id": job.id,
        "job_id": job.id,
        "filename": job.filename,
        "status": job.status,
        "topics": topics,
        "options": {
            k: job.options.get(k)
            for k in (
                "video_format",
                "video_theme",
                "video_style",
                "target_duration",
                "enable_web_research",
                "content_layout",
                "age_group",
                "knowledge_level",
                "custom_prompt",
            )
            if k in (job.options or {})
        },
    }


def reclassify_plan(job_id: str, *, max_topics: int = 80) -> dict[str, Any]:
    job = store.get(job_id)
    if not job:
        raise FileNotFoundError("Plan job not found")
    text = (job.content or {}).get("extracted_text") or ""
    if len(text) < 200:
        raise ValueError("No extracted text on this plan — re-upload the document")
    breakdown = dtopics.classify_document_topics(
        text, filename=job.filename or "", max_topics=max_topics
    )
    store.set_content(job, "document_topics", breakdown)
    return {"ok": True, "plan_id": job.id, "topics": breakdown}


def _selected_topics(
    breakdown: dict, selected_ids: list[str], *, allow_fallback: bool
) -> list[dict]:
    by_id = {t.get("id"): t for t in (breakdown.get("topics") or []) if t.get("id")}
    out = []
    for sid in selected_ids:
        if sid in by_id:
            out.append(by_id[sid])
    if out or not allow_fallback:
        return out
    for tid in breakdown.get("recommended_ids") or []:
        if tid in by_id:
            out.append(by_id[tid])
    if not out:
        out = list(breakdown.get("topics") or [])[:12]
    return out


def _copy_input(parent: Job, child: Job) -> Path:
    pwork = resolve_job_dir(parent.id, create=False)
    cwork = resolve_job_dir(child.id, create=True)
    src = None
    for p in pwork.iterdir():
        if p.name.startswith("input") and p.is_file():
            src = p
            break
    if src is None:
        raise FileNotFoundError("Parent plan has no input file")
    dest = cwork / src.name
    shutil.copyfile(src, dest)
    return dest


def create_jobs_from_plan(
    plan_id: str,
    *,
    user_id: str,
    selected_ids: list[str] | None = None,
    mode: str = "per_topic",  # per_topic | single
    video_opts: dict | None = None,
    enable_web_research: bool = True,
    deep_grounding: bool = True,
    content_layout: str = "auto",
    extra_topics: str = "",
    age_group: str = "auto",
    knowledge_level: str = "auto",
    custom_prompt: str = "",
    review_notes: str = "",
) -> dict[str, Any]:
    """Spawn one combined video or N topic videos from a plan job."""
    parent = store.get(plan_id)
    if not parent:
        raise FileNotFoundError("Plan not found")
    breakdown = (parent.content or {}).get("document_topics") or {}
    full_text = (parent.content or {}).get("extracted_text") or ""
    if not full_text:
        raise ValueError("Plan has no extracted text")
    explicit = selected_ids is not None
    chosen_ids = [str(s).strip() for s in (selected_ids or []) if str(s).strip()]
    if explicit and not chosen_ids:
        raise ValueError("Select at least one topic")
    topics = _selected_topics(breakdown, chosen_ids, allow_fallback=not explicit)
    if not topics:
        raise ValueError("Select at least one topic")

    raw_opts = dict(video_opts or {})
    base_opts = normalize_video_options(
        video_format=raw_opts.get("video_format"),
        target_duration=raw_opts.get("target_duration"),
        youtube_video_url=raw_opts.get("youtube_video_url", ""),
        video_theme=raw_opts.get("video_theme"),
        video_style=raw_opts.get("video_style"),
    )
    base_opts["enable_web_research"] = bool(enable_web_research)
    base_opts["use_topic_prep"] = bool(deep_grounding)
    base_opts["lock_visual_preset"] = True
    base_opts["content_layout"] = (content_layout or "auto").strip() or "auto"
    if extra_topics.strip():
        base_opts["extra_topics"] = extra_topics.strip()
    from .pipeline.audience import stamp_options

    base_opts = stamp_options(
        base_opts,
        age_group=age_group or parent.options.get("age_group") or "auto",
        knowledge_level=knowledge_level or parent.options.get("knowledge_level") or "auto",
        custom_prompt=custom_prompt if custom_prompt is not None else parent.options.get("custom_prompt") or "",
        review_notes=review_notes or parent.options.get("review_notes") or "",
    )
    # Inherit voice / publish from parent plan options when present
    for k in (
        "publish",
        "muse_voice",
        "slide_ai_images",
        "video_style_label",
        "video_theme_label",
    ):
        if k in raw_opts and raw_opts[k] is not None:
            base_opts[k] = raw_opts[k]
        elif k in (parent.options or {}) and k not in base_opts:
            base_opts[k] = parent.options[k]

    mode = (mode or "per_topic").strip().lower()
    if mode not in {"per_topic", "single"}:
        mode = "per_topic"

    child_ids: list[str] = []

    if mode == "single":
        # One video covering all selected topics (text concatenation + topic list).
        opts = dict(base_opts)
        opts["parent_job_id"] = plan_id
        opts["batch_mode"] = "single"
        names = [t.get("name") or "Topic" for t in topics]
        opts["extra_topics"] = ", ".join(
            filter(
                None,
                [opts.get("extra_topics") or "", *names[:16]],
            )
        )
        opts["section_topics"] = [{"id": t.get("id"), "name": t.get("name")} for t in topics]
        title = breakdown.get("title") or parent.filename or "Lesson"
        fname = f"{str(title)[:60]} — selected topics.md"
        child = store.create(fname, options=opts, user_id=user_id)
        _copy_input(parent, child)
        body = "\n\n".join(dtopics.slice_topic_text(full_text, t) for t in topics)
        store.set_content(child, "extracted_text", body)
        store.set_content(child, "slide_title", title)
        store.set_content(child, "title", title)
        store.set_content(child, "document_topics", {"selected": topics, "mode": "single"})
        child_ids.append(child.id)
        store.set_content(parent, "child_job_ids", child_ids)
        parent.options["child_job_ids"] = child_ids
        store.set_result(parent, "planned")
        runner_submit(child)
        return {
            "ok": True,
            "mode": "single",
            "plan_id": plan_id,
            "job_ids": child_ids,
            "primary_job_id": child_ids[0],
            "topics": topics,
        }

    # One video per topic
    for t in topics:
        opts = dict(base_opts)
        opts["parent_job_id"] = plan_id
        opts["batch_mode"] = "per_topic"
        opts["section_id"] = t.get("id")
        opts["section_title"] = t.get("name") or "Topic"
        opts["extra_topics"] = ", ".join(
            filter(
                None,
                [
                    opts.get("extra_topics") or "",
                    t.get("name") or "",
                    *((t.get("focus") or [])[:3]),
                ],
            )
        )
        opts["automation_kind"] = "topic"
        opts["automation_title"] = (t.get("name") or "Topic")[:80]
        fname = f"{(t.get('name') or 'topic')[:70]}.md"
        child = store.create(fname, options=opts, user_id=user_id)
        _copy_input(parent, child)
        body = dtopics.slice_topic_text(full_text, t)
        store.set_content(child, "extracted_text", body)
        store.set_content(child, "slide_title", t.get("name") or "Topic")
        store.set_content(child, "title", t.get("name") or "Topic")
        store.set_content(child, "publish_title", t.get("name") or "Topic")
        child_ids.append(child.id)
        runner_submit(child)

    store.set_content(parent, "child_job_ids", child_ids)
    parent.options["child_job_ids"] = child_ids
    store.set_result(parent, "planned")
    return {
        "ok": True,
        "mode": "per_topic",
        "plan_id": plan_id,
        "job_ids": child_ids,
        "primary_job_id": child_ids[0] if child_ids else None,
        "topics": topics,
    }


def runner_submit(job: Job) -> None:
    """Start pipeline from generate when extract text is already seeded."""
    from . import runner
    from .jobs import StageStatus

    def _run() -> None:
        try:
            store.set_stage(job, "extract", StageStatus.DONE, "pre-seeded from topic plan")
            run_from_stage(job, "generate")
        except Exception as e:  # noqa: BLE001
            _LOG.error(f"topic job {job.id} failed: {e}")
            store.set_result(job, "error", str(e))

    runner.submit(_run)