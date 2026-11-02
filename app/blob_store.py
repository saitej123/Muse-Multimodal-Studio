"""Job files stay on local disk under ``workspace/``.

Cloud object storage was removed. ``/files`` reads the workspace copy.
"""
from __future__ import annotations

from pathlib import Path


def bucket_name() -> str:
    return ""


def active() -> bool:
    return False


def upload_one_now(job_id: str, rel: str, path: Path) -> bool:
    del job_id, rel, path
    return False


def sync_workspace(job_id: str, work: Path) -> int:
    del job_id, work
    return 0


def sync_workspace_async(job_id: str, work: Path) -> None:
    del job_id, work


def fetch(job_id: str, rel: str, dest: Path) -> bool:
    del job_id, rel, dest
    return False
