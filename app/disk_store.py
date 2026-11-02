"""Local persistence only.

Jobs, cost events, and agent memory stay in SQLite under ``workspace/``.
There is no cloud database and no cloud file bucket.
"""
from __future__ import annotations

from typing import Any


def enabled() -> bool:
    return False


def hosted() -> bool:
    return False


def connected() -> bool:
    return False


def store_for(kind: str) -> str:
    del kind
    return "sqlite"


def queue_mirror(snapshot: dict) -> None:
    del snapshot


def mirror_job(snapshot: dict) -> bool:
    del snapshot
    return False


def queue_usage(doc: dict) -> None:
    del doc


def flush_usage() -> int:
    return 0


def query_since(collection: str, field: str, since: float, limit: int = 50000) -> list[dict]:
    del collection, field, since, limit
    return []


def get_job(job_id: str) -> dict[str, Any] | None:
    del job_id
    return None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    del limit
    return []


def load_snapshots(limit: int = 80) -> list[dict[str, Any]]:
    del limit
    return []


def put_doc(collection: str, doc_id: str, data: dict) -> bool:
    del collection, doc_id, data
    return False


def fetch_all(collection: str, limit: int = 1000) -> list[dict]:
    del collection, limit
    return []


def usage_collection() -> str:
    return "usage_events"


def memory_collection() -> str:
    return "agent_memory"


def status() -> dict[str, Any]:
    return {
        "enabled": False,
        "connected": False,
        "hosted": False,
        "mode": "local",
        "backend": "sqlite",
        "project": None,
        "collection": "jobs",
        "usage_collection": usage_collection(),
        "memory_collection": memory_collection(),
        "synced_jobs": 0,
        "synced_usage": 0,
        "pending_usage": 0,
        "stores": {"jobs": "sqlite", "costs": "sqlite", "memory": "sqlite"},
        "storage": "SQLite on this machine",
        "warning": "",
    }
