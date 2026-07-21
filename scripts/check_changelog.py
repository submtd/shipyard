#!/usr/bin/env python3
"""CI changelog gate. Self-contained: stdlib only, no keel import, so it runs
in any repo keel:init scaffolds it into.

Fails when a work-branch PR does not add content to CHANGELOG.md's Unreleased
section, measured against the PR base. Mirrors keel's advisory hook: release
and back-merge heads are exempt (except for a fork PR, whose branch NAME
alone must never grant that exemption -- see KEEL_PR_IS_FORK below), and an
indeterminate result never fails.

Usage: check_changelog.py <base-ref> <head-ref>
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

CONFIG_NAME = ".keel.json"
GIT_TIMEOUT = 5.0
_UNRELEASED = re.compile(r"^(#{1,6})\s*\[?unreleased\]?", re.IGNORECASE)
_HEADING = re.compile(r"^(#{1,6})\s")


def _run_git(args):
    try:
        proc = subprocess.run(["git", *args], capture_output=True, text=True,
                              timeout=GIT_TIMEOUT, encoding="utf-8", errors="replace")
    except (OSError, subprocess.SubprocessError):
        return None
    return proc.stdout if proc.returncode == 0 else None


def unreleased_body(text):
    """Return the Unreleased section's body (blank lines stripped), collecting
    nested sub-headings, terminating at the next same-or-shallower heading."""
    lines, depth, collecting, body = text.splitlines(), None, False, []
    for line in lines:
        m = _UNRELEASED.match(line.strip())
        if m and not collecting:
            depth, collecting = len(m.group(1)), True
            continue
        if collecting:
            h = _HEADING.match(line.strip())
            if h and len(h.group(1)) <= depth:
                break
            body.append(line)
    return "\n".join(b for b in body if b.strip())


def gained_content(before, after):
    """True when `after`'s Unreleased section has at least one non-blank line
    the base's didn't have.

    This used to be `before != after`, which made any difference count --
    including a pure deletion. A PR that only *removed* an Unreleased entry
    passed the gate, and the success message told the author their changelog
    had "gained content". Counting lines (rather than comparing sets) keeps
    a reworded entry passing: the rewritten line is one the base didn't
    have, which is a real contribution.
    """
    before_counts = Counter(unreleased_body(before).splitlines())
    after_counts = Counter(unreleased_body(after).splitlines())
    return any(count > before_counts[line] for line, count in after_counts.items())


def _str_or(value, default):
    """Return value if it is a non-empty str, otherwise default. Guards against
    wrong-typed config values (e.g. a prefix given as a number) flowing through
    into string operations like .startswith()."""
    return value if isinstance(value, str) and value else default


def _config_text_at_base(base):
    """The raw .keel.json as it exists on the PR's base ref, or None if the
    base has no config (or git can't be reached).

    This is deliberately NOT the working tree. In CI the working tree is the
    PR's own head checkout, so reading the config from it let a PR turn off
    the gate that reviews it, just by including requireChangelog: false in
    the same branch. The base ref can only be changed by something that has
    already been merged -- i.e. already reviewed.
    """
    for ref in (f"origin/{base}", base):
        text = _run_git(["show", f"{ref}:{CONFIG_NAME}"])
        if text is not None:
            return text
    return None


def load_cfg(root, base=None):
    """Minimal, tolerant .keel.json read. Returns a flat dict of the fields the
    gate needs, with defaults. Never raises on a bad file -- CI should not crash
    on config; it degrades to the defaults.

    When `base` is given, the config is read from that ref and the working
    tree is used only if the base has no config at all -- which means the
    repo isn't keel-managed yet (this is the PR adopting it), and there is
    therefore no already-enabled gate to bypass.
    """
    raw = {}
    text = _config_text_at_base(base) if base is not None else None
    if text is None:
        path = Path(root) / CONFIG_NAME
        if path.is_file():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = None
    if text is not None:
        try:
            raw = json.loads(text) or {}
        except ValueError:
            raw = {}
    if not isinstance(raw, dict):
        raw = {}
    branches = raw.get("branches") if isinstance(raw.get("branches"), dict) else {}
    prefixes = raw.get("prefixes") if isinstance(raw.get("prefixes"), dict) else {}
    t = raw.get("topology")
    topology = t if t in ("gitflow", "trunk") else "gitflow"
    production = _str_or(branches.get("production"), "main")
    integration = production if topology == "trunk" else _str_or(branches.get("integration"), "develop")
    rc = raw.get("requireChangelog", True)
    require_changelog = rc if isinstance(rc, bool) else True
    return {
        "topology": topology,
        "production": production,
        "integration": integration,
        "feature_prefix": _str_or(prefixes.get("feature"), "feature/"),
        "release_prefix": _str_or(prefixes.get("release"), "release/"),
        "hotfix_prefix": _str_or(prefixes.get("hotfix"), "hotfix/"),
        "require_changelog": require_changelog,
    }


def kind_of_branch(name, cfg):
    if name == cfg["production"]:
        return "production"
    if name == cfg["integration"]:
        return "integration"
    if name.startswith(cfg["feature_prefix"]):
        return "feature"
    if name.startswith(cfg["release_prefix"]):
        return "release"
    if name.startswith(cfg["hotfix_prefix"]):
        return "hotfix"
    return "other"


def main(argv):
    if len(argv) != 3:
        print("usage: check_changelog.py <base-ref> <head-ref>", file=sys.stderr)
        return 2
    base, head = argv[1], argv[2]
    cfg = load_cfg(".", base=base)
    if not cfg["require_changelog"]:
        print("changelog check not required by .keel.json")
        return 0

    head_kind = kind_of_branch(head, cfg)
    is_fork = os.environ.get("KEEL_PR_IS_FORK") == "true"
    if is_fork:
        # A fork PR's head branch name is contributor-controlled, and the
        # only exemptions (release / back-merge) are internal same-repo flows
        # a fork can't legitimately perform. So a fork is never exempt by
        # branch name -- it must add a changelog entry like any outside
        # contribution. (GitHub forbids same-repo head==base, so a fork
        # branch named "main"/"develop"/"release/*" was the only way these
        # name-based exemptions were ever reachable in CI.)
        exempt = False
    elif cfg["topology"] == "trunk":
        exempt = head_kind in ("release", "production", "integration")
    else:
        exempt = head_kind not in ("feature", "hotfix")
    if exempt:
        print(f"'{head}' ({head_kind}) is exempt from the changelog gate")
        return 0

    here = Path("CHANGELOG.md")
    if not here.is_file():
        print("::error::CHANGELOG.md does not exist; create one or set "
              "requireChangelog: false in .keel.json")
        return 1

    merge_base = _run_git(["merge-base", f"origin/{base}", "HEAD"])
    if merge_base is None:
        merge_base = _run_git(["merge-base", base, "HEAD"])
    if merge_base is None:
        print(f"::warning::could not determine the merge base with {base}; "
              "skipping (unknown is not a violation)")
        return 0
    merge_base = merge_base.strip()

    before = _run_git(["show", f"{merge_base}:CHANGELOG.md"])
    if before is None:
        print(f"::warning::could not read CHANGELOG.md at {merge_base}; "
              "skipping (unknown is not a violation)")
        return 0
    if gained_content(before, here.read_text(encoding="utf-8", errors="replace")):
        print("CHANGELOG.md Unreleased section gained content — ok")
        return 0
    print("::error::the Unreleased section of CHANGELOG.md gained no content "
          f"on this branch. Add an entry before merging into {base}.")
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
