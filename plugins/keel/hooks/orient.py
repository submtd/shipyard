#!/usr/bin/env python3
"""SessionStart entrypoint: describe the repo's lifecycle in one short block.

Only registered for the `startup` matcher (see hooks.json) -- orientation
should appear once per session, not be re-injected on every resume/compact.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keel import gitio                            # noqa: E402
from keel.config import ConfigError, load_config  # noqa: E402
from keel.render import _sentence                 # noqa: E402

SKILLS = (
    "keel:start-work", "keel:finish-work", "keel:respond-to-review",
    "keel:sync", "keel:review", "keel:land", "keel:release", "keel:ship",
    "keel:protect", "keel:doctor",
)


def orientation(cfg, branch):
    if cfg.is_trunk:
        flow = f"{cfg.feature_prefix}* -> PR -> {cfg.production} (tagged to release)"
    else:
        flow = (f"{cfg.feature_prefix}* -> PR -> {cfg.integration} -> "
                f"{cfg.release_prefix}* -> PR -> {cfg.production}")
    protected = sorted({cfg.production, cfg.integration})
    on_protected = branch in protected
    lines = [
        "This repository uses keel for its git lifecycle.",
        "",
        f"- Topology: {cfg.topology} ({flow})",
        f"- Protected: {', '.join(protected)} "
        f"(changes reach {'it' if len(protected) == 1 else 'them'} via PR)",
        f"- Review policy: {cfg.review_policy} "
        f"(CHANGES_REQUESTED always blocks a merge, regardless of policy)",
        f"- Current branch: {branch or 'unknown (detached HEAD?)'}",
    ]
    if on_protected:
        lines += ["", f"You are on protected branch '{branch}'. Start work with "
                      f"the keel:start-work skill before making changes."]
    lines += ["", f"Skills: {', '.join(SKILLS)}.",
              "",
              "keel's hook is advisory: it catches mistakes early, but GitHub "
              "branch protection is the real boundary (see keel:protect)."]
    return "\n".join(lines)


def main():
    root = gitio.repo_root()
    if root is None:
        return 0  # not a git repo; nothing to say
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(json.dumps({
            "additionalContext": "[keel] {} keel is inactive.".format(
                _sentence(str(exc)))
        }))
        return 0
    if cfg is None:
        return 0  # repo is not keel-managed
    print(json.dumps({"additionalContext": orientation(cfg, gitio.current_branch())}))
    return 0


def run():
    """Wrap main() so no exception -- expected or not -- can ever propagate
    and break session startup. This hook is advisory only."""
    try:
        return main()
    except Exception:  # noqa: BLE001 - advisory hook must never break startup
        return 0


if __name__ == "__main__":
    sys.exit(run())
