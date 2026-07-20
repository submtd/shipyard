import pytest
from keel.actions import classify


def kinds(cmd):
    return [a.kind for a in classify(cmd)]


def test_plain_commit():
    assert kinds("git commit -m 'hello'") == ["commit"]


def test_quoted_separator_does_not_fabricate_actions():
    # Regression: the old guard split on ';' inside the quoted message and
    # invented a phantom push from the commit text.
    assert kinds("git commit -m 'fix; git push origin main'") == ["commit"]


def test_chained_commands_are_each_classified():
    assert kinds("git add -A && git commit -m x") == ["commit"]
    assert kinds("git commit -m x && git push origin feature/a") == ["commit", "push"]


def test_push_destination_from_refspec():
    (a,) = classify("git push origin HEAD:main")
    assert a.kind == "push"
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [("HEAD", "main", False)]


def test_push_current_branch_has_no_explicit_dst():
    (a,) = classify("git push origin feature/x")
    assert [(r.src, r.dst) for r in a.refs] == [("feature/x", "feature/x")]


def test_push_with_no_refs_has_empty_refs():
    (a,) = classify("git push")
    assert a.refs == ()


def test_tags_flag_does_not_mark_branch_refs_as_tags():
    # Regression: 'git push origin main --tags' was treated as a pure tag push
    # and allowed for every role.
    (a,) = classify("git push origin main --tags")
    assert [(r.dst, r.is_tag) for r in a.refs] == [("main", False)]


def test_explicit_tag_refspec_is_a_tag():
    (a,) = classify("git push origin refs/tags/v1.2.3")
    assert a.refs[0].is_tag is True


def test_tags_only_push_has_no_branch_refs():
    (a,) = classify("git push origin --tags")
    assert a.refs == ()


def test_pr_create_base_and_head():
    (a,) = classify("gh pr create --base develop --head feature/x --title t")
    assert (a.kind, a.base, a.head) == ("pr-create", "develop", "feature/x")


def test_pr_create_ignores_flag_values_when_finding_subcommand():
    (a,) = classify("gh pr create --repo o/r --base develop --title 'pr create'")
    assert a.kind == "pr-create"
    assert a.repo == "o/r"


def test_pr_merge_number_is_not_a_flag_value():
    # Regression: '--repo o/r' was counted as a positional, so pr_number == 'o/r'.
    (a,) = classify("gh pr merge --squash --repo o/r 5")
    assert (a.kind, a.pr_number, a.strategy) == ("pr-merge", "5", "squash")


def test_pr_merge_short_squash_flag():
    (a,) = classify("gh pr merge 5 -s")
    assert a.strategy == "squash"


def test_pr_merge_unknown_strategy_is_none():
    (a,) = classify("gh pr merge 5")
    assert a.strategy is None


@pytest.mark.parametrize("cmd", [
    "git status",
    "git log --oneline",
    "echo 'git commit -m x'",
    "gh pr view 5",
])
def test_read_only_commands_classify_to_nothing(cmd):
    assert classify(cmd) == []


@pytest.mark.parametrize("cmd,expected_number,expected_strategy", [
    ("gh pr merge -m 5", "5", "merge"),
    ("gh pr merge -r 5", "5", "rebase"),
    ("gh pr merge -s 5", "5", "squash"),
    ("gh pr merge -d -s 5", "5", "squash"),
    ("gh pr merge --repo o/r -m 5", "5", "merge"),
])
def test_pr_merge_boolean_short_flags_do_not_consume_the_number(
        cmd, expected_number, expected_strategy):
    (a,) = classify(cmd)
    assert (a.pr_number, a.strategy) == (expected_number, expected_strategy)


def test_pr_create_with_short_value_flag_before_positional():
    (a,) = classify("gh pr create -t 'some title' --base develop")
    assert (a.kind, a.base) == ("pr-create", "develop")
