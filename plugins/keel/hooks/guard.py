#!/usr/bin/env python3
"""PreToolUse entrypoint. Advisory: never crashes the tool call."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keel import ghio, gitio                    # noqa: E402
from keel.actions import classify               # noqa: E402
from keel.config import ConfigError, load_config  # noqa: E402
from keel.facts import Facts, Tri               # noqa: E402
from keel.render import render                  # noqa: E402
from keel.rules import evaluate                 # noqa: E402


def gather(action, cwd, cfg):
    branch = gitio.current_branch(cwd=cwd)
    changelog_ok = Tri.UNKNOWN
    changelog_present = Tri.UNKNOWN
    if action.kind == "pr-create":
        changelog_ok = Tri.of(gitio.changelog_gained_content(cfg.integration, cwd=cwd))
        changelog_present = Tri.of(gitio.changelog_present(cwd=cwd))
    pr = ghio.pr_facts(action.pr_number, cwd=cwd) if action.kind == "pr-merge" else None
    # NB: pr_facts() returns None when `gh` itself failed (unreachable,
    # timeout, not found) -- distinct from a successful call whose PR
    # genuinely has no review yet (which returns a dict with
    # review_state: None). Flattening via `(pr or {}).get(...)` collapses
    # both into pr_review_state=None, which _rule_review would otherwise
    # treat as a confident "no review" and block. This stays safe only
    # because a failed call also leaves pr_base=None, and _rule_review
    # (and _rule_merge_strategy) both warn on an unknown base BEFORE they
    # would reach the review-state check. See test_guard.py's
    # test_failed_gh_call_warns_not_blocks_on_merge, which pins this down.
    return Facts(
        branch=branch,
        capability=ghio.capability(cwd=cwd) if action.kind == "pr-merge" else Tri.UNKNOWN,
        pr_base=(pr or {}).get("base"),
        pr_head=(pr or {}).get("head"),
        pr_is_fork=(pr or {}).get("is_fork", Tri.UNKNOWN),
        pr_review_state=(pr or {}).get("review_state"),
        changelog_ok=changelog_ok,
        changelog_present=changelog_present,
    )


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if event.get("tool_name") != "Bash":
        return 0

    command = (event.get("tool_input") or {}).get("command", "")
    actions = classify(command)
    if not actions:
        return 0

    cwd = gitio.target_cwd(command, event.get("cwd") or os.getcwd())
    root = gitio.repo_root(cwd=cwd)
    if root is None:
        return 0  # not a git repo; nothing to say

    try:
        cfg = load_config(root)
    except ConfigError as exc:
        # Loud, per the spec: a broken config must never silently disable keel.
        print(json.dumps({"systemMessage": f"[keel] {exc} keel is inactive "
                                           f"until this is fixed."}))
        return 0
    if cfg is None:
        return 0  # repo is not keel-managed

    for action in actions:
        verdict = evaluate(action, gather(action, cwd, cfg), cfg)
        if verdict.decision != "allow":
            print(json.dumps(render(verdict)))
            return 0
    return 0


def run():
    """Wrap main() so no exception -- expected or not -- can ever propagate
    and abort the user's Bash tool call. This hook is advisory only."""
    try:
        return main()
    except Exception as exc:  # noqa: BLE001 - advisory hook must never break Bash
        print(json.dumps({"systemMessage": f"[keel] internal error, allowing: {exc}"}))
        return 0


if __name__ == "__main__":
    sys.exit(run())
