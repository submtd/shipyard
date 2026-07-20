import pytest
from keel.actions import Action, PushRef
from keel.config import Config
from keel.facts import Facts, Tri
from keel.rules import evaluate, Verdict


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


def test_trunk_topology_allows_feature_into_production():
    action = Action(kind="pr-create", base="main", head="feature/x")
    facts = Facts(branch="feature/x", changelog_ok=Tri.TRUE)
    c = cfg(topology="trunk", integration="main")
    assert evaluate(action, facts, c).decision != "block"


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


def test_changelog_gate_disabled_by_config():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    c = cfg(require_changelog=False)
    assert evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.FALSE), c).decision == "allow"


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


# --- Rule 6: capability ---------------------------------------------------

def test_missing_capability_warns_never_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="APPROVED", capability=Tri.FALSE)
    assert evaluate(action, facts, cfg()).decision == "warn"
