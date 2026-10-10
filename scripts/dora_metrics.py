#!/usr/bin/env python3
"""Compute DORA metrics and deployment history from real pipeline data.

Reads GitHub Actions runs and jobs, the deploy records each deploy uploads,
incident issues and releases, then writes one JSON file for the status page.
Uses only the Python standard library.

DORA metrics (production, over the reporting window):
  Deployment frequency   successful production deploys per week
  Lead time for changes  commit to live in production (median)
  Change failure rate    production deploys that failed or were rolled back
  Time to restore        failure detected to service verified (median)

Deliberate failure demos are shown in the history but excluded from the
change failure rate, because they are drills rather than real changes.

Usage:
  GH_TOKEN=... dora_metrics.py --repo owner/name --config status-site/config.json --out metrics.json
"""

from __future__ import annotations

import argparse
import io
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.request
import zipfile
from datetime import UTC, datetime, timedelta
from typing import Any

API = "https://api.github.com"
DEPLOY_WORKFLOWS = ["deliver.yml", "demo-failure.yml", "rollback.yml", "deploy-manual.yml"]
DEPLOY_JOB = re.compile(r"deploy to (staging|production)$")
BUILD_JOB = re.compile(r"^(Build once|Build broken release) / ")
RESTORE_RE = re.compile(r"Time to restore \| (\d+) seconds")
RUN_RE = re.compile(r"/actions/runs/(\d+)")
ENV_RE = re.compile(r"in \*\*(staging|production)\*\*")
FAILED_RESULTS = {"rolled_back", "failed", "rollback_failed"}


class GitHub:
    def __init__(self, repo: str, token: str) -> None:
        self.repo = repo
        self.token = token

    def _open(self, url: str) -> bytes:
        req = urllib.request.Request(url, headers={
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        })
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            return bytes(resp.read())

    def get(self, path: str) -> Any:
        return json.loads(self._open(f"{API}/repos/{self.repo}{path}"))

    def download(self, url: str) -> bytes:
        return self._open(url)


def parse_time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def seconds_between(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    return max(0, round((end - start).total_seconds()))


def median(values: list[int]) -> int | None:
    return round(statistics.median(values)) if values else None


def deploy_records(gh: GitHub, run_id: int) -> dict[str, dict[str, Any]]:
    """Download deploy-record.json from a run's deploy artifacts, keyed by environment."""
    records: dict[str, dict[str, Any]] = {}
    try:
        artifacts = gh.get(f"/actions/runs/{run_id}/artifacts?per_page=50").get("artifacts", [])
    except urllib.error.HTTPError:
        return records
    for artifact in artifacts:
        if not artifact["name"].startswith("deploy-state-") or artifact.get("expired"):
            continue
        try:
            archive = zipfile.ZipFile(io.BytesIO(gh.download(artifact["archive_download_url"])))
            if "deploy-record.json" in archive.namelist():
                record = json.loads(archive.read("deploy-record.json"))
                records[record["environment"]] = record
        except (urllib.error.HTTPError, zipfile.BadZipFile, KeyError, json.JSONDecodeError):
            continue
    return records


def collect_incidents(gh: GitHub) -> list[dict[str, Any]]:
    issues = gh.get("/issues?labels=incident&state=all&per_page=100")
    incidents = []
    for issue in issues:
        body = issue.get("body") or ""
        restore = RESTORE_RE.search(body)
        run = RUN_RE.search(body)
        env = ENV_RE.search(body)
        incidents.append({
            "number": issue["number"],
            "title": issue["title"],
            "url": issue["html_url"],
            "state": issue["state"],
            "createdAt": issue["created_at"],
            "environment": env.group(1) if env else None,
            "restoreSeconds": int(restore.group(1)) if restore else None,
            "runId": int(run.group(1)) if run else None,
        })
    return incidents


def collect(gh: GitHub, since: datetime) -> dict[str, Any]:
    releases = [
        {"tag": r["tag_name"], "publishedAt": r["published_at"], "url": r["html_url"], "sha": None}
        for r in gh.get("/releases?per_page=100") if not r.get("prerelease")
    ]
    for release in releases:
        try:
            release["sha"] = gh.get(f"/commits/{release['tag']}")["sha"]
        except urllib.error.HTTPError:
            pass
    version_by_sha = {r["sha"]: r["tag"].lstrip("v") for r in releases if r["sha"]}

    incidents = collect_incidents(gh)
    incident_by_run_env = {(i["runId"], i["environment"]): i for i in incidents if i["runId"]}

    deployments: list[dict[str, Any]] = []
    build_seconds: list[int] = []
    for workflow in DEPLOY_WORKFLOWS:
        try:
            runs = gh.get(f"/actions/workflows/{workflow}/runs?per_page=100&status=completed").get("workflow_runs", [])
        except urllib.error.HTTPError:
            continue
        for run in runs:
            created = parse_time(run["created_at"])
            if created is None or created < since:
                continue
            jobs = gh.get(f"/actions/runs/{run['id']}/jobs?per_page=100&filter=all").get("jobs", [])
            builds = [j for j in jobs if BUILD_JOB.match(j["name"]) and j.get("conclusion") == "success"]
            if builds:
                span = seconds_between(min(parse_time(j["started_at"]) for j in builds),
                                       max(parse_time(j["completed_at"]) for j in builds))
                if span:
                    build_seconds.append(span)

            deploy_jobs = [j for j in jobs if DEPLOY_JOB.search(j["name"])]
            records = deploy_records(gh, run["id"]) if deploy_jobs else {}
            for job in deploy_jobs:
                env = DEPLOY_JOB.search(job["name"]).group(1)  # type: ignore[union-attr]
                record = records.get(env, {})
                steps = job.get("steps") or []
                job_created = parse_time(job.get("created_at") or job.get("started_at"))
                first_step = parse_time(steps[0]["started_at"]) if steps else None
                completed = parse_time(job.get("completed_at"))

                if record.get("result"):
                    result = record["result"]
                elif job["conclusion"] == "success":
                    result = "success"
                elif job["conclusion"] in ("failure", "cancelled") and not steps:
                    result = "not_approved"
                elif (run["id"], env) in incident_by_run_env:
                    result = "rolled_back"
                elif job["conclusion"] == "skipped":
                    continue
                else:
                    result = "failed"

                # Rollbacks and manual deploys ship an older release, so the
                # triggering commit is only a safe fallback for build workflows.
                fallback_sha = run["head_sha"] if run["name"] in ("deliver", "demo-failure") else None
                sha = record.get("sha") or fallback_sha
                incident = incident_by_run_env.get((run["id"], env))
                entry = {
                    "environment": env,
                    "workflow": run["name"],
                    "runId": run["id"],
                    "runUrl": run["html_url"],
                    "sha": sha,
                    "version": record.get("version") or (version_by_sha.get(sha, "") if sha else ""),
                    "result": result,
                    "demo": run["name"] == "demo-failure",
                    "startedAt": (first_step or job_created or created).isoformat(),
                    "completedAt": completed.isoformat() if completed else None,
                    "durationSeconds": seconds_between(first_step, completed),
                    "approvalWaitSeconds": seconds_between(job_created, first_step) if env == "production" else None,
                    "restoreSeconds": record.get("restoreSeconds") or (incident or {}).get("restoreSeconds"),
                    "incidentUrl": (incident or {}).get("url"),
                    "leadTimeSeconds": None,
                    "pipelineSeconds": None,
                }
                commit_time = parse_time((run.get("head_commit") or {}).get("timestamp"))
                if env == "production" and result == "success" and run["name"] == "deliver":
                    entry["leadTimeSeconds"] = seconds_between(commit_time, completed)
                    if entry["leadTimeSeconds"] is not None:
                        entry["pipelineSeconds"] = entry["leadTimeSeconds"] - (entry["approvalWaitSeconds"] or 0)
                deployments.append(entry)

    deployments.sort(key=lambda d: d["startedAt"], reverse=True)
    return {"deployments": deployments, "releases": releases, "incidents": incidents, "buildSeconds": build_seconds}


def rate(value: float | None, thresholds: list[tuple[float, str]], fallback: str) -> str:
    if value is None:
        return "no data"
    for limit, label in thresholds:
        if value <= limit:
            return label
    return fallback


def observed_days(data: dict[str, Any], window_days: int, now: datetime) -> float:
    """Days covered by real data: the window, or less when the project is younger."""
    starts = [parse_time(d["startedAt"]) for d in data["deployments"]]
    first = min((s for s in starts if s), default=None)
    if first is None:
        return float(window_days)
    return min(float(window_days), max(1.0, (now - first).total_seconds() / 86400))


def dora(data: dict[str, Any], window_days: float) -> dict[str, Any]:
    prod = [d for d in data["deployments"] if d["environment"] == "production" and d["result"] != "not_approved"]
    real = [d for d in prod if not d["demo"]]
    successes = [d for d in real if d["result"] == "success"]
    failures = [d for d in real if d["result"] in FAILED_RESULTS]
    per_week = len(successes) / (window_days / 7)
    per_day = len(successes) / window_days

    leads = [d["leadTimeSeconds"] for d in successes if d["leadTimeSeconds"] is not None]
    pipelines = [d["pipelineSeconds"] for d in successes if d["pipelineSeconds"] is not None]
    restores = [i["restoreSeconds"] for i in data["incidents"] if i["restoreSeconds"] is not None]
    cfr = (len(failures) / len(real)) if real else None
    lead = median(leads)
    restore = median(restores)

    if per_day >= 1:
        freq_rating = "elite"
    elif per_week >= 1:
        freq_rating = "high"
    elif per_week * 4 >= 1:
        freq_rating = "medium"
    else:
        freq_rating = "low" if successes else "no data"

    return {
        "deploymentFrequency": {"count": len(successes), "perWeek": round(per_week, 1), "rating": freq_rating},
        "leadTime": {
            "medianSeconds": lead,
            "medianPipelineSeconds": median(pipelines),
            "samples": len(leads),
            "rating": rate(lead, [(86400, "elite"), (7 * 86400, "high"), (30 * 86400, "medium")], "low"),
        },
        "changeFailureRate": {
            "rate": round(cfr, 3) if cfr is not None else None,
            "failures": len(failures),
            "attempts": len(real),
            "rating": rate(cfr, [(0.05, "elite"), (0.10, "high"), (0.15, "medium")], "low"),
        },
        "timeToRestore": {
            "medianSeconds": restore,
            "samples": len(restores),
            "rating": rate(restore, [(3600, "elite"), (86400, "high"), (7 * 86400, "medium")], "low"),
        },
        "stoppedBeforeProduction": len([
            d for d in data["deployments"]
            if d["environment"] == "staging" and d["result"] in FAILED_RESULTS and not d["demo"]
        ]),
        "drills": len([d for d in data["deployments"] if d["demo"]]),
    }


def ci_stats(gh: GitHub, since: datetime) -> dict[str, Any]:
    runs = gh.get("/actions/workflows/ci.yml/runs?per_page=100&status=completed").get("workflow_runs", [])
    recent = [r for r in runs if (parse_time(r["created_at"]) or since) >= since]
    passed = [r for r in recent if r["conclusion"] == "success"]
    return {"runs": len(recent), "passRate": round(len(passed) / len(recent), 3) if recent else None}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
    parser.add_argument("--config", default="status-site/config.json")
    parser.add_argument("--out", default="status-site/data/metrics.json")
    parser.add_argument("--window-days", type=int, default=30)
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not token or not args.repo:
        print("GH_TOKEN and --repo (or GITHUB_REPOSITORY) are required", file=sys.stderr)
        return 2

    gh = GitHub(args.repo, token)
    now = datetime.now(UTC)
    since = now - timedelta(days=args.window_days)
    with open(args.config, encoding="utf-8") as handle:
        config = json.load(handle)

    data = collect(gh, since)
    days = observed_days(data, args.window_days, now)
    metrics = {
        "generatedAt": now.isoformat(timespec="seconds"),
        "repository": args.repo,
        "windowDays": args.window_days,
        "observedDays": round(days, 1),
        "config": config,
        "dora": dora(data, days),
        "pipeline": {"medianBuildSeconds": median(data["buildSeconds"]), "builds": len(data["buildSeconds"]),
                     "ci": ci_stats(gh, since)},
        "deployments": data["deployments"][:50],
        "releases": data["releases"][:20],
        "incidents": data["incidents"][:20],
    }
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    d = metrics["dora"]
    print(f"Wrote {args.out}: {len(data['deployments'])} deployments, {len(data['releases'])} releases, "
          f"{len(data['incidents'])} incidents")
    print(f"  deploy frequency {d['deploymentFrequency']}")
    print(f"  lead time        {d['leadTime']}")
    print(f"  change failure   {d['changeFailureRate']}")
    print(f"  time to restore  {d['timeToRestore']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
