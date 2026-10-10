#!/usr/bin/env python3
"""Post deploy smoke test, shared by Render, Kind and local runs.

Checks, in order:
  1. Warm up: every service answers /healthz (free tier instances may need
     about a minute to wake up, so this retries).
  2. Version: every service reports the expected commit, which proves the
     intended build is the one actually serving traffic.
  3. Wiring: the web service reaches the API, and the API reaches the worker.
  4. End to end: a real job is submitted through the web service and must be
     completed by the worker.

Exit code is 0 only when every check passes. A Markdown report is printed
and, with --summary, appended to a file such as $GITHUB_STEP_SUMMARY.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any


def http(method: str, url: str, body: dict[str, Any] | None = None, timeout: int = 20) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read()
            return resp.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as err:
        return err.code, None
    except (urllib.error.URLError, TimeoutError, ConnectionError, json.JSONDecodeError):
        return 0, None


def wait_healthy(name: str, base: str, deadline: float) -> tuple[bool, str]:
    started = time.time()
    while time.time() < deadline:
        code, _ = http("GET", f"{base}/healthz", timeout=30)
        if code == 200:
            return True, f"healthy after {round(time.time() - started)}s"
        time.sleep(5)
    return False, "never became healthy"


class Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, bool, str]] = []

    def add(self, check: str, ok: bool, detail: str) -> bool:
        self.rows.append((check, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {check}: {detail}", flush=True)
        return ok

    @property
    def ok(self) -> bool:
        return all(ok for _, ok, _ in self.rows)

    def markdown(self, title: str) -> str:
        lines = [f"### {title}: {'passed' if self.ok else 'FAILED'}", "", "| Check | Result | Detail |", "|---|---|---|"]
        lines += [f"| {check} | {'pass' if ok else 'FAIL'} | {detail} |" for check, ok, detail in self.rows]
        return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--web", required=True)
    parser.add_argument("--api", required=True)
    parser.add_argument("--worker", required=True)
    parser.add_argument("--expect-sha", default="", help="commit every service must report")
    parser.add_argument("--warmup-timeout", type=int, default=240)
    parser.add_argument("--job-timeout", type=int, default=150)
    parser.add_argument("--title", default="Smoke test")
    parser.add_argument("--summary", default="", help="file to append the Markdown report to")
    args = parser.parse_args()

    services = {"web": args.web.rstrip("/"), "api": args.api.rstrip("/"), "worker": args.worker.rstrip("/")}
    report = Report()

    deadline = time.time() + args.warmup_timeout
    with ThreadPoolExecutor(max_workers=3) as pool:
        warm = {name: pool.submit(wait_healthy, name, url, deadline) for name, url in services.items()}
    for name, future in warm.items():
        ok, detail = future.result()
        report.add(f"{name} health", ok, detail)

    if report.ok:
        for name, url in services.items():
            code, info = http("GET", f"{url}/version")
            commit = (info or {}).get("commit", "unknown")
            version = (info or {}).get("version", "unknown")
            if args.expect_sha:
                report.add(f"{name} version", code == 200 and commit == args.expect_sha,
                           f"{version} at {commit[:7]} (expected {args.expect_sha[:7]})")
            else:
                report.add(f"{name} version", code == 200, f"{version} at {commit[:7]}")

        code, status = http("GET", f"{services['web']}/api/status", timeout=60)
        workers = [s for s in (status or {}).get("services", []) if s.get("name") == "worker"]
        report.add("web to api to worker wiring", code == 200 and bool(workers) and workers[0].get("healthy"),
                   f"HTTP {code}, worker {workers[0].get('state') if workers else 'missing'}")

        code, job = http("POST", f"{services['web']}/api/jobs", {"payload": f"smoke test {int(time.time())}"}, timeout=60)
        if report.add("job accepted", code == 202 and bool(job), f"HTTP {code}"):
            started = time.time()
            final: dict[str, Any] = {}
            while time.time() - started < args.job_timeout:
                _, final = http("GET", f"{services['web']}/api/jobs/{job['id']}")
                if (final or {}).get("status") in ("done", "failed"):
                    break
                time.sleep(2)
            final = final or {}
            report.add("job completed by worker", final.get("status") == "done",
                       f"{final.get('status', 'no answer')} in {round(time.time() - started)}s by {final.get('processedBy', 'nobody')}")

    markdown = report.markdown(args.title)
    if args.summary:
        with open(args.summary, "a", encoding="utf-8") as handle:
            handle.write(markdown + "\n")
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
