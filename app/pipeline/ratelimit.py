"""One shared pacing and back-off policy for every Muse call.

The API answers a burst with HTTP 429. Slide
text, page reading, voice and thumbnails all hit the same project quota, so they
share one gate here instead of each retrying on its own:

  * ``throttle()``      spaces call starts by a small gap, across all threads.
  * ``note_limit()``    when any call is rate limited, every thread pauses until
                        the delay the API asked for has passed (no stampede).
  * ``is_rate_limited`` recognises a real quota error and not the word "generate".
  * ``backoff_delay``   honours ``retryDelay`` / "retry in Ns", else grows 8s..75s
                        with jitter.
"""
from __future__ import annotations

import random
import re
import threading
import time

_lock = threading.Lock()
_next_start = 0.0      # earliest monotonic time the next call may start
_cooldown_until = 0.0  # all calls wait until this time after a rate-limit hit

# Gap between call starts. Small enough to keep a slide build quick, large
# enough that a fan-out does not land in the same instant.
MIN_GAP = 0.35
MAX_WAIT = 90.0

_LIMIT_RE = re.compile(
    r"(\b429\b|resource[_ ]exhausted|rate[ _-]?limit|rate exceeded|"
    r"quota|too many requests|requests per (minute|day)|try again later)",
    re.I,
)
_DELAY_RES = (
    re.compile(r"retry in\s+([0-9.]+)\s*s", re.I),
    re.compile(r"retry[_ ]?delay['\"]?\s*[:=]\s*['\"]?([0-9.]+)\s*s", re.I),
    re.compile(r"retry-after['\"]?\s*[:=]\s*['\"]?([0-9.]+)", re.I),
)


def is_rate_limited(exc: BaseException | None) -> bool:
    """True for a quota / 429 error. Never true for words like "generate"."""
    if exc is None:
        return False
    code = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if code == 429:
        return True
    return bool(_LIMIT_RE.search(str(exc)))


def _hinted_delay(exc: BaseException | None) -> float | None:
    text = str(exc or "")
    for rx in _DELAY_RES:
        m = rx.search(text)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                return None
    return None


def backoff_delay(exc: BaseException | None, attempt: int, base: float = 1.5) -> float:
    """Seconds to wait before retry ``attempt`` (0-based)."""
    if is_rate_limited(exc):
        hinted = _hinted_delay(exc)
        if hinted is not None:
            return min(MAX_WAIT, hinted + 1.0 + random.uniform(0, 1.5))
        return min(75.0, 8.0 * (2 ** attempt)) + random.uniform(0, 2.0)
    return base * (2 ** attempt) + random.uniform(0, base * 0.5)


def note_limit(delay: float) -> None:
    """Tell every thread to hold off for ``delay`` seconds."""
    global _cooldown_until
    until = time.monotonic() + max(0.0, min(MAX_WAIT, delay))
    with _lock:
        if until > _cooldown_until:
            _cooldown_until = until


def throttle(gap: float | None = None) -> None:
    """Block until this call may start (shared across threads)."""
    global _next_start
    step = MIN_GAP if gap is None else gap
    with _lock:
        now = time.monotonic()
        start = max(now, _next_start, _cooldown_until)
        _next_start = start + step
    wait = start - now
    if wait > 0:
        time.sleep(wait)


def attempts_for(exc: BaseException | None, current: int, floor: int = 6) -> int:
    """Rate limits get more tries than other errors, because waiting fixes them."""
    return max(current, floor) if is_rate_limited(exc) else current
