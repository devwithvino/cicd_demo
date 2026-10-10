#!/usr/bin/env python3
"""Enforce the house writing style across the repository.

Rules:
1. The em dash character is banned in every text file.
2. A double hyphen used as punctuation is banned in Markdown prose
   (outside code fences and inline code) and in code comments.
   CLI flags such as `--build` inside code are allowed.

Exit code is 1 when any violation is found, so CI fails the build.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

EM_DASH = chr(0x2014)
SKIP_DIRS = {".git", "node_modules", ".terraform", ".venv", "dist", "coverage", "__pycache__"}
TEXT_SUFFIXES = {
    ".md", ".py", ".go", ".ts", ".js", ".mjs", ".css", ".html", ".yml", ".yaml",
    ".tf", ".sh", ".toml", ".json", ".txt", ".cfg", ".ini",
}
COMMENT_PREFIXES = {
    ".py": "#", ".sh": "#", ".yml": "#", ".yaml": "#", ".toml": "#", ".tf": "#",
    ".go": "//", ".ts": "//", ".js": "//", ".mjs": "//",
}

# Exactly two hyphens, not part of a longer run and not an HTML comment marker.
MD_DOUBLE_HYPHEN = re.compile(r"(?<![-<!])--(?![->])")
# In comments only a space separated double hyphen counts as punctuation.
COMMENT_DOUBLE_HYPHEN = re.compile(r"\s--\s")
INLINE_CODE = re.compile(r"`[^`]*`")


def iter_files(root: Path):
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            if not SKIP_DIRS.intersection(path.parts):
                yield path


def check_markdown(lines: list[str]) -> list[tuple[int, str]]:
    problems = []
    in_fence = False
    for number, line in enumerate(lines, start=1):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        prose = INLINE_CODE.sub("", line)
        if MD_DOUBLE_HYPHEN.search(prose):
            problems.append((number, "double hyphen in prose"))
    return problems


def check_comments(lines: list[str], prefix: str) -> list[tuple[int, str]]:
    problems = []
    for number, line in enumerate(lines, start=1):
        index = line.find(prefix)
        if index == -1:
            continue
        comment = INLINE_CODE.sub("", line[index + len(prefix):])
        if COMMENT_DOUBLE_HYPHEN.search(f" {comment} "):
            problems.append((number, "double hyphen in comment"))
    return problems


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    violations = 0
    for path in iter_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = text.splitlines()
        problems = [(n, "em dash") for n, line in enumerate(lines, start=1) if EM_DASH in line]
        if path.suffix == ".md":
            problems += check_markdown(lines)
        elif path.suffix in COMMENT_PREFIXES:
            problems += check_comments(lines, COMMENT_PREFIXES[path.suffix])
        for number, reason in sorted(problems):
            print(f"{path}:{number}: {reason}")
            violations += 1
    if violations:
        print(f"\n{violations} style violation(s). Use commas or periods instead.")
        return 1
    print("Prose lint passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
