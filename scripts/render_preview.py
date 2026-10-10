#!/usr/bin/env python3
"""Pull request preview environments on Render, wired together.

Render's multi service Preview Environments need a paid plan, but single
service previews of image backed services are free. This script creates one
preview per service from the staging services, points them at each other and
at their own Key Value prefix, and deploys the pull request's image digests.

Commands:
  up       Create or update the previews for a pull request and wait until live.
  down     Delete the previews for a pull request.
  janitor  Delete previews whose pull request is no longer open.

Examples:
  render_preview.py up --pr 12 --base api=srv-a,worker=srv-b,web=srv-c \\
      --registry ghcr.io/owner/shipyard --digests '{"api":"sha256:..."}' --out preview.json
  render_preview.py down --pr 12
  render_preview.py janitor --keep 12,15

Previews are named shipyard-<service>-pr-<number>. The Render API key is read
from RENDER_API_KEY.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from render_deploy import RenderError, deploy_one, log, parse_services, request

PREVIEW_NAME = re.compile(r"^shipyard-(api|worker|web)-pr-(\d+)$")


def preview_name(service: str, pr: int) -> str:
    return f"shipyard-{service}-pr-{pr}"


def list_previews() -> list[dict[str, Any]]:
    """Every Shipyard preview service in the workspace."""
    found: list[dict[str, Any]] = []
    cursor = ""
    while True:
        page = request("GET", f"/services?includePreviews=true&limit=100{'&cursor=' + cursor if cursor else ''}") or []
        for item in page:
            service = item.get("service", item)
            if PREVIEW_NAME.match(service.get("name", "")):
                found.append(service)
        if len(page) < 100:
            return found
        cursor = page[-1].get("cursor", "")
        if not cursor:
            return found


def find_preview(name: str) -> dict[str, Any] | None:
    for item in request("GET", f"/services?name={name}&includePreviews=true&limit=20") or []:
        service = item.get("service", item)
        if service.get("name") == name:
            return dict(service)
    return None


def ensure_preview(service: str, base_id: str, pr: int, image_ref: str) -> dict[str, str]:
    """Return the preview's id and URL, creating the preview when it is missing."""
    name = preview_name(service, pr)
    existing = find_preview(name)
    if existing:
        log(f"{service}: reusing preview {existing['id']}")
        return {"id": existing["id"], "url": existing["serviceDetails"]["url"]}
    created = request("POST", f"/services/{base_id}/preview", {"imagePath": image_ref, "name": name, "plan": "free"})
    svc = created["service"]
    log(f"{service}: created preview {svc['id']}")
    return {"id": svc["id"], "url": svc["serviceDetails"]["url"]}


def env_vars(service_id: str) -> dict[str, str]:
    items = request("GET", f"/services/{service_id}/env-vars?limit=100") or []
    return {i["envVar"]["key"]: i["envVar"]["value"] for i in items}


def cmd_up(args: argparse.Namespace) -> int:
    bases = parse_services(args.base)
    digests: dict[str, str] = json.loads(args.digests)
    refs = {svc: f"{args.registry}-{svc}@{digests[svc]}" for svc in bases}

    previews = {svc: ensure_preview(svc, bases[svc], args.pr, refs[svc]) for svc in bases}

    # Wire the previews to each other and isolate their data, starting from
    # the staging configuration so required settings such as KV_URL carry over.
    wiring = {
        "api": {"WORKER_URL": previews["worker"]["url"]},
        "web": {"API_URL": previews["api"]["url"]},
        "worker": {},
    }
    for svc, preview in previews.items():
        env = env_vars(bases[svc])
        env.update({"APP_ENV": f"pr-{args.pr}", "KEY_PREFIX": f"pr-{args.pr}:", "IMAGE_REF": refs[svc]})
        # Previews never report to Sentry, so they can not use up the quota.
        env.pop("SENTRY_DSN", None)
        env.update(wiring.get(svc, {}))
        request("PUT", f"/services/{preview['id']}/env-vars", [{"key": k, "value": v} for k, v in env.items()])
        log(f"{svc}: configured {len(env)} environment variables")

    with ThreadPoolExecutor(max_workers=len(previews)) as pool:
        futures = {svc: pool.submit(deploy_one, svc, p["id"], refs[svc]) for svc, p in previews.items()}
        results = {svc: f.result() for svc, f in futures.items()}

    out = {svc: {**previews[svc], **results[svc], "ref": refs[svc]} for svc in previews}
    with open(args.out, "w", encoding="utf-8") as handle:
        json.dump(out, handle, indent=2)
    log(f"preview record written to {args.out}")
    return 0 if all(r["status"] == "live" for r in results.values()) else 1


def delete_services(services: list[dict[str, Any]]) -> int:
    for service in services:
        request("DELETE", f"/services/{service['id']}")
        log(f"deleted {service['name']} ({service['id']})")
    return len(services)


def cmd_down(args: argparse.Namespace) -> int:
    targets = [p for p in list_previews() if PREVIEW_NAME.match(p["name"]).group(2) == str(args.pr)]  # type: ignore[union-attr]
    count = delete_services(targets)
    log(f"removed {count} preview service(s) for pull request {args.pr}")
    return 0


def cmd_janitor(args: argparse.Namespace) -> int:
    keep = {int(n) for n in args.keep.split(",") if n.strip()}
    orphans = [p for p in list_previews() if int(PREVIEW_NAME.match(p["name"]).group(2)) not in keep]  # type: ignore[union-attr]
    count = delete_services(orphans)
    log(f"janitor removed {count} orphaned preview service(s), kept previews for {sorted(keep) or 'no'} open pull requests")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    up = sub.add_parser("up")
    up.add_argument("--pr", type=int, required=True)
    up.add_argument("--base", required=True, help="service=baseServiceId pairs for api, worker and web")
    up.add_argument("--registry", required=True)
    up.add_argument("--digests", required=True)
    up.add_argument("--out", required=True)

    down = sub.add_parser("down")
    down.add_argument("--pr", type=int, required=True)

    janitor = sub.add_parser("janitor")
    janitor.add_argument("--keep", default="", help="open pull request numbers, comma separated")

    args = parser.parse_args()
    handlers = {"up": cmd_up, "down": cmd_down, "janitor": cmd_janitor}
    try:
        return handlers[args.command](args)
    except RenderError as err:
        log(f"error: {err}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
