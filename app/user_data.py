"""Per-user data: the saved voice library table.

Narration uses studio neural voices (see ``app/pipeline/tts.py``) — voice
cloning was removed. This module keeps the ``user_voices`` table helpers
(``list_voices`` / ``get_voice`` / ``delete_voice``) so account deletion can
clean up legacy rows and files. The ``save_*`` / ``ensure_*`` / ``resolve_*``
entry points stay as explicit errors so any stale caller fails loudly instead
of silently doing nothing.

Limits: regular users may save up to ``voice_limit_user`` voices; admins up to
``voice_limit_admin`` (both configurable via ``.env``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import WORKSPACE_DIR, get_settings
from .db import _connect, _lock
from .logging_setup import log

VOICES_DIR = WORKSPACE_DIR / "voices"


def _ensure_schema() -> None:
    conn = _connect()
    with _lock:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS user_voices (
                id          TEXT PRIMARY KEY,
                user_id     TEXT NOT NULL,
                name        TEXT NOT NULL,
                kind        TEXT NOT NULL DEFAULT 'clone',
                filepath    TEXT,
                recording_path TEXT,
                cloud_voice_id TEXT,
                style_source  TEXT,
                created_at  REAL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uservoices_user ON user_voices(user_id)"
        )
        # Migrate older DBs that lack recording_path.
        cols = {row[1] for row in conn.execute("PRAGMA table_info(user_voices)")}
        if "recording_path" not in cols:
            conn.execute("ALTER TABLE user_voices ADD COLUMN recording_path TEXT")
        if "cloud_voice_id" not in cols:
            conn.execute("ALTER TABLE user_voices ADD COLUMN cloud_voice_id TEXT")
        if "style_source" not in cols:
            conn.execute("ALTER TABLE user_voices ADD COLUMN style_source TEXT")
        conn.commit()


def voice_limit(role: str) -> int:
    s = get_settings()
    return s.voice_limit_admin if role == "admin" else s.voice_limit_user


def list_voices(user_id: str) -> list[dict]:
    _ensure_schema()
    conn = _connect()
    with _lock:
        rows = conn.execute(
            "SELECT id, name, kind, filepath, recording_path, cloud_voice_id, style_source, created_at "
            "FROM user_voices WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
    out: list[dict] = []
    for row in rows:
        rec = dict(row)
        rec["has_style"] = bool(rec.get("filepath"))
        rec["has_recording"] = bool(rec.get("recording_path"))
        rec["has_cloud_voice"] = bool(rec.get("cloud_voice_id"))
        # Cloning is removed, so legacy rows are never narration-ready.
        rec["ready_for_narration"] = False
        rec["can_auto_clone"] = False
        out.append(rec)
    return out


def count_voices(user_id: str) -> int:
    _ensure_schema()
    conn = _connect()
    with _lock:
        row = conn.execute(
            "SELECT COUNT(*) c FROM user_voices WHERE user_id = ?", (user_id,)
        ).fetchone()
    return int(row["c"] if row else 0)


def get_voice(user_id: str, voice_id: str) -> Optional[dict]:
    _ensure_schema()
    conn = _connect()
    with _lock:
        row = conn.execute(
            "SELECT * FROM user_voices WHERE id = ? AND user_id = ?",
            (voice_id, user_id),
        ).fetchone()
    return dict(row) if row else None


def voice_path(user_id: str, voice_id: str) -> Optional[Path]:
    """Absolute path to the legacy saved voice file for ``voice_id`` (if any)."""
    rec = get_voice(user_id, voice_id)
    if not rec or not rec.get("filepath"):
        return None
    p = Path(rec["filepath"])
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    return p if p.exists() else None


def recording_path(user_id: str, voice_id: str) -> Optional[Path]:
    """Absolute path to the saved reference recording for ``voice_id`` (if any)."""
    rec = get_voice(user_id, voice_id)
    if not rec or not rec.get("recording_path"):
        return None
    p = Path(rec["recording_path"])
    if not p.is_absolute():
        p = WORKSPACE_DIR / p
    return p if p.exists() else None


def save_voice(
    *, user_id: str, role: str, name: str, style_bytes: bytes, kind: str = "clone"
) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def save_voice_recording(
    *, user_id: str, role: str, name: str, audio_bytes: bytes, ext: str = ".webm"
) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def attach_voice_style(
    user_id: str,
    voice_id: str,
    style_bytes: bytes,
    *,
    style_source: str = "upload",
) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def ensure_voice_style(user_id: str, voice_id: str, *, force: bool = False) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def resolve_voice_for_job(user_id: str, voice_id: str, work: Path) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def save_pocket_voice(
    *,
    user_id: str,
    role: str,
    name: str,
    style_bytes: bytes | None = None,
    audio_path: Path | None = None,
) -> dict:
    """Removed: narration uses studio neural voices (see ``pipeline/tts.py``)."""
    raise RuntimeError("Voice cloning was removed. Choose a studio narration voice.")


def delete_voice(user_id: str, voice_id: str) -> bool:
    _ensure_schema()
    rec = get_voice(user_id, voice_id)
    if not rec:
        return False
    fp = rec.get("filepath")
    rp = rec.get("recording_path")
    conn = _connect()
    with _lock:
        conn.execute(
            "DELETE FROM user_voices WHERE id = ? AND user_id = ?",
            (voice_id, user_id),
        )
        conn.commit()
    for rel in (fp, rp):
        if not rel:
            continue
        try:
            p = Path(rel)
            if not p.is_absolute():
                p = WORKSPACE_DIR / p
            if p.exists():
                p.unlink()
        except Exception:  # noqa: BLE001
            pass
    # Remove any sibling artifacts (raw webm, json).
    try:
        user_dir = VOICES_DIR / user_id
        for p in user_dir.glob(f"{voice_id}.*"):
            p.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    log.bind(task="voice").info(f"deleted voice {voice_id} for user {user_id}")
    return True
