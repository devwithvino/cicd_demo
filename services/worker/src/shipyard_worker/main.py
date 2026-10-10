"""Entry point: run the queue consumer and the HTTP server together."""

from __future__ import annotations

import json
import logging
import signal
import sys
import threading
from datetime import UTC, datetime
from types import FrameType

import redis

from shipyard_worker.config import Config
from shipyard_worker.consumer import Consumer
from shipyard_worker.http_server import make_server
from shipyard_worker.monitoring import init_sentry, release

_STANDARD_ATTRS = set(vars(logging.LogRecord("", 0, "", 0, "", None, None)))


class JsonFormatter(logging.Formatter):
    """Structured logs, one JSON object per line, matching the other services."""

    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, object] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "msg": record.getMessage(),
            "service": "worker",
        }
        entry.update({k: v for k, v in vars(record).items() if k not in _STANDARD_ATTRS})
        if record.exc_info:
            entry["error"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)


def main() -> None:
    configure_logging()
    log = logging.getLogger("shipyard.worker")
    cfg = Config.from_env()
    if init_sentry(cfg):
        log.info("sentry error reporting enabled", extra={"release": release(cfg)})

    client = redis.Redis.from_url(cfg.kv_url, socket_timeout=10, health_check_interval=30)
    consumer = Consumer(client, cfg.key_prefix, worker_label=f"worker {cfg.version}")

    def is_ready() -> bool:
        try:
            return bool(client.ping())
        except redis.RedisError:
            return False

    def version_info() -> dict[str, object]:
        info = cfg.version_info()
        info["lastPoll"] = consumer.last_poll
        return info

    server = make_server(cfg.port, version_info, is_ready)
    threading.Thread(target=server.serve_forever, name="http", daemon=True).start()
    log.info(
        "worker started",
        extra={"port": cfg.port, "environment": cfg.environment, "version": cfg.version},
    )

    def shutdown(signum: int, _frame: FrameType | None) -> None:
        log.info("shutdown signal received", extra={"signal": signum})
        consumer.stop_event.set()

    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    consumer.run_forever()
    server.shutdown()
    client.close()


if __name__ == "__main__":
    main()
