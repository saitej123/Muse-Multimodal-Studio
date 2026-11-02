"""Paper → video automation (in-process scheduler + paper fetchers).

* ``engine`` — admin-triggered / scheduled runs using the main pipeline
* ``sources`` — arXiv / Semantic Scholar paper fetchers (stdlib only)
* ``compute`` — CPU/GPU availability gate before starting a run
"""
from .engine import (
    archive_job,
    cancel_run,
    complete_paper,
    delete_job,
    list_incomplete,
    load_history,
    mark_folder_published,
    preview,
    resume,
    skip_paper,
    start_scheduler,
    status,
    trigger,
    upsert_history,
)

__all__ = [
    "archive_job",
    "cancel_run",
    "complete_paper",
    "delete_job",
    "list_incomplete",
    "load_history",
    "mark_folder_published",
    "preview",
    "resume",
    "skip_paper",
    "start_scheduler",
    "status",
    "trigger",
    "upsert_history",
]
