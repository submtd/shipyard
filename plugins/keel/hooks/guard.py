#!/usr/bin/env python3
"""PreToolUse entrypoint. Advisory: never crashes the tool call."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keel import ghio, gitio                    # noqa: E402
from keel.actions import classify               # noqa: E402
from keel.config import CONFIG_NAME, ConfigError, load_config  # noqa: E402
from keel.facts import Facts, Tri               # noqa: E402
from keel.render import render                  # noqa: E402
from keel.rules import aggregate, evaluate       # noqa: E402


def gather(action, cwd, cfg, branch):
    """Facts for one action. `branch` is invariant across every action of a
    single command (they all share `cwd`), so callers compute it once and
    pass it in rather than re-deriving it here."""
    changelog_ok = Tri.UNKNOWN
    changelog_present = Tri.UNKNOWN
    if action.kind == "pr-create":
        # Important 5: compare against the PR's ACTUAL base, not always
        # cfg.integration -- a gitflow hotfix/* -> production PR's window
        # must be measured against production, or the comparison is wrong
        # in both directions (misses content that IS new relative to
        # production, and can credit content that only looks new because
        # develop's history is stale).
        changelog_ok = Tri.of(
            gitio.changelog_gained_content(action.base or cfg.integration, cwd=cwd))
        changelog_present = Tri.of(gitio.changelog_present(cwd=cwd))
    # action.repo carries an explicit `--repo`/`-R`. It must reach gh, or
    # a cross-repo command is judged against the LOCAL repo's PR of the
    # same number -- a different PR, so the review and merge-strategy
    # gates return a confident wrong answer instead of an honest unknown.
    pr = (ghio.pr_facts(action.pr_number, cwd=cwd, repo=action.repo)
          if action.kind == "pr-merge" else None)
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
        capability=(ghio.capability(cwd=cwd, repo=action.repo)
                    if action.kind == "pr-merge" else Tri.UNKNOWN),
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
        msg = str(exc)
        sep = "" if msg.endswith((".", "!", "?")) else "."
        print(json.dumps({"systemMessage": f"[keel] {msg}{sep} keel is "
                                           f"inactive until this is fixed."}))
        return 0
    if cfg is None:
        # Absent means one of two very different things, and collapsing them
        # is what made the guard a silent no-op on gitflow's default adoption
        # path: keel:init writes .keel.json on the current branch (normally
        # `main`), keel:start-work then branches from INTEGRATION (`develop`),
        # and the new branch carries no config -- so every rule was skipped,
        # silently, on exactly the branches keel exists to watch.
        #
        # A repo that never adopted keel is genuinely nothing to say. A repo
        # that HAS adopted it, on a branch that lacks the file, is a
        # misconfiguration and must be as loud as a malformed config already
        # is. Unknown (git could not answer) stays silent -- an unknown must
        # never become a warning about a repo that may not use keel at all.
        if gitio.config_ever_committed(cwd=cwd) is True:
            print(json.dumps({"systemMessage":
                              f"[keel] This repo uses keel, but {CONFIG_NAME} is "
                              f"not on this branch, so every check is inactive "
                              f"here. Merge or rebase from the branch that has "
                              f"it (usually your production branch)."}))
        return 0

    # `cwd` is identical for every action of one command, so anything that
    # only depends on `cwd` (the current branch) is computed once here
    # rather than once per action inside gather().
    branch = gitio.current_branch(cwd=cwd)

    # A compound command (`git commit -m x && git push origin main`) can
    # classify into several actions. Evaluate ALL of them -- do not stop at
    # the first non-allow verdict -- then report the single most severe
    # verdict across the whole command, using the same block > warn > allow
    # reduction rules.evaluate() uses within one action. Otherwise an early
    # warn would silently mask a later block, which defeats the point of
    # the hook.
    verdicts = [evaluate(action, gather(action, cwd, cfg, branch), cfg)
                for action in actions]
    verdict = aggregate(verdicts)
    if verdict.decision != "allow":
        print(json.dumps(render(verdict)))
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
