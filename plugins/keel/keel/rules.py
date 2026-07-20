"""The rule engine. Pure: no I/O, no subprocess, no globals.

Rules key on (action, base, head, headIsFork, capability). There is no role.

Fail policy, applied uniformly: a fact that is Tri.UNKNOWN produces a 'warn',
never a 'block'. The hook is advisory; blocking on ignorance costs more trust
than it buys.
"""
from dataclasses import dataclass

from .facts import Tri


@dataclass(frozen=True)
class Verdict:
    decision: str  # "allow" | "warn" | "block"
    rule: str = ""
    message: str = ""


ALLOW = Verdict("allow")


def _block(rule, message):
    return Verdict("block", rule, message)


def _warn(rule, message):
    return Verdict("warn", rule, message)


def _protected(cfg):
    return {cfg.production, cfg.integration}


def _kind_of_branch(name, cfg):
    if name is None:
        return None
    # Exact names are checked before prefixes: a production/integration branch
    # name that happens to also match a configured prefix (e.g.
    # production="main-line", feature_prefix="main-") must still classify as
    # production/integration, not feature/release/hotfix.
    if name == cfg.production:
        return "production"
    if name == cfg.integration:
        return "integration"
    if name.startswith(cfg.feature_prefix):
        return "feature"
    if name.startswith(cfg.release_prefix):
        return "release"
    if name.startswith(cfg.hotfix_prefix):
        return "hotfix"
    return "other"


# --- Rule 1: protected-branch writes -------------------------------------

def _rule_protected_write(action, facts, cfg):
    protected = _protected(cfg)

    if action.kind == "commit":
        if facts.branch is None:
            return _warn("protected-write",
                         "Could not determine the current branch; skipping the "
                         "protected-branch check.")
        if facts.branch in protected:
            return _block("protected-write",
                          f"'{facts.branch}' is protected. Start a branch with "
                          f"keel:start-work; changes reach it via PR.")
        return ALLOW

    if action.kind == "push":
        if not action.refs:
            # 'git push' with no refspec pushes the current branch.
            if facts.branch is None:
                return _warn("protected-write",
                             "Could not determine what this push targets.")
            targets = [facts.branch]
        else:
            # Tag refs are exempt -- but only the tag refs themselves. A branch
            # ref in the same command is still checked.
            targets = [r.dst for r in action.refs if not r.is_tag]
        hits = [t for t in targets if t in protected]
        if hits:
            return _block("protected-write",
                          f"This pushes directly to protected branch "
                          f"'{hits[0]}'. Open a PR instead (keel:finish-work).")
    return ALLOW


# --- Rule 2: valid PR edges ----------------------------------------------

def _valid_edge(head_kind, base, cfg):
    if cfg.is_trunk:
        return (head_kind in ("feature", "hotfix") and base == cfg.production)
    return (
        (head_kind == "feature" and base == cfg.integration)
        or (head_kind == "release" and base == cfg.production)
        or (head_kind == "hotfix" and base == cfg.production)
        or (head_kind == "production" and base == cfg.integration)  # back-merge
    )


def _rule_pr_edge(action, facts, cfg):
    head = action.head or facts.branch
    head_kind = _kind_of_branch(head, cfg)
    if action.base is None or head_kind is None:
        return _warn("pr-edge", "Could not determine this PR's base or head branch.")
    if not _valid_edge(head_kind, action.base, cfg):
        if cfg.is_trunk:
            expected = f"'{cfg.production}'"
        else:
            expected = (f"'{cfg.integration}' for feature work, "
                        f"'{cfg.production}' for releases and hotfixes")
        return _block("pr-edge",
                      f"'{head}' should not target '{action.base}'. "
                      f"Expected {expected}.")
    return ALLOW


# --- Rule 3: changelog ----------------------------------------------------

def _rule_changelog(action, facts, cfg):
    if not cfg.require_changelog:
        return ALLOW
    head_kind = _kind_of_branch(action.head or facts.branch, cfg)
    if head_kind is None:
        return _warn("changelog",
                     "Could not determine the head branch's kind, so the "
                     "CHANGELOG check was skipped.")
    # Release and back-merge PRs carry no new user-facing change of their own.
    if head_kind not in ("feature", "hotfix"):
        return ALLOW
    if facts.changelog_ok is Tri.UNKNOWN:
        return _warn("changelog",
                     "Could not compare against the base branch, so the "
                     "CHANGELOG check was skipped. Run 'git fetch' and retry "
                     "if you want it enforced.")
    if facts.changelog_ok is Tri.FALSE:
        return _block("changelog",
                      "The Unreleased section of CHANGELOG.md has not gained "
                      "any content on this branch. Add an entry before opening "
                      "the PR.")
    return ALLOW


# --- Rule 4: merge strategy ----------------------------------------------

def _rule_merge_strategy(action, facts, cfg):
    if facts.pr_base is None:
        return _warn("merge-strategy", "Could not determine the PR's base branch.")
    # The `and not cfg.is_trunk` guard here relies on an invariant established
    # in config.load_config: under trunk topology, `integration` is always
    # normalized to equal `production`. A directly-constructed Config with
    # topology="trunk" and integration != production would bypass this
    # branch's merge-strategy enforcement silently.
    if facts.pr_base == cfg.integration and not cfg.is_trunk:
        expected = cfg.merge_to_integration
    elif facts.pr_base == cfg.production:
        expected = cfg.merge_to_production
    else:
        return ALLOW
    if action.strategy is None:
        return _warn("merge-strategy",
                     f"No merge strategy given; '{facts.pr_base}' expects "
                     f"--{expected}.")
    if action.strategy != expected:
        return _block("merge-strategy",
                      f"PRs into '{facts.pr_base}' use --{expected}, "
                      f"not --{action.strategy}.")
    return ALLOW


# --- Rule 5: review policy -----------------------------------------------

def _rule_review(action, facts, cfg):
    if facts.pr_review_state == "CHANGES_REQUESTED":
        return _block("review",
                      "This PR has requested changes outstanding. "
                      "Address them first (keel:respond-to-review).")
    if cfg.review_policy == "none":
        return ALLOW
    if facts.pr_base is None:
        return _warn("review", "Could not determine the PR's base branch.")
    # Releases and back-merges carry already-reviewed content.
    head_kind = _kind_of_branch(facts.pr_head, cfg)
    if head_kind in ("release", "production"):
        return ALLOW
    accepted = ("APPROVED",) if cfg.review_policy == "approval" else ("APPROVED", "COMMENTED")
    if facts.pr_review_state is None:
        return _block("review",
                      "This PR has no review yet. Review it first "
                      "(keel:review).")
    if facts.pr_review_state not in accepted:
        return _block("review",
                      f"reviewPolicy is '{cfg.review_policy}', which requires an "
                      f"approving review; this PR is '{facts.pr_review_state}'.")
    return ALLOW


# --- Rule 6: capability ---------------------------------------------------

def _rule_capability(action, facts, cfg):
    # Deliberate divergence from the other rules: Tri.UNKNOWN here maps to
    # ALLOW rather than warn. facts.capability defaults to UNKNOWN, so this
    # is the common case on every call -- warning on it would be constant
    # noise for a best-effort heads-up that never gates anything. "allow"
    # still satisfies the binding policy (UNKNOWN must never block). Do not
    # "fix" this to warn.
    if facts.capability is Tri.FALSE:
        return _warn("capability",
                     "You may not have merge permission on this repository; "
                     "this is likely to fail.")
    return ALLOW


# NOTE: tuple order is load-bearing. When multiple rules for an action.kind
# produce a finding, the FIRST one (in this order) supplies the primary
# decision/rule/message; the rest are appended to the message as secondary
# findings (see evaluate()). Order rules so the most fundamental gate for
# that action comes first.
RULES = {
    "commit": (_rule_protected_write,),
    "push": (_rule_protected_write,),
    "pr-create": (_rule_pr_edge, _rule_changelog),
    "pr-merge": (_rule_review, _rule_merge_strategy, _rule_capability),
}


def evaluate(action, facts, cfg):
    """Return the most severe verdict across the rules for this action.

    Every rule for action.kind is evaluated -- none are skipped once a block
    or warn is found. The most severe decision wins (block > warn > allow);
    among verdicts of that severity, the first one in RULES order supplies
    the primary decision/rule/message. Any additional block or warn verdicts
    are appended to the message as "Also: [rule] message" so they are not
    silently dropped.
    """
    verdicts = [rule(action, facts, cfg) for rule in RULES.get(action.kind, ())]

    blocks = [v for v in verdicts if v.decision == "block"]
    warns = [v for v in verdicts if v.decision == "warn"]

    if blocks:
        primary, rest = blocks[0], blocks[1:] + warns
    elif warns:
        primary, rest = warns[0], warns[1:]
    else:
        return ALLOW

    # Several rules can independently report the same underlying cause (an
    # unresolvable PR base warns from both the review and merge-strategy
    # rules). Repeating identical text just makes the message harder to read.
    seen = {primary.message}
    extra = []
    for verdict in rest:
        if verdict.message in seen:
            continue
        seen.add(verdict.message)
        extra.append(f"Also: [{verdict.rule}] {verdict.message}")

    if not extra:
        return primary
    return Verdict(primary.decision, primary.rule,
                   "{} {}".format(primary.message, " ".join(extra)))
