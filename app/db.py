"""SQLite persistence for job metadata.

Jobs (and their editable content, artifacts, options, and stage progress) are
persisted to a local SQLite database so sessions survive server restarts and can
be listed as history. Large binary artifacts stay on disk under
``workspace/{job_id}/`` - only metadata + relative paths live in the DB.

The whole job is serialized as JSON in a single row (the job dict is already the
snapshot the API/UI consume), which keeps the schema trivial while giving us
durable session history and a fast list view via the indexed columns.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

from .config import BASE_DIR

DB_PATH = BASE_DIR / "workspace" / "sessions.db"

_lock = threading.Lock()
_conn: Optional[sqlite3.Connection] = None


def _connect() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                filename    TEXT,
                status      TEXT,
                created_at  REAL,
                updated_at  REAL,
                data        TEXT
            )
            """
        )
        _conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created ON jobs(created_at)")
        _conn.execute(
            """
            CREATE TABLE IF NOT EXISTS automation_topics (
                id            TEXT PRIMARY KEY,
                title         TEXT NOT NULL,
                blurb         TEXT,
                heat          INTEGER DEFAULT 5,
                status        TEXT NOT NULL DEFAULT 'trending',
                selected      INTEGER NOT NULL DEFAULT 0,
                prepared      INTEGER NOT NULL DEFAULT 0,
                truthfulness  TEXT,
                prep_json     TEXT,
                content_md    TEXT,
                job_id        TEXT,
                folder        TEXT,
                model         TEXT,
                created_at    REAL,
                updated_at    REAL,
                data          TEXT
            )
            """
        )
        _conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_auto_topics_updated "
            "ON automation_topics(updated_at)"
        )
        _conn.commit()
    return _conn


def save_job(snapshot: dict) -> None:
    """Insert or update a job row from its snapshot dict."""
    conn = _connect()
    with _lock:
        conn.execute(
            """
            INSERT INTO jobs (id, filename, status, created_at, updated_at, data)
            VALUES (:id, :filename, :status, :created_at, :updated_at, :data)
            ON CONFLICT(id) DO UPDATE SET
                filename=excluded.filename,
                status=excluded.status,
                updated_at=excluded.updated_at,
                data=excluded.data
            """,
            {
                "id": snapshot["id"],
                "filename": snapshot.get("filename", ""),
                "status": snapshot.get("status", ""),
                "created_at": snapshot.get("created_at", time.time()),
                "updated_at": time.time(),
                "data": json.dumps(snapshot, default=str),
            },
        )
        conn.commit()


def load_all() -> list[dict]:
    """Return all persisted job snapshots, newest first."""
    conn = _connect()
    with _lock:
        rows = conn.execute(
            "SELECT data FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    out: list[dict] = []
    for r in rows:
        try:
            out.append(json.loads(r["data"]))
        except Exception:
            continue
    return out


def list_sessions() -> list[dict]:
    """Lightweight history rows for the session/history tabs."""
    conn = _connect()
    with _lock:
        rows = conn.execute(
            "SELECT id, filename, status, created_at, updated_at "
            "FROM jobs ORDER BY created_at DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_job(job_id: str) -> None:
    conn = _connect()
    with _lock:
        conn.execute("DELETE FROM jobs WHERE id = ?", (job_id,))
        conn.commit()


# ----------------------------------------------------------- automation topics --

def upsert_topic(row: dict) -> dict:
    """Insert or update an automation topic row (selection / prep / queue)."""
    tid = str(row.get("id") or "").strip()
    if not tid:
        raise ValueError("topic id required")
    now = time.time()
    conn = _connect()
    with _lock:
        existing = conn.execute(
            "SELECT created_at, data FROM automation_topics WHERE id = ?", (tid,)
        ).fetchone()
        created = float(existing["created_at"]) if existing else now
        prev_data: dict = {}
        if existing and existing["data"]:
            try:
                prev_data = json.loads(existing["data"])
            except Exception:
                prev_data = {}
        data = {**prev_data, **(row.get("data") or {}), **{
            k: row[k] for k in (
                "title", "blurb", "heat", "status", "truthfulness", "folder",
                "model", "job_id",
            ) if k in row and row[k] is not None
        }}
        conn.execute(
            """
            INSERT INTO automation_topics (
                id, title, blurb, heat, status, selected, prepared,
                truthfulness, prep_json, content_md, job_id, folder, model,
                created_at, updated_at, data
            ) VALUES (
                :id, :title, :blurb, :heat, :status, :selected, :prepared,
                :truthfulness, :prep_json, :content_md, :job_id, :folder, :model,
                :created_at, :updated_at, :data
            )
            ON CONFLICT(id) DO UPDATE SET
                title=CASE
                    WHEN automation_topics.prepared = 1 THEN automation_topics.title
                    ELSE excluded.title
                END,
                blurb=CASE
                    WHEN automation_topics.prepared = 1 THEN automation_topics.blurb
                    ELSE COALESCE(excluded.blurb, automation_topics.blurb)
                END,
                heat=CASE
                    WHEN automation_topics.prepared = 1 THEN automation_topics.heat
                    ELSE excluded.heat
                END,
                status=CASE
                    WHEN automation_topics.prepared = 1
                         AND excluded.status IN ('trending', 'selected')
                    THEN automation_topics.status
                    ELSE excluded.status
                END,
                selected=CASE
                    WHEN excluded.selected = 1 THEN 1
                    ELSE automation_topics.selected
                END,
                prepared=CASE
                    WHEN automation_topics.prepared = 1 THEN 1
                    ELSE excluded.prepared
                END,
                truthfulness=COALESCE(excluded.truthfulness, automation_topics.truthfulness),
                prep_json=COALESCE(excluded.prep_json, automation_topics.prep_json),
                content_md=COALESCE(excluded.content_md, automation_topics.content_md),
                job_id=COALESCE(excluded.job_id, automation_topics.job_id),
                folder=COALESCE(excluded.folder, automation_topics.folder),
                model=COALESCE(excluded.model, automation_topics.model),
                updated_at=excluded.updated_at,
                data=excluded.data
            """,
            {
                "id": tid,
                "title": str(row.get("title") or tid),
                "blurb": str(row.get("blurb") or ""),
                "heat": int(row.get("heat") or 5),
                "status": str(row.get("status") or "trending"),
                "selected": 1 if row.get("selected") else 0,
                "prepared": 1 if row.get("prepared") else 0,
                "truthfulness": row.get("truthfulness") or None,
                "prep_json": (
                    json.dumps(row["prep"]) if isinstance(row.get("prep"), dict)
                    else (row.get("prep_json") or None)
                ),
                "content_md": row.get("content_md") or None,
                "job_id": row.get("job_id") or None,
                "folder": row.get("folder") or None,
                "model": row.get("model") or None,
                "created_at": created,
                "updated_at": now,
                "data": json.dumps(data),
            },
        )
        conn.commit()
    return get_topic(tid) or {}


def get_topic(topic_id: str) -> dict | None:
    conn = _connect()
    with _lock:
        row = conn.execute(
            "SELECT * FROM automation_topics WHERE id = ?", (topic_id,)
        ).fetchone()
    if not row:
        return None
    return _topic_row(row)


def list_topics(*, prepared_only: bool = False, selected_only: bool = False, limit: int = 50) -> list[dict]:
    conn = _connect()
    clauses: list[str] = []
    args: list = []
    if prepared_only:
        clauses.append("prepared = 1")
    if selected_only:
        clauses.append("selected = 1")
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    with _lock:
        rows = conn.execute(
            f"SELECT * FROM automation_topics {where} "
            f"ORDER BY updated_at DESC LIMIT ?",
            (*args, max(1, int(limit))),
        ).fetchall()
    return [_topic_row(r) for r in rows]


def mark_topic_selected(topic_id: str, selected: bool = True) -> dict | None:
    conn = _connect()
    with _lock:
        row = conn.execute(
            "SELECT * FROM automation_topics WHERE id = ?", (topic_id,)
        ).fetchone()
        if not row:
            return None
        status = "selected" if selected else (row["status"] or "trending")
        if selected and row["prepared"]:
            status = "prepared"
        conn.execute(
            "UPDATE automation_topics SET selected=?, status=?, updated_at=? WHERE id=?",
            (1 if selected else 0, status, time.time(), topic_id),
        )
        conn.commit()
    return get_topic(topic_id)


def _topic_row(row: sqlite3.Row) -> dict:
    prep = None
    if row["prep_json"]:
        try:
            prep = json.loads(row["prep_json"])
        except Exception:
            prep = None
    extra = {}
    if row["data"]:
        try:
            extra = json.loads(row["data"])
        except Exception:
            extra = {}
    return {
        "id": row["id"],
        "title": row["title"] or "",
        "blurb": row["blurb"] or "",
        "heat": row["heat"] or 5,
        "status": row["status"] or "trending",
        "selected": bool(row["selected"]),
        "prepared": bool(row["prepared"]),
        "truthfulness": row["truthfulness"] or "",
        "prep": prep,
        "content_md": row["content_md"] or "",
        "job_id": row["job_id"] or "",
        "folder": row["folder"] or "",
        "model": row["model"] or "",
        "created_at": row["created_at"] or 0,
        "updated_at": row["updated_at"] or 0,
        "kind": "topic",
        **{k: v for k, v in extra.items() if k not in {
            "id", "title", "blurb", "heat", "status", "selected", "prepared",
        }},
    }
