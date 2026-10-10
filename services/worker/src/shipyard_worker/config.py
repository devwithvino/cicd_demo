"""Runtime and build configuration.

Build metadata (version, commit, build time) is baked into the image as
environment variables at build time. Runtime settings such as the
environment name change per deployment while the image stays identical.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import UTC, datetime


@dataclass(frozen=True)
class Config:
    port: int
    environment: str
    kv_url: str
    key_prefix: str
    repo_url: str
    version: str
    commit: str
    build_time: str
    image_ref: str = ""
    sentry_dsn: str = ""
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @classmethod
    def from_env(cls) -> Config:
        return cls(
            port=int(os.environ.get("PORT", "8081")),
            environment=os.environ.get("APP_ENV", "local"),
            kv_url=os.environ.get("KV_URL", "redis://localhost:6379/0"),
            key_prefix=os.environ.get("KEY_PREFIX", "local:"),
            repo_url=os.environ.get("REPO_URL", "").rstrip("/"),
            version=os.environ.get("APP_VERSION", "dev"),
            commit=os.environ.get("GIT_SHA", "unknown"),
            build_time=os.environ.get("BUILD_TIME", "unknown"),
            image_ref=os.environ.get("IMAGE_REF", ""),
            sentry_dsn=os.environ.get("SENTRY_DSN", ""),
        )

    def version_info(self) -> dict[str, object]:
        """Describe exactly which build is running and where."""
        uptime = datetime.now(UTC) - self.started_at
        info: dict[str, object] = {
            "service": "worker",
            "version": self.version,
            "commit": self.commit,
            "buildTime": self.build_time,
            "environment": self.environment,
            "startedAt": self.started_at.isoformat(timespec="seconds"),
            "uptimeSeconds": int(uptime.total_seconds()),
        }
        if self.image_ref:
            info["imageRef"] = self.image_ref
        if self.repo_url and self.commit != "unknown":
            info["commitUrl"] = f"{self.repo_url}/commit/{self.commit}"
        return info
