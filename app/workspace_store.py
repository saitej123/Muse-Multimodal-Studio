"""Named workspace folders for Studio jobs + post-run cleanup.

Job API id stays a short hex id (``/api/jobs/{id}``, ``/files/{id}/…``).
On disk the folder is renamed after content exists::

    workspace/
      refertrack-…_video_192262152b0b/
        final.mp4
        thumbnail.png
        cover.png          # retained cover for presentation.html
        presentation.html
        input.pdf          # or named source PDF
        meta.json
        audio/             # kept only until merge; removed after finalize
"""
from __future__ import annotations

import json
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .config import WORKSPACE_DIR
from .logging_setup import log

if TYPE_CHECKING:
    from .jobs import Job

_LOG = log.bind(task="workspace")

# Temp / intermediate artifacts removed once final.mp4 exists.
_TEMP_NAMES = {
    "shots",
    "raw.mp4",
    "convert",
    "pages_shots",
    "capture.log",
    "tmp",
    "temp",
}


def slugify(text: str, *, max_len: int = 55) -> str:
    base = re.sub(r"[^\w\s-]", "", (text or "").lower()).strip()
    base = re.sub(r"[\s_-]+", "-", base)[:max_len].strip("-")
    return base or "job"


def make_folder_slug(job: "Job") -> str:
    """``<title-or-file>[_kind]_<jobId>`` — unique, human-readable."""
    opts = job.options or {}
    content = job.content or {}
    title = (
        str(content.get("slide_title") or "").strip()
        or str(content.get("publish_title") or "").strip()
        or str(opts.get("automation_title") or "").strip()
    )
    fname = Path(str(job.filename or "")).stem
    if fname.lower() in {"paper", "input", "upload", ""}:
        fname = ""
    base = slugify(title or fname or "job")
    kind = str(opts.get("automation_kind") or "").strip().lower()
    fmt = str(opts.get("video_format") or "").strip().lower()
    if kind in {"video", "reel"}:
        base = f"{base}_{kind}"
    elif any(x in fmt for x in ("instagram", "tiktok", "short", "reel")):
        base = f"{base}_reel"
    elif fmt:
        # youtube_video → omit (default); others get a short tag
        if fmt not in {"youtube_video", ""}:
            tag = fmt.replace("youtube_", "").replace("_video", "").replace("_", "-")[:16]
            if tag:
                base = f"{base}_{tag}"
    return f"{base}_{job.id}"


def resolve_job_dir(job_id: str, *, create: bool = False) -> Path:
    """Resolve on-disk folder for a job id (named slug or legacy id folder)."""
    from .jobs import store

    root = WORKSPACE_DIR
    root.mkdir(parents=True, exist_ok=True)
    job = store.get(job_id)
    slug = ""
    if job:
        slug = str((job.options or {}).get("folder_slug") or "").strip()

    candidates: list[Path] = []
    if slug:
        candidates.append(root / slug)
    candidates.append(root / job_id)
    # Suffix match for renamed folders when options not yet loaded.
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir() and d.name.endswith(f"_{job_id}") and d not in candidates:
                candidates.append(d)

    for c in candidates:
        if c.is_dir():
            return c

    path = root / (slug or job_id)
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _rewrite_file_urls(job: "Job", old_folder: str, new_folder: str) -> None:
    """Artifact URLs use job.id, not folder name — no path rewrite needed.

    Kept for clarity: ``/files/{job.id}/…`` is resolved via ``resolve_job_dir``.
    """
    _ = (job, old_folder, new_folder)


def _retain_cover_for_html(work: Path) -> None:
    """Copy the cover page next to presentation.html before pages/ is deleted."""
    html = work / "presentation.html"
    pages = work / "pages"
    if not html.is_file() or not pages.is_dir():
        return
    cover_src: Path | None = None
    for p in sorted(pages.glob("page_000.*")):
        if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
            cover_src = p
            break
    if cover_src is None:
        for p in sorted(pages.iterdir()):
            if p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                cover_src = p
                break
    if cover_src is None:
        return
    dest = work / f"cover{cover_src.suffix.lower()}"
    try:
        shutil.copy2(cover_src, dest)
    except OSError:
        return
    try:
        text = html.read_text(encoding="utf-8")
        old_ref = f"pages/{cover_src.name}"
        if old_ref in text:
            html.write_text(text.replace(old_ref, dest.name), encoding="utf-8")
    except OSError:
        pass


def cleanup_job_temps(work: Path, job: "Job") -> list[str]:
    """Delete intermediate capture / preview files; keep finals only."""
    removed: list[str] = []
    has_final = (work / "final.mp4").is_file()
    if not has_final:
        return removed

    _retain_cover_for_html(work)

    for name in list(_TEMP_NAMES):
        p = work / name
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(name + "/")
        elif p.is_file():
            try:
                p.unlink()
                removed.append(name)
            except OSError:
                pass

    # Page source images & per-slide audio are baked into final.mp4 — drop them.
    for sub in ("pages", "audio"):
        p = work / sub
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(sub + "/")

    # Clear preview artifact pointers so UI doesn't 404.
    arts = job.artifacts or {}
    changed = False
    for key in ("pages", "pages_shots", "audio"):
        if key in arts:
            arts.pop(key, None)
            changed = True
    if changed:
        job.artifacts = arts

    # Drop empty social staging leftovers except final carousel if present.
    social = work / "social"
    if social.is_dir():
        # Keep ig_carousel if any images; otherwise remove empty tree.
        keep = False
        for f in social.rglob("*"):
            if f.is_file() and f.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}:
                keep = True
                break
        if not keep:
            shutil.rmtree(social, ignore_errors=True)
            removed.append("social/")

    return removed


def write_job_meta(work: Path, job: "Job") -> None:
    opts = job.options or {}
    content = job.content or {}
    meta = {
        "job_id": job.id,
        "folder_slug": opts.get("folder_slug") or work.name,
        "filename": job.filename,
        "title": content.get("slide_title") or content.get("publish_title") or "",
        "status": job.status,
        "video_format": opts.get("video_format"),
        "automation_kind": opts.get("automation_kind") or "",
        "automation_folder": opts.get("automation_folder") or "",
        "source_pdf": opts.get("source_pdf") or job.filename or "",
        "artifacts": {
            k: v for k, v in (job.artifacts or {}).items()
            if k in {"video_final", "thumbnail", "html", "youtube"}
        },
        "synced_at": time.time(),
    }
    (work / "meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def rename_source_pdf(work: Path, job: "Job") -> str | None:
    """Pick a display PDF name from title/filename (keeps ``input.*`` on disk)."""
    src = None
    for name in ("input.pdf", "input.png", "input.jpg", "input.jpeg", "input.webp", "input.md"):
        p = work / name
        if p.is_file():
            src = p
            break
    if src is None:
        return None
    preferred = str((job.options or {}).get("source_pdf") or job.filename or "").strip()
    if not preferred or preferred.lower() in {"paper.pdf", "input.pdf", "input.md"}:
        title = (job.content or {}).get("slide_title") or ""
        if title:
            preferred = slugify(title, max_len=70) + src.suffix.lower()
        else:
            return src.name
    preferred = Path(preferred).name
    if not preferred.lower().endswith(src.suffix.lower()):
        preferred = Path(preferred).stem + src.suffix.lower()
    return preferred


def finalize_job_workspace(job: "Job") -> dict[str, Any]:
    """Post-process: cleanup temps, name folder from content, write meta.

    Called when a job finishes successfully (``status=done``).
    """
    from .jobs import store

    work = resolve_job_dir(job.id, create=False)
    if not work.is_dir():
        work = WORKSPACE_DIR / job.id
    if not work.is_dir():
        return {"ok": False, "error": "no workspace"}

    removed = cleanup_job_temps(work, job)
    source_name = rename_source_pdf(work, job)
    if source_name:
        opts = dict(job.options or {})
        opts["source_pdf"] = source_name
        if not opts.get("automation_title") and (job.content or {}).get("slide_title"):
            opts["automation_title"] = str(job.content.get("slide_title"))[:200]
        job.options = opts
        if job.filename in {"paper.pdf", "input.pdf", ""} or not job.filename:
            job.filename = source_name

    new_slug = make_folder_slug(job)
    old_name = work.name
    dest = WORKSPACE_DIR / new_slug
    renamed = False
    if work.resolve() != dest.resolve():
        if dest.exists():
            # Collision — keep current if already ends with job id.
            if work.name.endswith(f"_{job.id}"):
                new_slug = work.name
            else:
                new_slug = f"{slugify(new_slug.rsplit('_', 1)[0], max_len=40)}_{job.id}"
                dest = WORKSPACE_DIR / new_slug
        if work.resolve() != dest.resolve() and not dest.exists():
            try:
                work.rename(dest)
                work = dest
                renamed = True
                _LOG.info(f"job {job.id}: folder {old_name} → {new_slug}")
            except OSError as e:
                _LOG.warning(f"job {job.id}: rename failed: {e}")
                new_slug = work.name

    opts = dict(job.options or {})
    opts["folder_slug"] = new_slug
    job.options = opts

    # Strip internal bookkeeping keys that must not leak into job content / API.
    content = dict(job.content or {})
    for key in list(content):
        if key.startswith("_workspace_"):
            content.pop(key, None)
    job.content = content

    write_job_meta(work, job)
    try:
        from . import blob_store

        blob_store.sync_workspace_async(job.id, work)
    except Exception:
        pass
    try:
        # Persist + notify SSE clients (do not invent content keys).
        store._publish(job)  # noqa: SLF001
    except Exception:
        try:
            store._persist(job)  # noqa: SLF001
        except Exception:
            pass

    return {
        "ok": True,
        "folder_slug": new_slug,
        "renamed": renamed,
        "removed": removed,
        "filename": job.filename,
    }


def migrate_all_done_jobs() -> list[dict]:
    """Finalize every completed job still on a bare id folder / with temps."""
    from .jobs import store

    store.hydrate()
    out: list[dict] = []
    with store._lock:  # noqa: SLF001
        jobs = list(store._jobs.values())  # noqa: SLF001
    for job in jobs:
        if job.status not in {"done", "completed"} and not (job.artifacts or {}).get("video_final"):
            # Still finalize naming if final exists
            work = resolve_job_dir(job.id, create=False)
            if not (work / "final.mp4").is_file():
                continue
        try:
            result = finalize_job_workspace(job)
            out.append({"job_id": job.id, **result})
        except Exception as e:  # noqa: BLE001
            out.append({"job_id": job.id, "ok": False, "error": str(e)})
    return out
