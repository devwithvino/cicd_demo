"""Unit tests for next_version.py. Run with: python -m pytest scripts"""

from next_version import bump_level, next_version


def test_feat_bumps_minor() -> None:
    assert bump_level(["fix: a", "feat(api): b"]) == "minor"


def test_fix_and_chore_bump_patch() -> None:
    assert bump_level(["fix: a", "chore: b", "docs: c"]) == "patch"


def test_bang_or_footer_bumps_major() -> None:
    assert bump_level(["feat(api)!: drop v1"]) == "major"
    assert bump_level(["refactor: x\n\nBREAKING CHANGE: removed endpoint"]) == "major"


def test_next_version_math() -> None:
    assert next_version((1, 2, 3), "patch", first_release=False) == "1.2.4"
    assert next_version((1, 2, 3), "minor", first_release=False) == "1.3.0"
    assert next_version((1, 2, 3), "major", first_release=False) == "2.0.0"


def test_first_release_is_0_1_0() -> None:
    assert next_version((0, 0, 0), "major", first_release=True) == "0.1.0"
