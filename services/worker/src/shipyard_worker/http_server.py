"""Small HTTP server for health, version and metrics.

The worker runs as a free web service on Render, which requires it to
answer HTTP. Requests to these endpoints also wake the instance after the
free tier has spun it down.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def make_server(
    port: int,
    version_info: Callable[[], dict[str, object]],
    is_ready: Callable[[], bool],
) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        server_version = "shipyard-worker"

        def do_GET(self) -> None:
            if self.path == "/healthz":
                self._json(200, {"status": "ok"})
            elif self.path == "/readyz":
                ready = is_ready()
                self._json(200 if ready else 503, {"status": "ready" if ready else "unavailable"})
            elif self.path == "/version":
                self._json(200, version_info())
            elif self.path == "/metrics":
                self._send(200, generate_latest(), CONTENT_TYPE_LATEST)
            else:
                self._json(404, {"error": "not found"})

        def do_OPTIONS(self) -> None:
            self._send(204, b"", "text/plain")

        def _json(self, code: int, body: dict[str, Any]) -> None:
            self._send(code, json.dumps(body).encode(), "application/json")

        def _send(self, code: int, body: bytes, content_type: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: Any) -> None:
            # Access logs are noisy for health checks, so they are dropped.
            return

    return ThreadingHTTPServer(("0.0.0.0", port), Handler)  # noqa: S104
