#!/usr/bin/env python3
"""CI mirror of keel's changelog rule, built on keel's own parser.

Fails when a work-branch PR does not add content to CHANGELOG.md's Unreleased
section, measured against the PR base. Matches the advisory hook's policy:
release and back-merge heads are exempt, and an indeterminate result never
fails (unknown is not a violation) -- the hook warns there; CI stays quiet.

Usage: check_changelog.py <base-ref> <head-ref>
The refs are branch names; the base is compared as origin/<base>.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "plugins" / "keel"))

from keel.config import ConfigError, load_config  # noqa: E402
from keel.gitio import changelog_gained_content, changelog_present  # noqa: E402
from keel.rules import _kind_of_branch  # noqa: E402


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: check_changelog.py <base-ref> <head-ref>", file=sys.stderr)
        return 2
    base, head = sys.argv[1], sys.argv[2]

    root = Path(".")
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(f"::warning::keel config invalid, skipping changelog check: {exc}")
        return 0
    if cfg is None or not cfg.require_changelog:
        print("changelog check not required by .keel.json")
        return 0

    head_kind = _kind_of_branch(head, cfg)
    # Mirror the hook's exemptions: release/back-merge PRs carry no new
    # user-facing change of their own.
    if cfg.is_trunk:
        exempt = head_kind in ("release", "production", "integration")
    else:
        exempt = head_kind not in ("feature", "hotfix")
    if exempt:
        print(f"'{head}' ({head_kind}) is exempt from the changelog gate")
        return 0

    if changelog_present(cwd=".") is False:
        print("::error::CHANGELOG.md does not exist; create one or set "
              "requireChangelog: false in .keel.json")
        return 1

    gained = changelog_gained_content(f"origin/{base}", cwd=".")
    if gained is None:
        print(f"::warning::could not compare CHANGELOG.md against origin/{base}; "
              "skipping (unknown is not a violation)")
        return 0
    if not gained:
        print("::error::the Unreleased section of CHANGELOG.md gained no content "
              f"on this branch. Add an entry before merging into {base}.")
        return 1

    print("CHANGELOG.md Unreleased section gained content — ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
