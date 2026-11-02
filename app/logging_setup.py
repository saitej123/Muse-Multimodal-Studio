"""Centralized logging via loguru.

Importing :data:`log` anywhere gives a configured logger that writes colorized
output to stderr and rotates a file under ``logs/app.log``. The pipeline uses
this to record *which* backend handled *which* task (e.g. "Muse text",
"Muse vision / muse-wonder-1.0", "studio voice"), so the terminal clearly shows what
ran for every job.
"""
from __future__ import annotations

import sys

from loguru import logger as log

from .config import BASE_DIR

_CONFIGURED = False


def setup_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    log.remove()
    log.add(
        sys.stderr,
        level="INFO",
        colorize=True,
        format=(
            "<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | "
            "<cyan>{extra[task]: <14}</cyan> | <level>{message}</level>"
        ),
        filter=lambda r: r["extra"].setdefault("task", "-") or True,
    )
    log_dir = BASE_DIR / "logs"
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        log.add(
            log_dir / "app.log",
            level="DEBUG",
            rotation="5 MB",
            retention="7 days",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <7} | {extra[task]} | {message}",
            filter=lambda r: r["extra"].setdefault("task", "-") or True,
        )
    except OSError as e:
        log.warning(f"file log disabled ({e})")
    _CONFIGURED = True


setup_logging()

__all__ = ["log", "setup_logging"]
