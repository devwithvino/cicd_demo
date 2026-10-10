"""Error reporting to Sentry.

Sentry is switched on only when SENTRY_DSN is set, which the pipeline does
for staging and production. Local runs, Kind and previews send nothing.
The logging integration turns every log.exception and error log in the
worker into a Sentry event, so failures need no extra code.
"""

from __future__ import annotations

import sentry_sdk

from shipyard_worker.config import Config


def release(cfg: Config) -> str:
    """Sentry release name shared by every Shipyard service."""
    return f"shipyard@{cfg.version}"


def init_sentry(cfg: Config) -> bool:
    """Configure Sentry. Returns False, and does nothing, without a DSN."""
    if not cfg.sentry_dsn:
        return False
    sentry_sdk.init(
        dsn=cfg.sentry_dsn,
        environment=cfg.environment,
        release=release(cfg),
        send_default_pii=False,
        traces_sample_rate=0.0,
    )
    sentry_sdk.set_tag("service", "worker")
    sentry_sdk.set_tag("commit", cfg.commit)
    return True
