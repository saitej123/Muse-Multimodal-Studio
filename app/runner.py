"""Bounded background execution for pipeline runs.

FastAPI's ``BackgroundTasks`` run blocking work on the request thread pool and
offer no concurrency control. The pipeline stages here are heavy and blocking
(VLM/LLM calls, Playwright capture, FFmpeg). To handle more load gracefully we:

* run each job on a dedicated thread pool sized to the machine, and
* bound the number of *concurrently executing* jobs with a semaphore so a burst
  of uploads queues instead of thrashing CPU/RAM.

Jobs submitted beyond the concurrency limit wait their turn (status stays
``running`` and the UI keeps streaming), rather than failing.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import BoundedSemaphore
from typing import Callable

from .logging_setup import log


def _default_workers() -> int:
    # Heavy stages are mostly IO/subprocess bound; a few in parallel is plenty.
    try:
        env = int(os.environ.get("MAX_CONCURRENT_JOBS", "0"))
        if env > 0:
            return env
    except ValueError:
        pass
    cpu = os.cpu_count() or 4
    return max(2, min(4, cpu // 2))


_MAX_CONCURRENT = _default_workers()
# Pool is larger than the semaphore so queued jobs hold a thread cheaply while
# waiting; the semaphore is what actually bounds heavy concurrent work.
_executor = ThreadPoolExecutor(
    max_workers=_MAX_CONCURRENT + 4, thread_name_prefix="pipeline"
)
_slots = BoundedSemaphore(_MAX_CONCURRENT)

log.bind(task="runner").info(
    f"job runner ready (max concurrent jobs={_MAX_CONCURRENT})"
)


def submit(fn: Callable, *args, **kwargs) -> None:
    """Schedule ``fn(*args)`` on the pool, gated by the concurrency semaphore."""

    def _wrapped() -> None:
        _slots.acquire()
        try:
            fn(*args, **kwargs)
        except Exception as e:  # never let a pool thread die silently
            log.bind(task="runner").exception(f"job crashed: {e}")
        finally:
            _slots.release()

    _executor.submit(_wrapped)


def stats() -> dict:
    return {
        "max_concurrent": _MAX_CONCURRENT,
        "available_slots": _slots._value,  # best-effort introspection
    }
