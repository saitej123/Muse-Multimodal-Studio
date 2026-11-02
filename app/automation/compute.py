"""Compute-availability gate so runs only start "if compute is available".

Checks normalized CPU load and, when an NVIDIA GPU is present, free GPU memory.
Falls back gracefully on platforms without loadavg (e.g. bare Windows).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import time


def _normalized_load() -> float | None:
    """1-minute load average divided by CPU count, or None if unavailable."""
    try:
        load1, _, _ = os.getloadavg()  # not on native Windows
    except (OSError, AttributeError):
        return None
    cpus = os.cpu_count() or 1
    return load1 / cpus


def _gpu_free_mb() -> int | None:
    """Max free MiB across NVIDIA GPUs via nvidia-smi, or None if no GPU/tool."""
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            timeout=15, text=True,
        )
        vals = [int(x.strip()) for x in out.splitlines() if x.strip().isdigit()]
        return max(vals) if vals else None
    except Exception:  # noqa: BLE001
        return None


def compute_available(config) -> tuple[bool, str]:
    """Return ``(ok, reason)`` for whether a run may start now."""
    if not config.compute_gate:
        return True, "compute gate disabled"

    load = _normalized_load()
    if load is not None and load > config.max_load:
        return False, f"CPU load {load:.2f} > max {config.max_load:.2f}"

    if config.min_gpu_free_mb > 0:
        free = _gpu_free_mb()
        if free is not None and free < config.min_gpu_free_mb:
            return False, f"GPU free {free}MiB < required {config.min_gpu_free_mb}MiB"

    detail = []
    if load is not None:
        detail.append(f"load={load:.2f}")
    else:
        detail.append("load=n/a")
    return True, ", ".join(detail) or "ok"


def wait_for_compute(config, log) -> bool:
    """Block until compute is available or ``compute_wait_seconds`` elapses.

    Returns True if compute became available, False if we gave up.
    """
    deadline = time.time() + max(0, config.compute_wait_seconds)
    while True:
        ok, reason = compute_available(config)
        if ok:
            log(f"compute available ({reason})")
            return True
        if time.time() >= deadline:
            log(f"giving up waiting for compute: {reason}")
            return False
        log(f"waiting for compute: {reason}")
        time.sleep(min(60, max(5, config.poll_seconds)))
