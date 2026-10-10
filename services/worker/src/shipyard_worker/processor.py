"""The actual work done for each job.

The workload is intentionally small but visible: it fingerprints and
analyses the submitted text, then pauses briefly so a viewer can watch
the job move from queued to processing to done on the dashboard.
"""

from __future__ import annotations

import hashlib
import time

PROCESSING_DELAY_SECONDS = 1.0


def process(payload: str, delay: float = PROCESSING_DELAY_SECONDS) -> str:
    """Return a short human readable result for a job payload."""
    if delay > 0:
        time.sleep(delay)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]
    words = len(payload.split())
    return f"{words} words, {len(payload)} chars, sha256 {digest}, reversed: {payload[::-1]}"
