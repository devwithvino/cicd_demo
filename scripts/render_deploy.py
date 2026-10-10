#!/usr/bin/env python3
"""Deploy image digests to Render services, and roll them back.

Uses only the Python standard library so it runs on any CI runner.

Commands:
  deploy    Record the image each service runs now, then deploy new digests
            to all services in parallel and wait until they are live.
  rollback  Redeploy the images recorded by a previous deploy.
  current   Print the image each service is running.

Examples:
  render_deploy.py deploy --services api=srv-a,worker=srv-b,web=srv-c \\
      --registry ghcr.io/owner/shipyard --digests '{"api":"sha256:..."}' --state state.json
  render_deploy.py rollback --state state.json

The Render API key is read from the RENDER_API_KEY environment variable.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Any

API = "https://api.render.com/v1"
POLL_SECONDS = 10
TIMEOUT_SECONDS = 600
FAILED = {"build_failed", "update_failed", "pre_deploy_failed", "canceled", "deactivated"}


class RenderError(RuntimeError):
    pass


def request(method: str, path: str, body: dict[str, Any] | None = None) -> Any:
    key = os.environ.get("RENDER_API_KEY")
    if not key:
        raise RenderError("RENDER_API_KEY is not set")
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(5):
        req = urllib.request.Request(
            f"{API}{path}",
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as err:
            if err.code in (429, 500, 502, 503) and attempt < 4:
                time.sleep(2 ** attempt * 2)
                continue
            detail = err.read().decode(errors="replace")[:300]
            raise RenderError(f"{method} {path} failed with HTTP {err.code}: {detail}") from err
    raise RenderError(f"{method} {path} kept failing")


def live_image(service_id: str) -> str | None:
    """Return the image reference of the newest live deploy, if any."""
    deploys = request("GET", f"/services/{service_id}/deploys?limit=20") or []
    for item in deploys:
        deploy = item.get("deploy", item)
        if deploy.get("status") == "live":
            ref = (deploy.get("image") or {}).get("ref")
            if ref:
                return str(ref)
    service = request("GET", f"/services/{service_id}")
    path = (service or {}).get("imagePath")
    return str(path) if path else None


def deploy_one(name: str, service_id: str, image_ref: str, extra_env: dict[str, str] | None = None) -> dict[str, Any]:
    """Deploy one image reference and block until it is live or has failed."""
    started = time.time()
    # Expose the exact image to the app so the dashboard can show it.
    request("PUT", f"/services/{service_id}/env-vars/IMAGE_REF", {"value": image_ref})
    # Runtime settings that belong to the environment, such as SENTRY_DSN.
    for key, value in (extra_env or {}).items():
        request("PUT", f"/services/{service_id}/env-vars/{key}", {"value": value})
    deploy = request("POST", f"/services/{service_id}/deploys", {"imageUrl": image_ref})
    deploy_id = deploy["id"]
    log(f"{name}: deploy {deploy_id} started for {short(image_ref)}")

    status = deploy.get("status", "created")
    while time.time() - started < TIMEOUT_SECONDS:
        if status == "live" or status in FAILED:
            break
        time.sleep(POLL_SECONDS)
        status = request("GET", f"/services/{service_id}/deploys/{deploy_id}")["status"]
        log(f"{name}: {status}")
    else:
        status = "timed_out"

    seconds = round(time.time() - started)
    log(f"{name}: finished as {status} in {seconds}s")
    return {"deployId": deploy_id, "status": status, "seconds": seconds}


def parse_services(value: str) -> dict[str, str]:
    pairs = (item.split("=", 1) for item in value.split(",") if item.strip())
    return {name.strip(): sid.strip() for name, sid in pairs}


def run_parallel(
    targets: dict[str, tuple[str, str]], extra_env: dict[str, str] | None = None
) -> dict[str, dict[str, Any]]:
    """targets maps service name to (service id, image ref)."""
    with ThreadPoolExecutor(max_workers=len(targets) or 1) as pool:
        futures = {name: pool.submit(deploy_one, name, sid, ref, extra_env) for name, (sid, ref) in targets.items()}
        results: dict[str, dict[str, Any]] = {}
        for name, future in futures.items():
            try:
                results[name] = future.result()
            except RenderError as err:
                log(f"{name}: {err}")
                results[name] = {"status": "error", "error": str(err)}
    return results


def cmd_deploy(args: argparse.Namespace) -> int:
    services = parse_services(args.services)
    digests: dict[str, str] = json.loads(args.digests)
    missing = set(services) - set(digests)
    if missing:
        raise RenderError(f"no digest provided for: {', '.join(sorted(missing))}")

    state: dict[str, Any] = {"services": {}}
    targets: dict[str, tuple[str, str]] = {}
    for name, sid in services.items():
        new_ref = f"{args.registry}-{name}@{digests[name]}"
        state["services"][name] = {"serviceId": sid, "previousRef": live_image(sid), "newRef": new_ref}
        targets[name] = (sid, new_ref)
        log(f"{name}: currently running {short(state['services'][name]['previousRef'])}")

    started = time.time()
    extra_env = dict(pair.split("=", 1) for pair in args.env if "=" in pair and pair.split("=", 1)[1])
    for name, result in run_parallel(targets, extra_env).items():
        state["services"][name].update(result)
    state["seconds"] = round(time.time() - started)
    state["ok"] = all(s["status"] == "live" for s in state["services"].values())
    write_state(args.state, state)
    return 0 if state["ok"] else 1


def cmd_rollback(args: argparse.Namespace) -> int:
    with open(args.state, encoding="utf-8") as handle:
        state = json.load(handle)
    targets = {
        name: (svc["serviceId"], svc["previousRef"])
        for name, svc in state["services"].items()
        if svc.get("previousRef") and svc["previousRef"] != svc.get("newRef")
    }
    if not targets:
        log("nothing to roll back: no previous images recorded")
        return 1
    started = time.time()
    results = run_parallel(targets)
    rollback = {"seconds": round(time.time() - started), "services": results}
    rollback["ok"] = all(r["status"] == "live" for r in results.values())
    state["rollback"] = rollback
    write_state(args.state, state)
    return 0 if rollback["ok"] else 1


def cmd_current(args: argparse.Namespace) -> int:
    for name, sid in parse_services(args.services).items():
        print(f"{name}\t{live_image(sid)}")
    return 0


def write_state(path: str, state: dict[str, Any]) -> None:
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)
    log(f"state written to {path}")


def short(ref: str | None) -> str:
    if not ref:
        return "nothing"
    return ref.split("/")[-1][:40]


def log(message: str) -> None:
    print(message, flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    deploy = sub.add_parser("deploy")
    deploy.add_argument("--services", required=True, help="name=serviceId pairs, comma separated")
    deploy.add_argument("--registry", required=True, help="image prefix, for example ghcr.io/owner/shipyard")
    deploy.add_argument("--digests", required=True, help="JSON map of service name to digest")
    deploy.add_argument("--state", required=True, help="where to write the deploy record")
    deploy.add_argument("--env", action="append", default=[], help="KEY=VALUE to set before deploying, repeatable")

    rollback = sub.add_parser("rollback")
    rollback.add_argument("--state", required=True, help="deploy record written by the deploy command")

    current = sub.add_parser("current")
    current.add_argument("--services", required=True)

    args = parser.parse_args()
    handlers = {"deploy": cmd_deploy, "rollback": cmd_rollback, "current": cmd_current}
    try:
        return handlers[args.command](args)
    except RenderError as err:
        log(f"error: {err}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
