import json

import fakeredis
import pytest

from shipyard_worker.consumer import Consumer
from shipyard_worker.processor import process


@pytest.fixture
def client() -> fakeredis.FakeRedis:
    return fakeredis.FakeRedis()


def enqueue(client: fakeredis.FakeRedis, job_id: str, payload: str) -> None:
    job = {"id": job_id, "payload": payload, "status": "queued"}
    client.set(f"test:job:{job_id}", json.dumps(job), ex=3600)
    client.lpush("test:queue", job_id)


def load(client: fakeredis.FakeRedis, job_id: str) -> dict[str, object]:
    raw = client.get(f"test:job:{job_id}")
    assert raw is not None
    data: dict[str, object] = json.loads(raw)
    return data


def test_processes_job_and_records_version(client: fakeredis.FakeRedis) -> None:
    enqueue(client, "j1", "hello world")
    consumer = Consumer(client, "test:", "worker 1.2.3", work=lambda p: p.upper())

    assert consumer.run_once() is True

    job = load(client, "j1")
    assert job["status"] == "done"
    assert job["result"] == "HELLO WORLD"
    assert job["processedBy"] == "worker 1.2.3"
    assert "completedAt" in job


def test_keeps_expiry_set_by_api(client: fakeredis.FakeRedis) -> None:
    enqueue(client, "j1", "x")
    Consumer(client, "test:", "worker", work=lambda p: p).run_once()
    assert client.ttl("test:job:j1") > 0


def test_failed_work_marks_job_failed(client: fakeredis.FakeRedis) -> None:
    def boom(_: str) -> str:
        raise ValueError("bad input")

    enqueue(client, "j1", "x")
    Consumer(client, "test:", "worker", work=boom).run_once()
    assert load(client, "j1")["status"] == "failed"


def test_expired_job_is_skipped(client: fakeredis.FakeRedis) -> None:
    client.lpush("test:queue", "gone")
    consumer = Consumer(client, "test:", "worker", work=lambda p: p)
    assert consumer.run_once() is True
    assert client.get("test:job:gone") is None


def test_empty_queue_returns_false(
    client: fakeredis.FakeRedis, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("shipyard_worker.consumer.POP_TIMEOUT_SECONDS", 1)
    consumer = Consumer(client, "test:", "worker")
    assert consumer.run_once() is False
    assert consumer.last_poll is not None


def test_environments_are_isolated_by_prefix(client: fakeredis.FakeRedis) -> None:
    enqueue(client, "j1", "staging job")
    other_env = Consumer(client, "prd:", "worker", work=lambda p: p)
    other_env.handle("j1")
    assert load(client, "j1")["status"] == "queued"


def test_process_result_is_deterministic() -> None:
    result = process("ship it", delay=0)
    assert result.startswith("2 words, 7 chars, sha256 ")
    assert result.endswith("reversed: ti pihs")
