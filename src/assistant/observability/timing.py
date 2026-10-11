"""Slow-call log: one WARNING line when a block takes SLOW_MS or more.

Only the call's name and duration are logged, never its arguments (they can
hold tokens, chat ids or calendar links). Cloud Logging keeps it, so a slow
reply can be traced to the external call behind it.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterator
from contextlib import contextmanager

log = logging.getLogger(__name__)

SLOW_MS = 800


@contextmanager
def timed(name: str) -> Iterator[None]:
    start = time.monotonic()
    try:
        yield
    finally:
        ms = int((time.monotonic() - start) * 1000)
        if ms >= SLOW_MS:
            log.warning("slow_call name=%s ms=%d", name, ms)
