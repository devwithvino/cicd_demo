#!/usr/bin/env python3
"""Sentry from the pipeline: releases, deploy markers, a post deploy gate
and a digest of new issues for Slack. Uses only the standard library.

Commands:
  check       Confirm the token can read the organization and its issues.
  release     Create the release shipyard@VERSION (idempotent).
  deploy      Record a deploy of the release to an environment.
  new-issues  Count issues first seen in this release and environment within
              the last N minutes. Exit 1 when there are any (the gate).
  digest      New issues in the given environments since a timestamp, as JSON.

Settings come from the environment: SENTRY_AUTH_TOKEN, SENTRY_ORG,
SENTRY_PROJECT and SENTRY_DSN (used to find the data region). SENTRY_URL
overrides the API host. Every command is a no op, exiting 0, when Sentry
is not configured.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


class SentryError(RuntimeError):
    pass


def api_base() -> str:
    """Sentry Cloud keeps data per region; the DSN host names the region."""
    if os.environ.get("SENTRY_URL"):
        return os.environ["SENTRY_URL"].rstrip("/")
    host = urllib.parse.urlparse(os.environ.get("SENTRY_DSN", "")).hostname or ""
    for region in ("de", "us"):
        if f".ingest.{region}.sentry.io" in host:
            return f"https://{region}.sentry.io"
    return "https://sentry.io"


def configured() -> bool:
    return all(os.environ.get(k) for k in ("SENTRY_AUTH_TOKEN", "SENTRY_ORG", "SENTRY_PROJECT"))


def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    req = urllib.request.Request(
        f"{api_base()}/api/0{path}",
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Authorization": f"Bearer {os.environ['SENTRY_AUTH_TOKEN']}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
            raw = resp.read()
            return json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        detail = err.read().decode(errors="replace")[:300]
        raise SentryError(f"{method} {path} failed with HTTP {err.code}: {detail}") from err


def org() -> str:
    return os.environ["SENTRY_ORG"]


def project() -> str:
    return os.environ["SENTRY_PROJECT"]


def release_name(version: str) -> str:
    return f"shipyard@{version}"


def issues(query: str, limit: int = 25) -> list[dict[str, Any]]:
    params = urllib.parse.urlencode({"query": query, "limit": limit, "statsPeriod": "24h"})
    result = request("GET", f"/projects/{org()}/{project()}/issues/?{params}")
    return list(result or [])


def summarise(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": issue.get("title", ""),
        "culprit": issue.get("culprit", ""),
        "count": issue.get("count", ""),
        "level": issue.get("level", ""),
        "firstSeen": issue.get("firstSeen", ""),
        "release": (issue.get("firstRelease") or {}).get("version", ""),
        "link": issue.get("permalink", ""),
    }


def cmd_check(_: argparse.Namespace) -> int:
    request("GET", f"/organizations/{org()}/")
    issues("is:unresolved", limit=1)
    print(f"Sentry access works: organization {org()}, project {project()}, API {api_base()}")
    return 0


def cmd_release(args: argparse.Namespace) -> int:
    body = {"version": release_name(args.version), "projects": [project()]}
    if args.commit:
        body["ref"] = args.commit
    try:
        request("POST", f"/organizations/{org()}/releases/", body)
        print(f"created release {release_name(args.version)}")
    except SentryError as err:
        # An existing release is fine: the same build is promoted through
        # several environments.
        if "HTTP 208" in str(err) or "already exists" in str(err).lower():
            print(f"release {release_name(args.version)} already exists")
        else:
            raise
    return 0


def cmd_deploy(args: argparse.Namespace) -> int:
    version = urllib.parse.quote(release_name(args.version), safe="")
    request("POST", f"/organizations/{org()}/releases/{version}/deploys/", {"environment": args.environment})
    print(f"recorded deploy of {release_name(args.version)} to {args.environment}")
    return 0


def cmd_new_issues(args: argparse.Namespace) -> int:
    query = (
        f'is:unresolved release:"{release_name(args.version)}" '
        f"environment:{args.environment} firstSeen:-{args.minutes}m"
    )
    found = [summarise(i) for i in issues(query)]
    result = {"count": len(found), "issues": found}
    if args.out:
        with open(args.out, "w", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2)
    print(f"{len(found)} new Sentry issue(s) in {release_name(args.version)} on {args.environment}")
    for issue in found:
        print(f"  {issue['title']} ({issue['count']} events) {issue['link']}")
    return 1 if found else 0


def cmd_digest(args: argparse.Namespace) -> int:
    found: list[dict[str, Any]] = []
    for environment in [e for e in args.environments.split(",") if e]:
        for issue in issues(f"is:unresolved environment:{environment} firstSeen:>={args.since}"):
            found.append({"environment": environment, **summarise(issue)})
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump({"count": len(found), "issues": found}, handle, indent=2)
    print(f"{len(found)} new Sentry issue(s) since {args.since}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    rel = sub.add_parser("release")
    rel.add_argument("--version", required=True)
    rel.add_argument("--commit", default="")
    dep = sub.add_parser("deploy")
    dep.add_argument("--version", required=True)
    dep.add_argument("--environment", required=True)
    new = sub.add_parser("new-issues")
    new.add_argument("--version", required=True)
    new.add_argument("--environment", required=True)
    new.add_argument("--minutes", type=int, default=15)
    new.add_argument("--out", default="")
    dig = sub.add_parser("digest")
    dig.add_argument("--since", required=True, help="ISO 8601 timestamp, for example 2026-10-10T08:00:00")
    dig.add_argument("--environments", default="staging,production")
    dig.add_argument("--out", required=True)
    args = parser.parse_args()

    if not configured():
        print("Sentry is not configured (SENTRY_AUTH_TOKEN, SENTRY_ORG, SENTRY_PROJECT), skipping.")
        if getattr(args, "out", ""):
            with open(args.out, "w", encoding="utf-8") as handle:
                json.dump({"count": 0, "issues": [], "skipped": True}, handle)
        return 0

    handlers = {
        "check": cmd_check,
        "release": cmd_release,
        "deploy": cmd_deploy,
        "new-issues": cmd_new_issues,
        "digest": cmd_digest,
    }
    try:
        return handlers[args.command](args)
    except SentryError as err:
        print(f"error: {err}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
