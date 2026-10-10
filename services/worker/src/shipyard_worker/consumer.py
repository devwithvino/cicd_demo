"""Queue consumer that takes jobs from Key Value and completes them.

Shares its key layout with the API service:
    {prefix}job:{id}   JSON job document
    {prefix}queue      list of job IDs waiting to be processed
"""

from __future__ import annotations

import json
import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import redis
from prometheus_client import Counter, Histogram

from shipyard_worker import processor

log = logging.getLogger("shipyard.worker")

JOBS_PROCESSED = Counter(
    "shipyard_jobs_processed_total", "Jobs processed by the worker, by outcome.", ["outcome"]
)
JOB_DURATION = Histogram("shipyard_job_duration_seconds", "Time spent processing one job.")

POP_TIMEOUT_SECONDS = 5


def _now() -> str:
    return datetime.now(UTC).isoformat()


class Consumer:
    """Pops job IDs from the queue and writes results back."""

    def __init__(
        self,
        client: redis.Redis,
        prefix: str,
        worker_label: str,
        work: Callable[[str], str] = processor.process,
    ) -> None:
        self.client = client
        self.prefix = prefix
        self.worker_label = worker_label
        self.work = work
        self.stop_event = threading.Event()
        self.last_poll: str | None = None

    def key(self, name: str) -> str:
        return f"{self.prefix}{name}"

    def run_forever(self) -> None:
        log.info("consumer started", extra={"queue": self.key("queue")})
        while not self.stop_event.is_set():
            try:
                self.run_once()
            except redis.RedisError:
                log.exception("key value error, retrying shortly")
                self.stop_event.wait(2)
        log.info("consumer stopped")

    def run_once(self) -> bool:
        """Process at most one job. Returns True when a job was handled."""
        self.last_poll = _now()
        item = self.client.brpop([self.key("queue")], timeout=POP_TIMEOUT_SECONDS)
        if item is None:
            return False
        _, raw_id = item
        job_id = raw_id.decode() if isinstance(raw_id, bytes) else str(raw_id)
        self.handle(job_id)
        return True

    def handle(self, job_id: str) -> None:
        job = self._load(job_id)
        if job is None:
            log.warning("job expired before processing", extra={"job_id": job_id})
            JOBS_PROCESSED.labels(outcome="expired").inc()
            return

        job["status"] = "processing"
        job["processedBy"] = self.worker_label
        self._save(job_id, job)

        with JOB_DURATION.time():
            try:
                job["result"] = self.work(str(job.get("payload", "")))
                job["status"] = "done"
                outcome = "done"
            except Exception:
                log.exception("job failed", extra={"job_id": job_id})
                job["status"] = "failed"
                job["result"] = "processing error"
                outcome = "failed"
        job["completedAt"] = _now()
        self._save(job_id, job)
        JOBS_PROCESSED.labels(outcome=outcome).inc()
        log.info("job finished", extra={"job_id": job_id, "outcome": outcome})

    def _load(self, job_id: str) -> dict[str, Any] | None:
        raw = self.client.get(self.key(f"job:{job_id}"))
        if raw is None:
            return None
        data: dict[str, Any] = json.loads(raw)
        return data

    def _save(self, job_id: str, job: dict[str, Any]) -> None:
        # keepttl preserves the expiry the API set when the job was created.
        self.client.set(self.key(f"job:{job_id}"), json.dumps(job), keepttl=True)
