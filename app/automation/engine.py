"""Built-in paper -> video automation (in-process).

Runs inside the app process and reuses the same pipeline the UI uses
(``store`` + ``orchestrator.run_pipeline``). Triggered manually from the
admin dashboard or on a twice-daily off-hours schedule.
"""
from __future__ import annotations

import datetime as _dt
import json
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

from ..config import WORKSPACE_DIR, get_settings
from ..jobs import store
from ..logging_setup import log
from ..orchestrator import run_pipeline
from ..video_options import normalize_video_options
from . import compute as _compute
from . import sources as _sources

_LOG = log.bind(task="auto")
_LOG_TAIL = 200
_HISTORY_MAX = 200


# --------------------------------------------------------------- config bridge --

class _CfgAdapter:
    """Expose the attribute names ``sources``/``compute`` expect, from Settings."""

    def __init__(self) -> None:
        s = get_settings()
        # sources.*
        self.source = s.auto_source
        self.arxiv_categories = [c.strip() for c in s.auto_arxiv_categories.split(",") if c.strip()]
        self.arxiv_keywords = getattr(s, "auto_arxiv_keywords", "") or ""
        self.ss_query = s.auto_ss_query
        self.ss_api_key = s.auto_ss_api_key
        self.max_papers = s.auto_max_papers
        # compute.*
        self.compute_gate = s.auto_compute_gate
        self.max_load = s.auto_max_load
        self.min_gpu_free_mb = s.auto_min_gpu_free_mb
        self.compute_wait_seconds = s.auto_compute_wait_seconds
        self.poll_seconds = 5.0
        # engine
        self.require_code = s.auto_require_code
        self.make_video = s.auto_make_video
        self.video_format = s.auto_video_format
        self.video_seconds = s.auto_video_seconds
        self.make_reel = s.auto_make_reel
        self.reel_format = s.auto_reel_format
        self.reel_seconds = s.auto_reel_seconds
        self.video_theme = s.auto_video_theme
        self.video_style = getattr(s, "auto_video_style", None) or "auto"
        self.muse_voice = (getattr(s, "auto_muse_voice", None) or "Kore").strip() or "Kore"
        self.publish = s.auto_publish
        self.output_dir = s.auto_output_path
        self.state_file = s.auto_output_path / "seen.json"
        self.generate_thumbnail = bool(getattr(s, "auto_generate_thumbnail", True))


# ------------------------------------------------------------------- run state --

@dataclass
class RunState:
    running: bool = False
    started_at: Optional[float] = None
    finished_at: Optional[float] = None
    trigger: str = ""          # "manual" | "schedule"
    phase: str = "idle"        # human-readable current phase
    processed: int = 0
    total: int = 0
    last_error: str = ""
    log: list[str] = field(default_factory=list)
    current_paper: Optional[dict] = None
    papers_queue: list = field(default_factory=list)

    def snapshot(self) -> dict:
        return asdict(self)


_state = RunState()
_state_lock = threading.Lock()
_run_lock = threading.Lock()  # ensures only one automation run at a time
# Optional admin selection for the next manual run (paper ids). Cleared when consumed.
_pending_paper_ids: list[str] | None = None
# Cooperative cancel — checked between papers (and at run start).
_cancel_event = threading.Event()


def _run_log_path(state_dir: Path | None = None) -> Path:
    root = Path(state_dir or get_settings().auto_output_path)
    return root / "run_log.jsonl"


def _history_path(state_dir: Path | None = None) -> Path:
    root = Path(state_dir or get_settings().auto_output_path)
    return root / "history.json"


def _append_run_log(line: str) -> None:
    """Persist one log line so the admin Run log survives restarts / new runs."""
    try:
        path = _run_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"ts": time.time(), "line": line}, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _load_persisted_log(limit: int = _LOG_TAIL) -> list[str]:
    path = _run_log_path()
    if not path.is_file():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    out: list[str] = []
    for raw in lines[-max(1, limit):]:
        raw = raw.strip()
        if not raw:
            continue
        try:
            obj = json.loads(raw)
            line = str(obj.get("line") or "").strip()
            if line:
                out.append(line)
        except Exception:
            out.append(raw)
    return out


def _hydrate_log_from_disk() -> None:
    """Fill in-memory log from disk when empty (e.g. after process restart)."""
    persisted = _load_persisted_log()
    if not persisted:
        return
    with _state_lock:
        if _state.log:
            return
        _state.log = persisted[-_LOG_TAIL:]


def _load_history(state_dir: Path | None = None) -> list[dict]:
    path = _history_path(state_dir)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = data.get("runs") if isinstance(data, dict) else data
        return [r for r in (runs or []) if isinstance(r, dict) and r.get("id")]
    except Exception:
        return []


# Public alias for admin listing / other modules.
load_history = _load_history


def _save_history(runs: list[dict], state_dir: Path | None = None) -> None:
    path = _history_path(state_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Newest first; cap length.
    cleaned = [r for r in runs if isinstance(r, dict) and r.get("id")][:_HISTORY_MAX]
    path.write_text(json.dumps({"runs": cleaned}, indent=2), encoding="utf-8")


def upsert_history(
    folder_id: str,
    *,
    status: str = "",
    paper: dict | None = None,
    published: bool | None = None,
    deleted: bool | None = None,
    archived: bool | None = None,
    youtube: dict | None = None,
    job_id: str = "",
    extra: dict | None = None,
) -> dict:
    """Upsert a durable run-history row (survives folder delete for published)."""
    fid = Path(str(folder_id or "")).name
    if not fid:
        return {}
    runs = _load_history()
    now = time.time()
    entry: dict | None = next((r for r in runs if r.get("id") == fid), None)
    if entry is None:
        entry = {"id": fid, "created_at": now}
        runs.insert(0, entry)
    entry["updated_at"] = now
    if status:
        entry["status"] = status
    if paper is not None:
        entry["paper"] = {
            "id": paper.get("id") or "",
            "title": paper.get("title") or fid,
            "authors": list(paper.get("authors") or [])[:5],
            "arxiv_id": (paper.get("id") or "").split(":")[-1] if paper.get("id") else "",
            "source": paper.get("source") or "",
            "url": paper.get("url") or "",
            "code_url": paper.get("code_url") or "",
            "abstract": (paper.get("abstract") or "")[:400],
        }
    if published is not None:
        entry["published"] = bool(published)
        if published and entry.get("status") != "published":
            entry["status"] = "published"
    if deleted is not None:
        entry["deleted"] = bool(deleted)
    if archived is not None:
        entry["archived"] = bool(archived)
        if archived:
            entry["archived_at"] = now
        else:
            entry.pop("archived_at", None)
    if youtube is not None:
        entry["youtube"] = youtube
    if job_id:
        entry["job_id"] = job_id
    if extra:
        entry.update(extra)
    # Move updated entry to front.
    runs = [entry] + [r for r in runs if r.get("id") != fid]
    _save_history(runs)
    return entry


def mark_folder_published(folder: Path | str, record: dict | None = None) -> Path:
    """Write ``published.json`` and sync history (admin review or auto YouTube)."""
    base = Path(folder)
    base.mkdir(parents=True, exist_ok=True)
    payload = dict(record or {})
    payload.setdefault("reviewed_at", time.time())
    (base / "published.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    paper_meta: dict = {}
    pj = base / "paper.json"
    if pj.is_file():
        try:
            paper_meta = json.loads(pj.read_text(encoding="utf-8"))
        except Exception:
            paper_meta = {}
    upsert_history(
        base.name,
        status="published",
        paper=paper_meta,
        published=True,
        deleted=False,
        youtube=payload.get("youtube") if isinstance(payload.get("youtube"), dict) else None,
        job_id=str(payload.get("job_id") or ""),
    )
    return base / "published.json"


def _record(msg: str) -> None:
    _LOG.info(msg)
    line = f"{_dt.datetime.now():%H:%M:%S} {msg}"
    _append_run_log(line)
    with _state_lock:
        _state.log.append(line)
        _state.log[:] = _state.log[-_LOG_TAIL:]


def _set(**kw) -> None:
    with _state_lock:
        for k, v in kw.items():
            setattr(_state, k, v)


def _pdf_name_for(paper_or_meta, *, title: str = "", paper_id: str = "") -> str:
    """Stable human PDF filename for a paper."""
    if isinstance(paper_or_meta, dict):
        title = title or str(paper_or_meta.get("title") or "")
        paper_id = paper_id or str(paper_or_meta.get("id") or "")
        existing = str(paper_or_meta.get("pdf_file") or "").strip()
        if existing and existing.lower().endswith(".pdf") and existing.lower() != "paper.pdf":
            return Path(existing).name
    else:
        title = title or getattr(paper_or_meta, "title", "") or ""
        paper_id = paper_id or getattr(paper_or_meta, "id", "") or ""
    return _sources.pdf_basename(title, paper_id)


def _paper_dict(paper, *, folder: str = "", pdf_ready: bool = False, pdf_file: str = "") -> dict:
    name = pdf_file or (_pdf_name_for(paper) if pdf_ready else "")
    return {
        "id": paper.id,
        "title": paper.title,
        "authors": (paper.authors or [])[:5],
        "pdf_url": paper.pdf_url,
        "code_url": paper.code_url,
        "published": paper.published,
        "source": paper.source,
        "folder": folder,
        "pdf_file": name if pdf_ready else (pdf_file or ""),
        "has_code": bool(getattr(paper, "has_code", None) or paper.code_url),
    }


def _load_last_run(state_dir: Path) -> dict:
    path = state_dir / "last_run.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_last_run(state_dir: Path, data: dict) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    (state_dir / "last_run.json").write_text(json.dumps(data, indent=2), encoding="utf-8")


def _run_hours() -> list[int]:
    s = get_settings()
    return sorted({int(h) for h in str(s.auto_run_hours).split(",") if h.strip().isdigit() and 0 <= int(h) <= 23})


def _in_working_hours(hour: int) -> bool:
    s = get_settings()
    start, end = s.auto_work_start_hour, s.auto_work_end_hour
    return start <= hour < end


def _next_run_iso(hours: list[int]) -> Optional[str]:
    """Next configured run slot that is not blocked by working hours."""
    effective = [h for h in hours if not _in_working_hours(h)]
    if not effective:
        return None
    now = _dt.datetime.now()
    for delta in range(0, 2):
        day = now + _dt.timedelta(days=delta)
        for h in effective:
            cand = day.replace(hour=h, minute=0, second=0, microsecond=0)
            if cand > now:
                return cand.isoformat(timespec="minutes")
    return None


def _folder_has_video(folder: Path) -> bool:
    return _folder_has_kind(folder, "video") or _folder_has_kind(folder, "reel")


def _folder_is_complete(folder: Path) -> bool:
    """True when the primary deliverable exists — keep it out of the next-queue.

    Long-form ``video/video.mp4`` (or flat ``video_video.mp4``) means the paper
    is done for queue purposes. A missing reel must not re-surface the paper as
    ``Resume`` in Next input PDFs — that misleads admins into thinking the run
    never finished. Reel-only folders count as complete when long-form is off.
    """
    has_long = _folder_has_kind(folder, "video")
    if has_long:
        return True
    has_reel = _folder_has_kind(folder, "reel")
    if not has_reel:
        return False
    try:
        # Reel-only mode (long-form disabled).
        if not get_settings().auto_make_video:
            return True
    except Exception:
        pass
    # Has reel but long-form was expected and is still missing → incomplete.
    return False


def _folder_has_kind(folder: Path, kind: str) -> bool:
    return (folder / kind / "video.mp4").is_file() or (folder / f"{kind}_video.mp4").is_file()


def _paper_from_meta(meta: dict, folder: Path | None = None):
    """Rebuild a ``Paper`` from ``paper.json`` for resume."""
    fallback = folder.name if folder is not None else "paper"
    return _sources.Paper(
        id=str(meta.get("id") or ""),
        title=str(meta.get("title") or fallback),
        abstract=str(meta.get("abstract") or ""),
        authors=list(meta.get("authors") or []),
        pdf_url=str(meta.get("pdf_url") or ""),
        code_url=str(meta.get("code_url") or ""),
        published=str(meta.get("published") or ""),
        source=str(meta.get("source") or "resume"),
        score=float(meta.get("score") or 0),
        url=str(meta.get("url") or ""),
    )


def _load_incomplete_papers(cfg: _CfgAdapter) -> list:
    """Papers reconstructed from incomplete automation folders."""
    papers = []
    for item in list_incomplete(cfg.output_dir):
        folder = cfg.output_dir / item["folder"]
        meta_path = folder / "paper.json"
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        paper = _paper_from_meta(meta, folder)
        if not paper.id:
            paper.id = f"folder:{folder.name}"
        if not paper.pdf_url:
            pdf = _sources.resolve_pdf_path(folder, meta if isinstance(meta, dict) else {})
            paper.pdf_url = f"file://{pdf}"
        papers.append(paper)
    return papers


def list_incomplete(output_dir: Path | None = None) -> list[dict]:
    """Folders that have a PDF but no finished video — safe to resume."""
    root = Path(output_dir or get_settings().auto_output_path)
    out: list[dict] = []
    if not root.is_dir():
        return out
    for folder in sorted(root.iterdir(), reverse=True):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        meta_path = folder / "paper.json"
        meta: dict = {}
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
            except Exception:
                meta = {}
        pdf = _sources.resolve_pdf_path(folder, meta)
        if not pdf.is_file() or pdf.stat().st_size < 1024:
            continue
        if _folder_is_complete(folder):
            continue
        checkpoint = _load_checkpoint(folder)
        out.append({
            "folder": folder.name,
            "id": meta.get("id") or "",
            "title": meta.get("title") or folder.name,
            "pdf_ready": True,
            "pdf_file": pdf.name,
            "pdf_bytes": pdf.stat().st_size,
            "has_video": _folder_has_kind(folder, "video"),
            "has_reel": _folder_has_kind(folder, "reel"),
            "left_at": checkpoint.get("phase") or "downloaded (render not finished)",
            "checkpoint": checkpoint,
            "source": meta.get("source") or "",
            "code_url": meta.get("code_url") or "",
            "pdf_url": meta.get("pdf_url") or "",
            "resume": True,
        })
    return out


def _checkpoint_path(paper_dir: Path) -> Path:
    return paper_dir / "checkpoint.json"


def _load_checkpoint(paper_dir: Path) -> dict:
    path = _checkpoint_path(paper_dir)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(paper_dir: Path, **kw) -> None:
    """Persist resume metadata for ``paper_dir``.

    The Path argument is ``paper_dir`` (not ``folder``) so a legacy
    ``folder="<name>"`` keyword never collides with the positional Path.
    """
    # Legacy callers / older checkpoints may pass folder="<name>".
    if "folder" in kw and "folder_name" not in kw:
        kw["folder_name"] = kw.pop("folder")
    else:
        kw.pop("folder", None)
    path = _checkpoint_path(paper_dir)
    data = _load_checkpoint(paper_dir)
    data.update(kw)
    data["updated_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    try:
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass


def _clear_checkpoint(paper_dir: Path) -> None:
    try:
        _checkpoint_path(paper_dir).unlink(missing_ok=True)
    except OSError:
        pass


def status() -> dict:
    s = get_settings()
    _hydrate_log_from_disk()
    with _state_lock:
        snap = _state.snapshot()
    # Always prefer the durable log tail so the UI stays live after reloads.
    persisted = _load_persisted_log()
    mem = list(snap.get("log") or [])
    if persisted and len(persisted) > len(mem):
        snap["log"] = persisted
    elif mem:
        snap["log"] = mem
    run_hours = sorted({int(h) for h in str(s.auto_run_hours).split(",") if h.strip().isdigit() and 0 <= int(h) <= 23})
    incomplete = list_incomplete(s.auto_output_path)
    snap["enabled"] = s.auto_enabled
    snap["run_hours"] = run_hours
    snap["work_hours"] = {"start": s.auto_work_start_hour, "end": s.auto_work_end_hour}
    snap["effective_run_hours"] = [h for h in run_hours if not _in_working_hours(h)]
    snap["blocked_run_hours"] = [h for h in run_hours if _in_working_hours(h)]
    snap["next_run"] = _next_run_iso(run_hours)
    snap["source"] = s.auto_source
    snap["max_papers"] = s.auto_max_papers
    snap["require_code"] = s.auto_require_code
    snap["last_run"] = _load_last_run(s.auto_output_path)
    snap["incomplete"] = incomplete
    snap["incomplete_count"] = len(incomplete)
    snap["can_resume"] = len(incomplete) > 0 and not snap.get("running")
    snap["llm_provider"] = (s.llm_provider or "auto").strip().lower() or "auto"
    snap["active_provider"] = s.active_provider
    snap["llm_text_model"] = s.llm_text_model
    snap["thumbnail_backend"] = (s.thumbnail_backend or "auto").strip().lower() or "auto"
    return snap


def preview() -> dict:
    """Return up to ``max_papers`` (default 3) next papers for the admin UI.

    Shows incomplete (pending resume) first, then fresh candidates.
    Nothing here auto-starts — admin must select and Run / Resume.
    """
    with _state_lock:
        if _state.running:
            return {
                "running": True,
                "papers": list(_state.papers_queue),
                "current_paper": _state.current_paper,
            }
    try:
        cfg = _CfgAdapter()
        limit = max(1, min(int(cfg.max_papers or 3), 3))
        incomplete = list_incomplete(cfg.output_dir)
        # Fetch enough fresh candidates to fill the preview after incompletes.
        room = max(0, limit - min(len(incomplete), limit))
        fresh: list = []
        if room > 0:
            old = cfg.max_papers
            cfg.max_papers = room
            try:
                fresh = _select_papers(cfg, silent=True)
            finally:
                cfg.max_papers = old

        papers: list[dict] = []
        seen: set[str] = set()
        for item in incomplete[:limit]:
            pid = str(item.get("id") or "")
            if pid:
                seen.add(pid)
            papers.append({
                "id": pid or f"folder:{item['folder']}",
                "title": item.get("title") or item["folder"],
                "authors": [],
                "pdf_url": item.get("pdf_url") or "",
                "code_url": item.get("code_url") or "",
                "published": "",
                "source": item.get("source") or "resume",
                "folder": item.get("folder") or "",
                "pdf_file": item.get("pdf_file") or _pdf_name_for(item),
                "has_code": bool(item.get("code_url")),
                "resume": True,
                "left_at": item.get("left_at") or "",
                "has_video": bool(item.get("has_video")),
                "has_reel": bool(item.get("has_reel")),
            })
        for p in fresh:
            if p.id in seen:
                continue
            d = _paper_dict(p)
            d["resume"] = False
            papers.append(d)
            if len(papers) >= limit:
                break

        return {
            "running": False,
            "papers": papers,
            "incomplete": incomplete,
            "current_paper": incomplete[0] if incomplete else None,
            "count": len(papers),
            "resume_count": len(incomplete),
            "max_papers": limit,
        }
    except Exception as e:  # noqa: BLE001
        return {
            "running": False, "papers": [], "incomplete": [],
            "current_paper": None, "count": 0, "error": str(e),
        }


# ------------------------------------------------------------ dedup state file --

def _load_seen(state_file: Path) -> set[str]:
    try:
        return set(json.loads(state_file.read_text(encoding="utf-8")).get("seen", []))
    except Exception:
        return set()


def _mark_seen(state_file: Path, paper_id: str) -> None:
    if not paper_id:
        return
    seen = _load_seen(state_file)
    seen.add(paper_id)
    if ":" in paper_id:
        prefix, bare = paper_id.split(":", 1)
        if bare:
            seen.add(bare)
            if prefix != "arxiv":
                seen.add(f"arxiv:{bare}")
    state_file.parent.mkdir(parents=True, exist_ok=True)
    state_file.write_text(json.dumps({"seen": sorted(seen)}, indent=2), encoding="utf-8")


def _unmark_seen(state_file: Path, paper_id: str) -> None:
    seen = _load_seen(state_file)
    if paper_id in seen:
        seen.discard(paper_id)
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps({"seen": sorted(seen)}, indent=2), encoding="utf-8")


def _safe_output_folder(folder_name: str) -> Path:
    """Resolve an automation output folder; reject path traversal."""
    root = get_settings().auto_output_path.resolve()
    name = Path(str(folder_name or "")).name
    if not name or name in (".", ".."):
        raise ValueError("Invalid folder name")
    folder = (root / name).resolve()
    if not folder.is_relative_to(root):
        raise ValueError("Forbidden folder path")
    return folder


def cancel_run() -> dict:
    """Ask the active automation run to stop after the current paper finishes."""
    with _state_lock:
        running = _state.running
    if not running:
        return {"ok": False, "message": "No automation run is active."}
    _cancel_event.set()
    _record("pause requested by admin — will stop after current paper")
    _set(phase="pausing…")
    return {"ok": True, "message": "Pause requested — finishing current paper, then stopping."}


def delete_job(folder_name: str = "", *, paper_id: str = "", mark_seen: bool = False) -> dict:
    """Delete an automation output folder (incomplete or finished) and/or mark paper as seen."""
    cfg = _CfgAdapter()
    folder_obj = None
    if folder_name:
        try:
            folder_obj = _safe_output_folder(folder_name)
        except Exception:
            folder_obj = None

    pid = str(paper_id or "").strip()
    if folder_obj and folder_obj.is_dir():
        meta_path = folder_obj / "paper.json"
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                if not pid:
                    pid = str(meta.get("id") or "")
            except Exception:
                pass
        # Don't delete the folder currently being rendered.
        with _state_lock:
            current = _state.current_paper or {}
            running = _state.running
        if running and current.get("folder") == folder_obj.name:
            raise RuntimeError("Cannot delete the folder that is currently rendering — pause first.")
        was_published = (folder_obj / "published.json").is_file()
        if not was_published:
            try:
                hist = next((r for r in _load_history() if r.get("id") == folder_obj.name), None)
                was_published = bool(hist and (hist.get("published") or hist.get("status") == "published"))
            except Exception:
                was_published = False
        paper_snapshot = {}
        if (folder_obj / "paper.json").is_file():
            try:
                paper_snapshot = json.loads((folder_obj / "paper.json").read_text(encoding="utf-8"))
            except Exception:
                paper_snapshot = {"id": pid} if pid else {}
        elif pid:
            paper_snapshot = {"id": pid}
        shutil.rmtree(folder_obj, ignore_errors=False)
        upsert_history(
            folder_obj.name,
            status="published" if was_published else "deleted",
            published=was_published,
            deleted=True,
            paper=paper_snapshot or None,
        )
        if mark_seen or pid:
            if pid:
                _mark_seen(cfg.state_file, pid)
            _mark_seen(cfg.state_file, f"folder:{folder_obj.name}")
        _record(f"deleted job folder {folder_obj.name}" + (" (marked seen)" if pid else ""))
        return {
            "ok": True,
            "folder": folder_obj.name,
            "paper_id": pid,
            "marked_seen": bool(pid),
        }

    # Folder does not exist or wasn't given: fallback to marking paper_id as seen/deleted
    if pid or folder_name:
        target_id = pid or (f"folder:{folder_name}" if folder_name else "")
        if target_id:
            _mark_seen(cfg.state_file, target_id)
            if pid and folder_name:
                _mark_seen(cfg.state_file, f"folder:{folder_name}")
            _record(f"removed paper/folder reference: {target_id}")
            return {
                "ok": True,
                "folder": folder_name,
                "paper_id": pid,
                "marked_seen": True,
            }

    raise ValueError("folder_name or paper_id required")


def archive_job(folder_name: str, *, archived: bool = True) -> dict:
    """Mark a run as archived (History) without deleting files.

    Archived runs leave the active Queue / Ready filters and appear under History.
    """
    fid = Path(str(folder_name or "")).name
    if not fid or fid.lower() in {"topics", "__pycache__"}:
        raise ValueError("Invalid folder")
    root = Path(get_settings().auto_output_path)
    folder = root / fid
    paper_meta: dict = {}
    status = "ready"
    published = False
    if folder.is_dir():
        pj = folder / "paper.json"
        if pj.is_file():
            try:
                paper_meta = json.loads(pj.read_text(encoding="utf-8"))
            except Exception:
                paper_meta = {}
        published = (folder / "published.json").is_file()
        has_vid = any(folder.rglob("*.mp4")) or any(folder.rglob("*.webm"))
        if published:
            status = "published"
        elif has_vid:
            status = "ready"
        elif _sources.resolve_pdf_path(folder, paper_meta).is_file():
            status = "incomplete"
        else:
            status = "processing"
        title = str(paper_meta.get("title") or "").strip()
        if not title or title.lower() in {fid.lower(), "topics", "paper"}:
            for meta_rel in ("video/metadata.json", "metadata.json"):
                mp = folder / meta_rel
                if not mp.is_file():
                    continue
                try:
                    m = json.loads(mp.read_text(encoding="utf-8"))
                    mt = str(m.get("title") or "").strip()
                    if mt:
                        paper_meta["title"] = mt
                        break
                except Exception:
                    pass
    else:
        hist = next((r for r in _load_history() if r.get("id") == fid), None)
        if not hist:
            raise FileNotFoundError(f"Folder not found: {folder_name}")
        paper_meta = hist.get("paper") or {"title": fid}
        published = bool(hist.get("published"))
        status = str(hist.get("status") or ("published" if published else "ready"))

    entry = upsert_history(
        fid,
        status=status,
        paper=paper_meta or {"title": fid},
        published=published,
        archived=bool(archived),
        deleted=False,
    )
    _record(f"{'archived' if archived else 'unarchived'} job {fid}")
    return {"ok": True, "folder": fid, "archived": bool(archived), "entry": entry}


def skip_paper(paper_id: str, *, folder_name: str = "", delete_folder: bool = False) -> dict:
    """Mark a paper as already handled so it won't appear in the next queue.

    Use when a similar/same paper was already generated. Optionally delete its
    incomplete download folder.
    """
    pid = str(paper_id or "").strip()
    if not pid and folder_name:
        folder = _safe_output_folder(folder_name)
        meta_path = folder / "paper.json"
        if meta_path.is_file():
            try:
                pid = str(json.loads(meta_path.read_text(encoding="utf-8")).get("id") or "")
            except Exception:
                pid = ""
        if not pid:
            pid = f"folder:{folder.name}"
    if not pid:
        raise ValueError("paper_id or folder_name required")
    cfg = _CfgAdapter()
    _mark_seen(cfg.state_file, pid)
    deleted = None
    if delete_folder and folder_name:
        try:
            deleted = delete_job(folder_name, mark_seen=False)
        except Exception as e:  # noqa: BLE001
            deleted = {"ok": False, "error": str(e)}
    _record(f"skipped / marked seen: {pid}")
    return {"ok": True, "paper_id": pid, "deleted": deleted}


def complete_paper(paper_id: str = "", folder_name: str = "") -> dict:
    """Resume/complete a specific incomplete paper (or its folder)."""
    ids: list[str] = []
    if paper_id:
        ids.append(str(paper_id).strip())
    if folder_name:
        ids.append(f"folder:{Path(folder_name).name}")
        # Prefer resolving to real paper id from meta
        try:
            folder = _safe_output_folder(folder_name)
            meta = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
            pid = str(meta.get("id") or "").strip()
            if pid:
                ids.insert(0, pid)
        except Exception:
            pass
    ids = [i for i in ids if i]
    if not ids:
        raise ValueError("paper_id or folder_name required")
    started = trigger("manual", paper_ids=ids)
    if not started:
        raise RuntimeError("An automation run is already in progress")
    return {"ok": True, "paper_ids": ids, "status": status()}


# ----------------------------------------------------------------- one paper ---

def _write_paper_meta(folder: Path, paper, *, pdf_file: str = "") -> None:
    folder.mkdir(parents=True, exist_ok=True)
    pdf_name = pdf_file or _pdf_name_for(paper)
    meta = {
        "id": paper.id,
        "arxiv_id": paper.id.split(":", 1)[-1] if str(paper.id).startswith("arxiv:") else paper.id.split(":", 1)[-1],
        "title": paper.title,
        "authors": paper.authors,
        "abstract": paper.abstract,
        "pdf_url": paper.pdf_url,
        "pdf_file": pdf_name,
        "code_url": paper.code_url,
        "published": paper.published,
        "source": paper.source,
        "url": getattr(paper, "url", "") or "",
        "score": getattr(paper, "score", 0),
        "folder": folder.name,
        "processed_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
    }
    (folder / "paper.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return pdf_name


def _download(url: str, dest: Path) -> None:
    import urllib.request

    dest.parent.mkdir(parents=True, exist_ok=True)
    # Prefer export.arxiv.org / https; some OA links redirect.
    headers = {
        "User-Agent": "multimodal-studio-automation/2.1",
        "Accept": "application/pdf,*/*",
    }
    # arXiv PDF URLs sometimes need the trailing .pdf stripped of version quirks.
    clean = (url or "").strip()
    if "arxiv.org/pdf/" in clean and not clean.endswith(".pdf"):
        clean = clean.rstrip("/") + ".pdf"
    req = urllib.request.Request(clean, headers=headers)
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as fh:
        shutil.copyfileobj(resp, fh)


def _copy_tree(src: Path, dest: Path) -> int:
    """Copy a directory tree; return number of files copied."""
    if not src.is_dir():
        return 0
    n = 0
    dest.mkdir(parents=True, exist_ok=True)
    for f in src.rglob("*"):
        if not f.is_file():
            continue
        rel = f.relative_to(src)
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            shutil.copyfile(f, out)
            n += 1
        except OSError:
            continue
    return n


def _write_post_text(out_dir: Path, meta: dict, paper_title: str) -> str:
    """Human-readable social post next to the video."""
    title = (meta.get("title") or paper_title or "New paper video").strip()
    desc = (meta.get("description") or "").strip()
    tags = meta.get("tags") or []
    tag_line = ""
    if isinstance(tags, list) and tags:
        tag_line = " ".join(
            ("#" + str(t).strip().lstrip("#").replace(" ", "") for t in tags if str(t).strip())
        )
    body = title
    if desc:
        body += "\n\n" + desc
    if tag_line:
        body += "\n\n" + tag_line
    path = out_dir / "post.txt"
    path.write_text(body.strip() + "\n", encoding="utf-8")
    return path.name


def _package_job_outputs(
    *,
    kind: str,
    job,
    work: Path,
    folder: Path,
    paper_title: str,
    generate_thumb: bool,
) -> dict:
    """Copy video, thumbnail, slides, voice, and post text into ``folder/kind/``."""
    result = {
        "kind": kind,
        "job_id": job.id,
        "video": "",
        "thumbnail": "",
        "slides": "",
        "audio_dir": "",
        "post": "",
        "metadata": "",
        "error": "",
    }
    out = folder / kind
    out.mkdir(parents=True, exist_ok=True)

    # Ensure thumbnail exists for automation packages (pipeline is on-demand only).
    if generate_thumb and not (job.artifacts or {}).get("thumbnail"):
        try:
            from ..orchestrator import generate_job_thumbnail

            ok, msg = generate_job_thumbnail(job)
            _record(f"[{kind}] thumbnail: {msg}" if ok else f"[{kind}] thumbnail soft-fail: {msg}")
        except Exception as e:  # noqa: BLE001
            _record(f"[{kind}] thumbnail generation soft-fail: {e}")

    arts = job.artifacts or {}
    content = job.content or {}

    # Video
    video_final = arts.get("video_final")
    src_video = None
    if video_final:
        cand = work / Path(str(video_final)).name
        if cand.is_file():
            src_video = cand
    if src_video is None:
        for name in ("final.mp4", "raw.mp4"):
            if (work / name).is_file():
                src_video = work / name
                break
    if src_video is not None:
        dest = out / "video.mp4"
        shutil.copyfile(src_video, dest)
        result["video"] = f"{kind}/video.mp4"
        _record(f"[{kind}] saved {result['video']}")
    else:
        result["error"] = "no video produced"

    # Thumbnail
    thumb_name = content.get("thumbnail") or ""
    tsrc = None
    if arts.get("thumbnail"):
        tsrc = work / Path(str(arts["thumbnail"])).name
    if (tsrc is None or not tsrc.is_file()) and thumb_name:
        tsrc = work / str(thumb_name)
    if (tsrc is None or not tsrc.is_file()) and (work / "thumbnail.png").is_file():
        tsrc = work / "thumbnail.png"
    if tsrc is not None and tsrc.is_file():
        tdest = out / "thumbnail.png"
        shutil.copyfile(tsrc, tdest)
        result["thumbnail"] = f"{kind}/thumbnail.png"

    # Slides / HTML
    html = work / "presentation.html"
    if html.is_file():
        shutil.copyfile(html, out / "presentation.html")
        result["slides"] = f"{kind}/presentation.html"
    # Cover / page images used by slides
    pages = work / "pages"
    if pages.is_dir():
        _copy_tree(pages, out / "pages")

    # Voice / narration audio
    audio = work / "audio"
    if audio.is_dir():
        n = _copy_tree(audio, out / "audio")
        if n:
            result["audio_dir"] = f"{kind}/audio"
            _record(f"[{kind}] copied {n} audio file(s)")

    # Narration script
    narration = (content.get("narration") or "").strip()
    if narration:
        (out / "narration.txt").write_text(narration + "\n", encoding="utf-8")

    # Publish metadata + social post text
    meta = {
        "title": content.get("publish_title") or content.get("slide_title") or paper_title,
        "description": content.get("publish_description") or "",
        "tags": content.get("publish_tags") or [],
        "slide_title": content.get("slide_title") or "",
        "doc_type": content.get("doc_type") or "",
        "job_id": job.id,
        "kind": kind,
    }
    (out / "metadata.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    result["metadata"] = f"{kind}/metadata.json"
    result["post"] = f"{kind}/{_write_post_text(out, meta, paper_title)}"
    # Root-level post for the long-form video (primary).
    if kind == "video":
        _write_post_text(folder, meta, paper_title)

    # If the pipeline uploaded to YouTube, mark this automation folder published.
    yt = (arts.get("youtube") if isinstance(arts, dict) else None) or None
    if isinstance(yt, dict) and yt.get("url") and kind == "video":
        try:
            mark_folder_published(
                folder,
                {
                    "reviewed_at": time.time(),
                    "title": meta.get("title") or paper_title,
                    "description": meta.get("description") or "",
                    "tags": meta.get("tags") or [],
                    "youtube": yt,
                    "video": result.get("video") or "",
                    "job_id": job.id,
                    "source": "pipeline",
                },
            )
            _record(f"[{kind}] published to YouTube: {yt.get('url')}")
        except Exception as e:  # noqa: BLE001
            _record(f"[{kind}] published.json write soft-fail: {e}")
    elif kind == "video" and result.get("video"):
        upsert_history(
            folder.name,
            status="ready",
            published=False,
            deleted=False,
            job_id=job.id,
            paper={"title": paper_title, "id": ""},
        )

    return result


def _render_one(cfg: _CfgAdapter, kind: str, pdf_path: Path, folder: Path,
                *, video_format: str, seconds: int, topics: str,
                paper_title: str = "") -> dict:
    """Create + run one pipeline job in-process and package its artifacts.

    Dedupes against Studio History using DB job metadata
    (``automation_paper_id`` / ``pdf_sha256`` + ``video_format`` / ``automation_kind``).
    """
    import hashlib
    import re

    from ..workspace_store import resolve_job_dir

    result = {
        "kind": kind, "job_id": "", "video": "", "thumbnail": "",
        "slides": "", "audio_dir": "", "post": "", "error": "",
    }
    paper_meta: dict = {}
    try:
        paper_meta = json.loads((folder / "paper.json").read_text(encoding="utf-8"))
    except Exception:
        paper_meta = {}
    paper_id = str(paper_meta.get("id") or "").strip()
    arxiv_id = str(paper_meta.get("arxiv_id") or "").strip()
    title = (paper_title or paper_meta.get("title") or folder.name or "paper").strip()

    pdf_sha = ""
    try:
        h = hashlib.sha256()
        with pdf_path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        pdf_sha = h.hexdigest()
    except Exception:
        pdf_sha = ""

    existing = store.find_automation_duplicate(
        paper_id=paper_id,
        video_format=video_format,
        kind=kind,
        pdf_sha256=pdf_sha,
    )
    if existing:
        arts = existing.artifacts or {}
        has_video = bool(arts.get("video_final"))
        if existing.status == "running" or existing.busy:
            result["job_id"] = existing.id
            result["error"] = f"duplicate skipped — job {existing.id} still running"
            result["skipped"] = True
            _record(f"[{kind}] duplicate of running job {existing.id} — skip")
            return result
        if has_video and existing.status != "error":
            _record(
                f"[{kind}] reuse job {existing.id} "
                f"(paper={paper_id or pdf_sha[:12]} format={video_format}) — no new History row"
            )
            work = resolve_job_dir(existing.id, create=False)
            packaged = _package_job_outputs(
                kind=kind,
                job=existing,
                work=work,
                folder=folder,
                paper_title=title,
                generate_thumb=cfg.generate_thumbnail,
            )
            result["job_id"] = existing.id
            result["skipped"] = True
            result.update(packaged)
            return result

    _record(f"[{kind}] creating job ({video_format}, {seconds}s)")
    video_opts = normalize_video_options(
        video_format=video_format,
        target_duration=int(seconds),
        video_theme=cfg.video_theme,
        video_style=getattr(cfg, "video_style", None) or "hybrid",
    )
    voice_opts = {
        "muse_voice": (getattr(cfg, "muse_voice", None) or "Kore").strip() or "Kore",
    }
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")[:60] or "paper"
    # Same PDF display name for video + reel of this paper (kind lives in options).
    display_name = paper_meta.get("pdf_file") or _pdf_name_for(paper_meta, title=title, paper_id=paper_id)
    if not str(display_name).lower().endswith(".pdf"):
        display_name = f"{slug}.pdf"
    job = store.create(
        display_name,
        options={
            "publish": cfg.publish,
            "extra_topics": topics,
            "automation_paper_id": paper_id,
            "arxiv_id": arxiv_id,
            "automation_kind": kind,
            "automation_title": title[:200],
            "pdf_sha256": pdf_sha,
            "automation_folder": folder.name,
            "source_pdf": display_name,
            "lock_visual_preset": str(video_opts.get("video_style") or "").lower() not in ("", "auto"),
            **voice_opts,
            **video_opts,
        },
        user_id="system",
    )
    result["job_id"] = job.id
    work = resolve_job_dir(job.id, create=True)
    shutil.copyfile(pdf_path, work / "input.pdf")

    # Defer finalize so packaging can still copy pages/ + audio/ before cleanup.
    run_pipeline(job, finalize=False)

    if job.status == "error":
        result["error"] = job.error or "pipeline error"
        _record(f"[{kind}] job {job.id} failed: {result['error']}")
        return result

    # Re-resolve in case anything moved; still the bare id folder until finalize.
    work = resolve_job_dir(job.id, create=False)
    packaged = _package_job_outputs(
        kind=kind,
        job=job,
        work=work,
        folder=folder,
        paper_title=title,
        generate_thumb=cfg.generate_thumbnail,
    )
    result.update(packaged)
    try:
        from ..workspace_store import finalize_job_workspace

        finalize_job_workspace(job)
    except Exception as e:  # noqa: BLE001
        _record(f"[{kind}] workspace finalize soft-fail: {e}")
    return result


def _ensure_pdf(cfg: _CfgAdapter, paper, folder: Path, pdf_path: Path) -> bool:
    """Download PDF only when missing/invalid. Supports resume of local copies."""
    if pdf_path.is_file() and pdf_path.stat().st_size >= 1024:
        _record(f"reusing existing PDF ({pdf_path.stat().st_size // 1024} KB)")
        return True
    url = (paper.pdf_url or "").strip()
    if url.startswith("file://"):
        src = Path(url[7:])
        if src.is_file() and src.stat().st_size >= 1024:
            shutil.copyfile(src, pdf_path)
            return True
        _record("local file:// PDF missing")
        return False
    try:
        _record(f"downloading PDF: {url}")
        _download(url, pdf_path)
    except Exception as e:  # noqa: BLE001
        aid = paper.id.split(":", 1)[-1] if str(paper.id).startswith("arxiv:") else ""
        if aid:
            alt = f"https://export.arxiv.org/pdf/{aid}.pdf"
            try:
                _record(f"pdf retry via export.arxiv.org: {alt}")
                _download(alt, pdf_path)
            except Exception as e2:  # noqa: BLE001
                _record(f"pdf download failed: {e}; retry: {e2}")
                return False
        else:
            _record(f"pdf download failed: {e}")
            return False
    if not pdf_path.exists() or pdf_path.stat().st_size < 1024:
        _record("pdf download produced an empty/invalid file")
        return False
    return True


def _process_paper(cfg: _CfgAdapter, paper) -> bool:
    folder = _sources.find_or_create_folder(cfg.output_dir, paper)
    folder.mkdir(parents=True, exist_ok=True)
    pdf_name = _pdf_name_for(paper)
    # Prefer an already-downloaded PDF in this folder (resume / rename).
    existing_meta: dict = {}
    meta_path = folder / "paper.json"
    if meta_path.is_file():
        try:
            existing_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            existing_meta = {}
    if existing_meta.get("pdf_file"):
        pdf_name = Path(str(existing_meta["pdf_file"])).name
    pdf_path = folder / pdf_name
    legacy = folder / "paper.pdf"
    # Migrate legacy paper.pdf → named file once.
    if not pdf_path.is_file() and legacy.is_file() and legacy.stat().st_size >= 1024:
        try:
            legacy.rename(pdf_path)
            _record(f"renamed paper.pdf → {pdf_name}")
        except OSError:
            shutil.copyfile(legacy, pdf_path)
    _write_paper_meta(folder, paper, pdf_file=pdf_name)
    _save_checkpoint(
        folder,
        paper_id=paper.id,
        title=paper.title,
        phase="starting",
        folder_name=folder.name,
        pdf_file=pdf_name,
    )

    if not _ensure_pdf(cfg, paper, folder, pdf_path):
        _save_checkpoint(folder, phase="pdf_failed")
        return False
    # Ensure meta points at the real on-disk name.
    if pdf_path.is_file():
        pdf_name = pdf_path.name
        _write_paper_meta(folder, paper, pdf_file=pdf_name)
    _save_checkpoint(folder, phase="pdf_ready", pdf_file=pdf_name)

    folder_name = folder.name
    with _state_lock:
        if _state.current_paper and _state.current_paper.get("id") == paper.id:
            _state.current_paper = _paper_dict(
                paper, folder=folder_name, pdf_ready=True, pdf_file=pdf_name
            )

    topics = (
        "the paper's core contribution, method, and results, "
        "real-world impact, limitations, and key takeaways"
    )
    renders = []
    # Resume: skip kinds that already produced a video in this folder.
    if cfg.make_video:
        if _folder_has_kind(folder, "video"):
            _record("[video] already present — skipping (resume)")
            renders.append({
                "kind": "video", "job_id": "", "video": "video/video.mp4",
                "skipped": True, "error": "",
            })
        else:
            _save_checkpoint(folder, phase="rendering_video")
            renders.append(_render_one(
                cfg, "video", pdf_path, folder,
                video_format=cfg.video_format, seconds=cfg.video_seconds,
                topics=topics, paper_title=paper.title,
            ))

    # Instagram/reels are chosen manually in Studio (same PDF, different format).
    # Automation never spawns a second History job — one paper → one long-form video.
    if cfg.make_reel:
        _record(
            "[reel] skipped — automation is video-only; "
            "pick Instagram Reels in Studio to render a reel from the same PDF"
        )

    results_path = folder / "results.json"
    results_path.write_text(
        json.dumps(
            {
                "paper_id": paper.id,
                "title": paper.title,
                "folder": folder.name,
                "renders": renders,
                "finished_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    ok = any(r.get("video") for r in renders)
    if ok:
        _save_checkpoint(folder, phase="done")
        _clear_checkpoint(folder)
    else:
        _save_checkpoint(folder, phase="render_incomplete", renders=renders)
    return ok


def _select_papers(cfg: _CfgAdapter, *, silent: bool = False) -> list:
    seen = _load_seen(cfg.state_file)
    candidates = _sources.fetch_latest(cfg)
    if not silent:
        _record(f"fetched {len(candidates)} candidate papers from {cfg.source}")
    picked = []
    for p in candidates:
        if p.id in seen or not p.pdf_url:
            continue
        if cfg.require_code and not p.has_code:
            continue
        picked.append(p)
        if len(picked) >= cfg.max_papers:
            break
    if not picked and cfg.require_code:
        if not silent:
            _record("no papers with a code link; falling back to newest with a PDF")
        for p in candidates:
            if p.id not in seen and p.pdf_url:
                picked.append(p)
                if len(picked) >= cfg.max_papers:
                    break
    return picked


# ----------------------------------------------------------------- the run -----

def _resolve_selected_papers(cfg: _CfgAdapter, paper_ids: list[str], incomplete_papers: list) -> list:
    """Map admin-selected ids to Paper objects (incomplete first, then fresh fetch)."""
    want = [str(x).strip() for x in (paper_ids or []) if str(x).strip()]
    if not want:
        return []
    by_id: dict = {p.id: p for p in incomplete_papers}
    for item in list_incomplete(cfg.output_dir):
        folder = item.get("folder") or ""
        pid = str(item.get("id") or "")
        # Prefer the already-built Paper with the same id.
        paper = by_id.get(pid)
        if paper is None and folder:
            meta_path = cfg.output_dir / folder / "paper.json"
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                paper = _paper_from_meta(meta, cfg.output_dir / folder)
                if not paper.id:
                    paper.id = f"folder:{folder}"
                if not paper.pdf_url:
                    pdf = _sources.resolve_pdf_path(cfg.output_dir / folder, meta)
                    paper.pdf_url = f"file://{pdf}"
            except Exception:
                paper = None
        if paper is not None:
            if pid:
                by_id[pid] = paper
            if folder:
                by_id[f"folder:{folder}"] = paper
    missing = [i for i in want if i not in by_id]
    if missing:
        for p in _sources.fetch_latest(cfg):
            by_id[p.id] = p
    out = []
    seen = set()
    for pid in want:
        p = by_id.get(pid)
        if not p or p.id in seen:
            continue
        out.append(p)
        seen.add(p.id)
        if len(out) >= max(1, int(cfg.max_papers or 3)):
            break
    return out


def _run(trigger: str) -> None:
    global _pending_paper_ids
    if not _run_lock.acquire(blocking=False):
        _record("run already in progress; ignoring trigger")
        with _state_lock:
            # Only clear the optimistic claim from ``trigger()`` if we did not
            # actually own the lock (another run is active).
            if _state.trigger == trigger and _state.phase == "starting":
                _state.running = False
                _state.phase = "idle"
        return
    try:
        selected_ids = list(_pending_paper_ids or [])
        _pending_paper_ids = None
        cfg = _CfgAdapter()
        cfg.output_dir.mkdir(parents=True, exist_ok=True)
        _set(running=True, started_at=time.time(), finished_at=None, trigger=trigger,
             phase="checking compute", processed=0, total=0, last_error="",
             current_paper=None, papers_queue=[])
        with _state_lock:
            # Keep prior log lines; add a separator so history stays readable.
            if _state.log and _state.log[-1] != "———":
                sep = "——"
                _state.log.append(sep)
                _append_run_log(sep)
        _record(f"run started (trigger={trigger})")
        if selected_ids:
            _record(f"admin selected {len(selected_ids)} paper(s)")
        _cancel_event.clear()

        ok, reason = _compute.compute_available(cfg)
        if not ok:
            _record(f"compute busy: {reason}")
            if not _compute.wait_for_compute(cfg, _record):
                _set(phase="skipped (compute busy)")
                return

        resume_only = trigger in {"resume", "resume_only"}
        # Incomplete folders are MANUAL ONLY (Resume / Complete / explicit select).
        # Never auto-prepend them on schedule or blank "Run now" — that re-ran old
        # queues whenever the server restarted near a slot or admin opened cron.
        incomplete_papers = _load_incomplete_papers(cfg)
        if resume_only:
            papers = incomplete_papers
            if not papers:
                _record("nothing to resume — no incomplete paper folders")
                _set(phase="idle (nothing to resume)")
                return
            _record(f"resume-only: {len(papers)} incomplete folder(s)")
        elif selected_ids:
            _set(phase="selecting papers")
            papers = _resolve_selected_papers(cfg, selected_ids, incomplete_papers)
            if not papers:
                _record("selected paper id(s) could not be resolved")
                _set(phase="idle (selection empty)")
                return
            _record(f"admin selected {len(papers)} paper(s) — manual run only")
        elif trigger == "schedule":
            _set(phase="selecting papers")
            # Scheduled runs only pick fresh unseen papers — never old incompletes.
            papers = _select_papers(cfg)
            if incomplete_papers:
                _record(
                    f"note: {len(incomplete_papers)} incomplete folder(s) waiting — "
                    f"admin must Resume / Complete them (not auto-run)"
                )
        else:
            # Blank manual trigger without selection: do not start anything.
            _record(
                "manual run ignored — select pending paper(s) in Admin, "
                "or use Resume for incomplete folders"
            )
            _set(phase="idle (select papers to run)")
            return

        if not papers:
            _record("no fresh papers to process")
            _set(phase="idle (nothing new)")
            return
        queue = [_paper_dict(p) for p in papers]
        _set(total=len(papers), phase="rendering", papers_queue=queue)
        _record(f"processing {len(papers)} paper(s)")

        processed = 0
        for p in papers:
            if _cancel_event.is_set():
                _record("paused by admin — remaining papers left for later resume")
                _set(phase="paused")
                break
            folder_name = _sources.find_or_create_folder(cfg.output_dir, p).name
            _record(f"=== {p.title} [{p.id}] ===")
            _set(
                phase=f"rendering: {p.title[:60]}",
                current_paper=_paper_dict(p, folder=folder_name),
            )
            try:
                if _process_paper(cfg, p):
                    _mark_seen(cfg.state_file, p.id)
                    processed += 1
                    _record(f"done: {p.title}")
                    folder = _sources.find_or_create_folder(cfg.output_dir, p)
                    pub = (folder / "published.json").is_file()
                    upsert_history(
                        folder.name,
                        status="published" if pub else "ready",
                        paper=_paper_dict(p, folder=folder.name),
                        published=pub,
                        deleted=False,
                    )
                else:
                    _record(f"incomplete: {p.title}")
                    folder = _sources.find_or_create_folder(cfg.output_dir, p)
                    upsert_history(
                        folder.name,
                        status="incomplete",
                        paper=_paper_dict(p, folder=folder.name),
                        published=False,
                        deleted=False,
                    )
            except Exception as e:  # noqa: BLE001
                _record(f"error on {p.id}: {e}")
                _LOG.exception(f"paper failed: {p.id}")
                try:
                    folder = _sources.find_or_create_folder(cfg.output_dir, p)
                    _save_checkpoint(folder, phase="error", error=str(e))
                except Exception:
                    pass
            _set(processed=processed)
            if _cancel_event.is_set():
                _record("paused by admin after current paper")
                _set(phase="paused")
                break

        _save_last_run(cfg.output_dir, {
            "trigger": trigger,
            "started_at": _state.started_at,
            "finished_at": time.time(),
            "processed": processed,
            "total": len(papers),
            "paper_ids": [p.id for p in papers],
            "selected": bool(selected_ids),
        })
        _set(phase="idle", current_paper=None, papers_queue=[])
        _record(f"run finished ({processed}/{len(papers)})")
    except Exception as e:  # noqa: BLE001
        _record(f"run crashed: {e}")
        _LOG.exception("automation run crashed")
        _set(last_error=str(e), phase="error", current_paper=None, papers_queue=[])
    finally:
        _set(running=False, finished_at=time.time())
        _run_lock.release()


def trigger(trigger: str = "manual", paper_ids: list[str] | None = None) -> bool:
    """Start a run in the background. Returns False if one is already running.

    ``trigger="resume"`` continues incomplete folders only (PDF present, no video).
    ``manual`` requires ``paper_ids`` (admin must select pending items).
    ``schedule`` fetches fresh papers only — never auto-resumes old incompletes.
    """
    global _pending_paper_ids
    with _state_lock:
        if _state.running:
            return False
        # Claim the run immediately so a second click cannot spawn another thread
        # before ``_run`` acquires ``_run_lock``.
        _state.running = True
        _state.trigger = trigger
        _state.phase = "starting"
        _pending_paper_ids = list(paper_ids) if paper_ids else None
    threading.Thread(target=_run, args=(trigger,), name="auto-run", daemon=True).start()
    return True


def resume() -> bool:
    """Continue incomplete automation folders where a previous run stopped."""
    return trigger("resume")


# ------------------------------------------------------------------ scheduler --

_scheduler_thread: Optional[threading.Thread] = None
_scheduler_stop = threading.Event()


def _load_fired_keys(state_dir: Path) -> set[str]:
    path = state_dir / "schedule_fired.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("fired") or [])
    except Exception:
        return set()


def _save_fired_key(state_dir: Path, key: str) -> None:
    path = state_dir / "schedule_fired.json"
    fired = _load_fired_keys(state_dir)
    fired.add(key)
    # Keep ~14 days of keys.
    recent = sorted(fired)[-48:]
    state_dir.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"fired": recent}, indent=2), encoding="utf-8")


def _scheduler_loop() -> None:
    _LOG.info("automation scheduler started")
    while not _scheduler_stop.is_set():
        s = get_settings()
        if s.auto_enabled:
            now = _dt.datetime.now()
            hours = _run_hours()
            out_dir = s.auto_output_path
            fired = _load_fired_keys(out_dir)
            # Fire in the first 10 minutes of a slot (wider catch-up window),
            # and also catch a missed slot once if the process started late.
            for h in hours:
                key = f"{now:%Y-%m-%d}:{h:02d}"
                if key in fired:
                    continue
                due = (now.hour == h and now.minute < 10) or (
                    # Catch-up: same day, slot hour already passed, still unfired.
                    now.hour > h and now.hour - h <= 2
                )
                if not due:
                    continue
                if _in_working_hours(h):
                    _LOG.info(f"skipping scheduled run at {h:02d}:00 (working hours)")
                    _save_fired_key(out_dir, key)
                    continue
                _LOG.info(f"scheduler firing automation run for slot {key} (now {now:%H:%M})")
                _save_fired_key(out_dir, key)
                trigger("schedule")
                break
        _scheduler_stop.wait(60)


def start_scheduler() -> None:
    global _scheduler_thread
    if _scheduler_thread and _scheduler_thread.is_alive():
        return
    _scheduler_stop.clear()
    _scheduler_thread = threading.Thread(target=_scheduler_loop, name="auto-scheduler", daemon=True)
    _scheduler_thread.start()
