import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator

import pytest

from shipyard_worker.config import Config
from shipyard_worker.http_server import make_server


@pytest.fixture
def base_url() -> Iterator[str]:
    cfg = Config(
        port=0,
        environment="test",
        kv_url="redis://unused",
        key_prefix="test:",
        repo_url="https://example.com/repo",
        version="1.2.3",
        commit="deadbeef",
        build_time="2026-01-01T00:00:00Z",
    )
    ready = {"value": True}
    server = make_server(0, cfg.version_info, lambda: ready["value"])
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}"
    server.shutdown()


def get(url: str) -> tuple[int, bytes]:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:  # noqa: S310
            return resp.status, resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.read()


def test_healthz(base_url: str) -> None:
    code, body = get(f"{base_url}/healthz")
    assert code == 200
    assert json.loads(body) == {"status": "ok"}


def test_version_reports_build_and_environment(base_url: str) -> None:
    code, body = get(f"{base_url}/version")
    info = json.loads(body)
    assert code == 200
    assert info["service"] == "worker"
    assert info["version"] == "1.2.3"
    assert info["environment"] == "test"
    assert info["commitUrl"] == "https://example.com/repo/commit/deadbeef"


def test_metrics_exposed(base_url: str) -> None:
    code, body = get(f"{base_url}/metrics")
    assert code == 200
    assert b"shipyard_jobs_processed_total" in body


def test_unknown_path_is_404(base_url: str) -> None:
    code, _ = get(f"{base_url}/nope")
    assert code == 404
