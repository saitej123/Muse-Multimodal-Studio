"""In-memory job store tracking pipeline runs, editable content, and progress.

Adds:
- Editable per-step content (extracted text, narration script) so users can
  refine the inputs and re-run individual stages to improve the output.
- A simple pub/sub event log per job so the API can stream live updates (SSE).
"""
from __future__ import annotations

import queue
import threading
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    SKIPPED = "skipped"
    ERROR = "error"


# Ordered pipeline stages surfaced to the UI.
STAGE_ORDER = [
    ("extract", "Extract content (VLM)"),
    ("generate", "Build slides + HTML"),
    ("narrate", "Voiceover per slide"),
    ("capture", "Capture slide images"),
    ("merge", "Assemble synced video"),
    ("publish_meta", "Title, description & thumbnail"),
    ("publish", "Upload to YouTube"),
]

# Which stages expose editable text the user can tweak before re-running.
EDITABLE_FIELDS = {
    "extract": "extracted_text",
    "generate": "extracted_text",  # HTML is generated from extracted_text
    "narrate": "narration",
}


@dataclass
class Stage:
    key: str
    label: str
    status: StageStatus = StageStatus.PENDING
    detail: str = ""
    started_at: Optional[float] = None
    ended_at: Optional[float] = None

    def dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d


@dataclass
class Job:
    id: str
    filename: str
    status: str = "running"  # running | done | error
    created_at: float = field(default_factory=time.time)
    user_id: str = ""  # owner; empty on legacy rows (admin-only access)
    stages: list[Stage] = field(default_factory=list)
    artifacts: dict = field(default_factory=dict)
    # Editable content produced/used by the pipeline.
    content: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    error: Optional[str] = None
    # Set while a runner thread is actively executing stages for this job;
    # used to prevent overlapping runs from corrupting shared state/files.
    busy: bool = False

    def dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "created_at": self.created_at,
            "user_id": self.user_id,
            "stages": [s.dict() for s in self.stages],
            "artifacts": self.artifacts,
            "content": self.content,
            "options": self.options,
            "error": self.error,
        }


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        # job_id -> list of subscriber queues for SSE streaming
        self._subscribers: dict[str, list[queue.Queue]] = {}
        self._hydrated = False

    def _persist(self, job: Job) -> None:
        """Best-effort durable save of a job snapshot to SQLite."""
        try:
            from . import db

            db.save_job(job.dict())
        except Exception:
            pass

    def hydrate(self) -> None:
        """Load persisted jobs from SQLite into memory (once, at startup)."""
        if self._hydrated:
            return
        self._hydrated = True
        try:
            from . import db

            for snap in db.load_all():
                job = _job_from_snapshot(snap)
                interrupted = job.status == "running"
                if interrupted:
                    job.status = "error"
                    job.error = "Interrupted by server restart"
                for stage in job.stages:
                    if stage.status == StageStatus.RUNNING:
                        stage.status = StageStatus.ERROR
                        stage.detail = "Interrupted by server restart"
                with self._lock:
                    if job.id not in self._jobs:
                        self._jobs[job.id] = job
                        self._subscribers.setdefault(job.id, [])
                if interrupted:
                    self._persist(job)
        except Exception:
            pass

    def list_jobs(self, *, user_id: str | None = None, admin: bool = False) -> list[dict]:
        """History rows (newest first) for the session tabs + Sessions gallery."""
        with self._lock:
            jobs = sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)
            if not admin and user_id is not None:
                jobs = [j for j in jobs if j.user_id == user_id]
            rows = []
            for j in jobs:
                arts = j.artifacts or {}
                shots = arts.get("pages_shots") or []
                preview = (
                    arts.get("thumbnail")
                    or (shots[0] if shots else None)
                    or (arts.get("pages") or [None])[0]
                )
                if not preview:
                    # Runs that skip page renders still keep cover.png in the job folder.
                    # Check paths directly: store lookups would re-enter the lock held here.
                    try:
                        from .config import WORKSPACE_DIR

                        slug = str((j.options or {}).get("folder_slug") or "").strip()
                        for folder in ([slug] if slug else []) + [j.id]:
                            if (WORKSPACE_DIR / folder / "cover.png").is_file():
                                preview = f"/files/{j.id}/cover.png"
                                break
                    except Exception:
                        preview = None
                rows.append({
                    "id": j.id,
                    "filename": j.filename,
                    "status": j.status,
                    "created_at": j.created_at,
                    "title": (
                        j.content.get("slide_title")
                        or (j.options or {}).get("automation_title")
                        or j.filename
                    ),
                    "slides": len(j.content.get("slides") or []),
                    "video_format": (j.options or {}).get("video_format"),
                    "duration": (j.options or {}).get("target_duration"),
                    "preview": preview,
                    "video": arts.get("video_final"),
                    "automation_paper_id": (j.options or {}).get("automation_paper_id") or "",
                    "automation_kind": (j.options or {}).get("automation_kind") or "",
                    "automation_folder": (j.options or {}).get("automation_folder") or "",
                    "automation_title": (j.options or {}).get("automation_title") or "",
                    "folder_slug": (j.options or {}).get("folder_slug") or "",
                    "source_pdf": (
                        (j.options or {}).get("source_pdf")
                        or (j.filename if str(j.filename or "").lower().endswith(".pdf") else "")
                        or ""
                    ),
                    "pdf_sha256": (j.options or {}).get("pdf_sha256") or "",
                })
            return rows

    def find_automation_duplicate(
        self,
        *,
        paper_id: str = "",
        video_format: str = "",
        kind: str = "",
        pdf_sha256: str = "",
    ) -> Optional[Job]:
        """Return an existing automation job for the same paper + format/kind.

        Used to prevent History spam when the same PDF is rendered again.
        Prefers completed jobs with a final video; also blocks while a twin is running.
        """
        paper_id = (paper_id or "").strip()
        video_format = (video_format or "").strip().lower()
        kind = (kind or "").strip().lower()
        pdf_sha256 = (pdf_sha256 or "").strip().lower()
        if not paper_id and not pdf_sha256:
            return None

        def _match(j: Job) -> bool:
            opts = j.options or {}
            if opts.get("user_id") == "" and j.user_id not in ("", "system"):
                # Prefer automation / system jobs; still allow match on meta.
                pass
            pid = str(opts.get("automation_paper_id") or "").strip()
            sha = str(opts.get("pdf_sha256") or "").strip().lower()
            fmt = str(opts.get("video_format") or "").strip().lower()
            k = str(opts.get("automation_kind") or "").strip().lower()
            id_ok = bool(paper_id and pid and pid == paper_id)
            sha_ok = bool(pdf_sha256 and sha and sha == pdf_sha256)
            if not (id_ok or sha_ok):
                return False
            if kind and k and k != kind:
                return False
            if video_format and fmt and fmt != video_format:
                return False
            # If kind/format both missing on the stored job, still match on paper id.
            return True

        with self._lock:
            candidates = [j for j in self._jobs.values() if _match(j)]
        if not candidates:
            return None
        # Prefer running (block duplicate start), then completed with video, then newest.
        running = [j for j in candidates if j.status == "running" or j.busy]
        if running:
            return sorted(running, key=lambda j: j.created_at, reverse=True)[0]
        done = [
            j for j in candidates
            if j.status in ("done", "completed")
            or (j.artifacts or {}).get("video_final")
        ]
        # Status in this codebase is often "done" — check both
        pool = done or candidates
        return sorted(pool, key=lambda j: j.created_at, reverse=True)[0]

    # --- lifecycle ---
    def create(self, filename: str, options: dict | None = None, user_id: str = "") -> Job:
        job_id = uuid.uuid4().hex[:12]
        stages = [Stage(key=k, label=l) for k, l in STAGE_ORDER]
        job = Job(id=job_id, filename=filename, stages=stages, options=options or {}, user_id=user_id)
        with self._lock:
            self._jobs[job_id] = job
            self._subscribers[job_id] = []
        self._persist(job)
        return job

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            return self._jobs.get(job_id)

    def delete(self, job_id: str) -> bool:
        """Remove a job from memory + persistence. Returns True if it existed."""
        with self._lock:
            existed = self._jobs.pop(job_id, None) is not None
            self._subscribers.pop(job_id, None)
        try:
            from . import db

            db.delete_job(job_id)
        except Exception:
            pass
        return existed

    def stage(self, job: Job, key: str) -> Stage:
        for s in job.stages:
            if s.key == key:
                return s
        raise KeyError(key)

    # --- pub/sub for streaming ---
    def subscribe(self, job_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.setdefault(job_id, []).append(q)
        return q

    def unsubscribe(self, job_id: str, q: queue.Queue) -> None:
        with self._lock:
            subs = self._subscribers.get(job_id, [])
            if q in subs:
                subs.remove(q)

    def _publish(self, job: Job) -> None:
        snap = job.dict()
        for q in list(self._subscribers.get(job.id, [])):
            try:
                q.put_nowait(snap)
            except Exception:
                pass
        # Durably persist the latest snapshot so history survives restarts.
        self._persist(job)

    # --- mutations (all publish an update) ---
    def set_stage(
        self,
        job: Job,
        key: str,
        status: StageStatus,
        detail: str = "",
    ) -> None:
        with self._lock:
            s = self.stage(job, key)
            s.status = status
            if detail:
                s.detail = detail
            if status == StageStatus.RUNNING:
                s.started_at = time.time()
                s.ended_at = None
            if status in (StageStatus.DONE, StageStatus.SKIPPED, StageStatus.ERROR):
                s.ended_at = time.time()
        self._publish(job)

    def note(self, job: Job, key: str, detail: str) -> None:
        """Update a stage's detail line without resetting its timer.

        Long stages (voice, capture) call this so the UI shows they are still
        moving. ``set_stage(..., RUNNING)`` would restart ``started_at``.
        """
        with self._lock:
            stage = self.stage(job, key)
            stage.detail = detail
        self._publish(job)

    def reset_stages(self, job: Job, keys: list[str]) -> None:
        with self._lock:
            for s in job.stages:
                if s.key in keys:
                    s.status = StageStatus.PENDING
                    s.detail = ""
                    s.started_at = None
                    s.ended_at = None
        self._publish(job)

    def set_artifact(self, job: Job, key: str, value) -> None:
        with self._lock:
            job.artifacts[key] = value
        self._publish(job)

    def set_content(self, job: Job, key: str, value) -> None:
        with self._lock:
            job.content[key] = value
        self._publish(job)

    def try_acquire(self, job: Job) -> bool:
        """Mark the job busy if it isn't already. Returns False if a run is active."""
        with self._lock:
            if job.busy:
                return False
            job.busy = True
            return True

    def release(self, job: Job) -> None:
        with self._lock:
            job.busy = False

    def set_result(self, job: Job, status: str, error: str | None = None) -> None:
        with self._lock:
            job.status = status
            if error is not None:
                job.error = error
            elif status in ("running", "done"):
                # A fresh run / successful completion clears any stale error so
                # the UI doesn't keep showing an old failure after a re-run.
                job.error = None
        self._publish(job)

    def snapshot(self, job: Job) -> dict:
        with self._lock:
            return job.dict()


def _job_from_snapshot(snap: dict) -> Job:
    """Reconstruct a Job (with stages) from a persisted snapshot dict."""
    stages = []
    by_key = {s.get("key"): s for s in snap.get("stages", [])}
    for k, label in STAGE_ORDER:
        s = by_key.get(k, {})
        try:
            status = StageStatus(s.get("status", "pending"))
        except ValueError:
            status = StageStatus.PENDING
        stages.append(
            Stage(
                key=k,
                label=label,
                status=status,
                detail=s.get("detail", ""),
                started_at=s.get("started_at"),
                ended_at=s.get("ended_at"),
            )
        )
    return Job(
        id=snap["id"],
        filename=snap.get("filename", ""),
        status=snap.get("status", "done"),
        created_at=snap.get("created_at", time.time()),
        user_id=snap.get("user_id", ""),
        stages=stages,
        artifacts=snap.get("artifacts", {}) or {},
        content=snap.get("content", {}) or {},
        options=snap.get("options", {}) or {},
        error=snap.get("error"),
    )


store = JobStore()
