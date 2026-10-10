#!/usr/bin/env python3
"""Calculate the next semantic version from conventional commits.

Looks at commits since the latest `vX.Y.Z` tag:
- a `!` after the type, or `BREAKING CHANGE` in the body, bumps major
- `feat` bumps minor
- anything else bumps patch

With no previous tag the first release is 0.1.0. Prints the version
without the `v` prefix, for example `1.4.0`.
"""

from __future__ import annotations

import re
import subprocess
import sys

TAG_PATTERN = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
BREAKING_SUBJECT = re.compile(r"^\w+(\([^)]*\))?!:")
FEAT_SUBJECT = re.compile(r"^feat(\([^)]*\))?:")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def latest_tag() -> tuple[str | None, tuple[int, int, int]]:
    for tag in git("tag", "--list", "v*", "--sort=-v:refname").split():
        match = TAG_PATTERN.match(tag)
        if match:
            major, minor, patch = (int(part) for part in match.groups())
            return tag, (major, minor, patch)
    return None, (0, 0, 0)


def bump_level(messages: list[str]) -> str:
    level = "patch"
    for message in messages:
        subject = message.splitlines()[0] if message else ""
        if BREAKING_SUBJECT.match(subject) or "BREAKING CHANGE" in message:
            return "major"
        if FEAT_SUBJECT.match(subject):
            level = "minor"
    return level


def next_version(current: tuple[int, int, int], level: str, first_release: bool) -> str:
    if first_release:
        return "0.1.0"
    major, minor, patch = current
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> int:
    tag, current = latest_tag()
    span = f"{tag}..HEAD" if tag else "HEAD"
    raw = git("log", span, "--format=%B%x00")
    messages = [m.strip() for m in raw.split("\x00") if m.strip()]
    print(next_version(current, bump_level(messages), first_release=tag is None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
