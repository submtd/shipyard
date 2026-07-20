import pytest
from keel.actions import Action, PushRef
from keel.config import Config
from keel.facts import Facts, Tri
from keel.rules import evaluate, Verdict, _kind_of_branch, _rule_changelog


def cfg(**over):
    base = dict(
        topology="gitflow", production="main", integration="develop",
        feature_prefix="feature/", release_prefix="release/", hotfix_prefix="hotfix/",
        contributions="both", review_policy="review",
        merge_to_integration="squash", merge_to_production="merge",
        require_changelog=True,
    )
    base.update(over)
    return Config(**base)


# --- Rule 1: protected-branch writes -------------------------------------

def test_commit_on_protected_branch_blocks():
    v = evaluate(Action(kind="commit"), Facts(branch="main"), cfg())
    assert v.decision == "block"
    assert v.rule == "protected-write"


def test_commit_on_feature_branch_allows():
    v = evaluate(Action(kind="commit"), Facts(branch="feature/x"), cfg())
    assert v.decision == "allow"


def test_commit_on_unknown_branch_warns_not_blocks():
    v = evaluate(Action(kind="commit"), Facts(branch=None), cfg())
    assert v.decision == "warn"


def test_push_to_protected_destination_blocks_from_feature_branch():
    # Regression: 'git push origin HEAD:main' was allowed because only the
    # current branch was checked.
    action = Action(kind="push", refs=(PushRef("HEAD", "main", False),))
    v = evaluate(action, Facts(branch="feature/x"), cfg())
    assert v.decision == "block"
    assert v.rule == "protected-write"


def test_push_to_feature_destination_allows():
    action = Action(kind="push", refs=(PushRef("feature/x", "feature/x", False),))
    assert evaluate(action, Facts(branch="feature/x"), cfg()).decision == "allow"


def test_pure_tag_push_allows():
    action = Action(kind="push", refs=(PushRef(None, "refs/tags/v1.0.0", True),))
    assert evaluate(action, Facts(branch="main"), cfg()).decision == "allow"


def test_mixed_tag_and_protected_branch_push_blocks():
    # Regression: 'git push origin main --tags' bypassed everything.
    action = Action(kind="push", refs=(
        PushRef("main", "main", False),
        PushRef(None, "refs/tags/v1.0.0", True),
    ))
    v = evaluate(action, Facts(branch="main"), cfg())
    assert v.decision == "block"


# --- Rule 2: valid PR edges ----------------------------------------------

@pytest.mark.parametrize("head,base", [
    ("feature/x", "develop"),
    ("release/1.2.0", "main"),
    ("hotfix/urgent", "main"),
    ("main", "develop"),
])
def test_valid_edges_allow(head, base):
    action = Action(kind="pr-create", base=base, head=head)
    facts = Facts(branch=head, changelog_ok=Tri.TRUE)
    assert evaluate(action, facts, cfg()).decision != "block"


@pytest.mark.parametrize("head,base", [
    ("feature/x", "main"),
    ("release/1.2.0", "develop"),
])
def test_invalid_edges_block(head, base):
    action = Action(kind="pr-create", base=base, head=head)
    facts = Facts(branch=head, changelog_ok=Tri.TRUE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "pr-edge"


def test_kind_of_branch_exact_name_wins_over_prefix_collision():
    # Regression: prefixes were tested before exact names, so a production
    # branch whose name happened to also match a configured prefix (e.g.
    # production="main-line", feature_prefix="main-") classified as
    # "feature" and never reached the exact-match checks.
    c = cfg(production="main-line", feature_prefix="main-")
    assert _kind_of_branch("main-line", c) == "production"
    assert _kind_of_branch("main-thing", c) == "feature"


def test_trunk_topology_allows_feature_into_production():
    action = Action(kind="pr-create", base="main", head="feature/x")
    facts = Facts(branch="feature/x", changelog_ok=Tri.TRUE)
    c = cfg(topology="trunk", integration="main")
    assert evaluate(action, facts, c).decision != "block"


@pytest.mark.parametrize("head", ["fix/x", "docs/y", "chore/z", "feature/a", "hotfix/b", "anything"])
def test_trunk_accepts_any_work_branch_into_production(head):
    action = Action(kind="pr-create", base="main", head=head)
    facts = Facts(branch=head, changelog_ok=Tri.TRUE, changelog_present=Tri.TRUE)
    assert evaluate(action, facts, cfg(topology="trunk", integration="main")).decision != "block"


def test_trunk_still_rejects_production_into_itself():
    action = Action(kind="pr-create", base="main", head="main")
    facts = Facts(branch="main", changelog_ok=Tri.TRUE, changelog_present=Tri.TRUE)
    v = evaluate(action, facts, cfg(topology="trunk", integration="main"))
    assert v.decision == "block" and v.rule == "pr-edge"


@pytest.mark.parametrize("head", ["fix/x", "docs/y", "chore/z"])
def test_trunk_changelog_gate_applies_to_arbitrary_work_branches(head):
    action = Action(kind="pr-create", base="main", head=head)
    facts = Facts(branch=head, changelog_ok=Tri.FALSE, changelog_present=Tri.TRUE)
    v = evaluate(action, facts, cfg(topology="trunk", integration="main"))
    assert v.decision == "block" and v.rule == "changelog"


def test_gitflow_still_rejects_fix_branch_into_integration():
    # Gitflow behavior must be unchanged: only feature/* is a valid work edge.
    action = Action(kind="pr-create", base="develop", head="fix/x")
    facts = Facts(branch="fix/x", changelog_ok=Tri.TRUE, changelog_present=Tri.TRUE)
    v = evaluate(action, facts, cfg())  # default gitflow
    assert v.decision == "block" and v.rule == "pr-edge"


def test_gitflow_fix_branch_not_subject_to_changelog_gate():
    # Under gitflow a non-feature/hotfix branch is exempt from changelog, as before.
    # (It is already blocked by pr-edge; this pins the changelog rule in isolation.)
    action = Action(kind="pr-create", base="develop", head="fix/x")
    facts = Facts(branch="fix/x", changelog_ok=Tri.FALSE, changelog_present=Tri.TRUE)
    assert _rule_changelog(action, facts, cfg()).decision == "allow"


# --- Rule 3: changelog ----------------------------------------------------

def test_feature_pr_without_changelog_blocks():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    v = evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "block"
    assert v.rule == "changelog"


def test_release_pr_skips_changelog_gate():
    action = Action(kind="pr-create", base="main", head="release/1.2.0")
    v = evaluate(action, Facts(branch="release/1.2.0", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "allow"


def test_back_merge_pr_skips_changelog_gate():
    action = Action(kind="pr-create", base="develop", head="main")
    v = evaluate(action, Facts(branch="main", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "allow"


def test_unknown_changelog_warns():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    v = evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.UNKNOWN), cfg())
    assert v.decision == "warn"


def test_changelog_gate_warns_when_head_kind_unresolvable():
    # Regression: when action.head and facts.branch are both None,
    # _kind_of_branch returns None, which used to fall through the
    # "not in (feature, hotfix)" guard and silently ALLOW -- despite
    # require_changelog=True and total ignorance of the PR's kind.
    action = Action(kind="pr-create", base="develop", head=None)
    v = _rule_changelog(action, Facts(branch=None, changelog_ok=Tri.TRUE), cfg())
    assert v.decision == "warn"
    assert v.rule == "changelog"


def test_changelog_gate_disabled_by_config():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    c = cfg(require_changelog=False)
    assert evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.FALSE), c).decision == "allow"


def test_absent_changelog_blocks_with_distinct_message():
    # Finding 4: a wholly absent CHANGELOG.md should block with a distinct,
    # actionable message -- not the confusing "has not gained any content"
    # text, which implies a file that exists but wasn't edited.
    action = Action(kind="pr-create", base="develop", head="feature/x")
    facts = Facts(branch="feature/x", changelog_present=Tri.FALSE, changelog_ok=Tri.FALSE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "changelog"
    assert "does not exist" in v.message
    assert "requireChangelog" in v.message
    assert "has not gained" not in v.message


def test_unknown_changelog_presence_does_not_block():
    # Tri.UNKNOWN must never block (fail policy). Presence unknown falls
    # through to the existing changelog_ok handling.
    action = Action(kind="pr-create", base="develop", head="feature/x")
    facts = Facts(branch="feature/x", changelog_present=Tri.UNKNOWN, changelog_ok=Tri.UNKNOWN)
    v = evaluate(action, facts, cfg())
    assert v.decision == "warn"


def test_present_but_unchanged_changelog_gives_original_message():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    facts = Facts(branch="feature/x", changelog_present=Tri.TRUE, changelog_ok=Tri.FALSE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert "has not gained any content" in v.message
    assert "does not exist" not in v.message


# --- Rule 4: merge strategy ----------------------------------------------

def test_non_squash_merge_into_integration_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="APPROVED")
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "merge-strategy"


def test_squash_merge_into_integration_allows():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="APPROVED")
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_merge_commit_into_production_allows():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="main", pr_head="release/1.2.0")
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_no_strategy_warn_names_the_actual_base_branch():
    # Regression: the "no strategy given" warn hardcoded cfg.production
    # regardless of the actual PR base, so merging into develop with no
    # --strategy flag produced a message naming 'main' instead of 'develop'.
    action = Action(kind="pr-merge", pr_number="5")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="APPROVED")
    v = evaluate(action, facts, cfg())
    assert v.decision == "warn"
    assert "'develop'" in v.message
    assert "'main'" not in v.message


# --- Rule 5: review policy -----------------------------------------------

def test_same_repo_pr_still_requires_review():
    # Regression: maintainers merging same-repo feature PRs skipped both the
    # squash and review gates via an isCrossRepository check.
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_is_fork=Tri.FALSE, pr_review_state=None)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "review"


def test_policy_review_accepts_commented():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="COMMENTED")
    assert evaluate(action, facts, cfg(review_policy="review")).decision == "allow"


def test_policy_approval_rejects_commented():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="COMMENTED")
    v = evaluate(action, facts, cfg(review_policy="approval"))
    assert v.decision == "block"
    assert v.rule == "review"


def test_policy_none_skips_review():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state=None)
    assert evaluate(action, facts, cfg(review_policy="none")).decision == "allow"


def test_changes_requested_always_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="CHANGES_REQUESTED")
    v = evaluate(action, facts, cfg(review_policy="none"))
    assert v.decision == "block"


def test_unknown_pr_base_warns():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    assert evaluate(action, Facts(pr_base=None), cfg()).decision == "warn"


def test_fork_pr_with_head_named_main_still_requires_review():
    # Important 4: a fork contributor's branch named 'main' collides with
    # the production branch name, so _kind_of_branch(pr_head) alone would
    # read as "production" and skip review entirely. The exemption must be
    # gated on this actually being a same-repo PR.
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="develop", pr_head="main",
                  pr_is_fork=Tri.TRUE, pr_review_state=None)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "review"


def test_fork_pr_with_head_named_release_still_requires_review():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="main", pr_head="release/1.0",
                  pr_is_fork=Tri.TRUE, pr_review_state=None)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "review"


def test_same_repo_back_merge_main_to_develop_still_exempt():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="main",
                  pr_is_fork=Tri.FALSE, pr_review_state=None)
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_same_repo_release_pr_still_exempt():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="main", pr_head="release/1.0",
                  pr_is_fork=Tri.FALSE, pr_review_state=None)
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_unknown_fork_status_does_not_block_beyond_known_false():
    # Fail policy: Tri.UNKNOWN must never produce a block a known-FALSE
    # would not. A known-FALSE (same repo) with head 'main' is exempt, so
    # UNKNOWN must be exempt too, not a fresh source of blocking.
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="main",
                  pr_is_fork=Tri.UNKNOWN, pr_review_state=None)
    assert evaluate(action, facts, cfg()).decision == "allow"


# --- Rule 6: capability ---------------------------------------------------

def test_missing_capability_warns_never_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="APPROVED", capability=Tri.FALSE)
    assert evaluate(action, facts, cfg()).decision == "warn"


# --- evaluate(): block/warn masking across multiple rules -----------------

def test_review_block_and_merge_strategy_block_both_surface():
    # Regression: evaluate() returned on the FIRST block, so a develop-bound
    # PR with strategy="merge" AND CHANGES_REQUESTED reported only the
    # merge-strategy block; the outstanding requested-changes review -- the
    # more fundamental gate -- was invisible.
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="CHANGES_REQUESTED")
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "review"
    assert "requested changes" in v.message
    assert "[merge-strategy]" in v.message
    assert "squash" in v.message


def test_base_branch_warn_and_capability_warn_both_surface():
    # Regression: evaluate() kept only the FIRST warn, so pr_base=None with
    # capability=Tri.FALSE reported only the base-branch warn; the
    # capability warning was silently dropped.
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base=None, capability=Tri.FALSE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "warn"
    assert "base branch" in v.message
    assert "[capability]" in v.message
    assert "merge permission" in v.message


def test_identical_secondary_messages_are_not_repeated():
    # The review and merge-strategy rules both warn when the base is unknown;
    # the user should see that cause once, not twice.
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    v = evaluate(action, Facts(pr_base=None, capability=Tri.FALSE), cfg())
    assert v.message.count("Could not determine the PR's base branch.") == 1
    assert "merge permission" in v.message


@pytest.mark.parametrize("head", ["release/1.2.0", "main"])
def test_release_and_back_merge_prs_are_exempt_from_the_missing_changelog_block(head):
    # A repo with no CHANGELOG.md at all must not have its release or
    # back-merge PRs blocked: those carry no new user-facing change of their
    # own, so the presence check must sit behind the head-kind exemption.
    action = Action(kind="pr-create", base="main" if head.startswith("release/") else "develop",
                    head=head)
    facts = Facts(branch=head, changelog_present=Tri.FALSE, changelog_ok=Tri.FALSE)
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_feature_pr_without_a_changelog_file_gets_the_distinct_message():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    facts = Facts(branch="feature/x", changelog_present=Tri.FALSE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "changelog"
    assert "does not exist" in v.message
    assert "requireChangelog" in v.message
