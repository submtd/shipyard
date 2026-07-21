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


# --- Critical 2: push destinations must normalize --------------------------

def test_push_force_prefix_is_stripped_from_dst():
    (a,) = classify("git push origin +main")
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [("main", "main", False)]


def test_push_refs_heads_prefix_is_stripped_from_dst():
    (a,) = classify("git push origin HEAD:refs/heads/main")
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [("HEAD", "main", False)]


def test_push_force_prefix_with_refspec_colon():
    (a,) = classify("git push origin +HEAD:main")
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [("HEAD", "main", False)]


def test_push_bare_refs_heads_dst_normalizes():
    (a,) = classify("git push origin refs/heads/main")
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [
        ("refs/heads/main", "main", False)]


def test_push_tag_ref_unaffected_by_normalization():
    (a,) = classify("git push origin refs/tags/v1.0.0")
    assert a.refs[0].dst == "refs/tags/v1.0.0"
    assert a.refs[0].is_tag is True


@pytest.mark.parametrize("cmd,kind,number,base", [
    ("gh -R owner/repo pr merge 5", "pr-merge", "5", None),
    ("gh --repo owner/repo pr merge --squash 5", "pr-merge", "5", None),
    ("gh --repo owner/repo pr create --title x --base develop", "pr-create", None, "develop"),
    ("gh -R owner/repo pr create --base develop", "pr-create", None, "develop"),
])
def test_global_flags_before_subcommand_still_classify(cmd, kind, number, base):
    (a,) = classify(cmd)
    assert (a.kind, a.pr_number, a.base) == (kind, number, base)


# --- newline-separated commands -------------------------------------------
#
# The Bash tool routinely sends multi-line scripts, so these are the common
# case, not an adversarial one. _segments listed "\n" as a separator, but
# shlex in whitespace_split mode never emits a newline token -- newline is
# whitespace -- so a multi-line command collapsed into ONE segment whose
# first positional was the first subcommand. Everything after it vanished:
# classify('git status\ngit push origin main') returned [] and the guard
# allowed a push to a protected branch it would otherwise have blocked.


def test_newline_separates_commands():
    actions = classify("git status\ngit push origin main")
    assert [a.kind for a in actions] == ["push"]
    assert actions[0].refs[0].dst == "main"


def test_newline_separated_commit_is_seen():
    actions = classify('git add -A\ngit commit -m "wip"')
    assert [a.kind for a in actions] == ["commit"]


def test_every_command_in_a_multi_line_script_is_classified():
    actions = classify("git fetch\ngit push origin main\ngit push origin develop")
    assert [a.refs[0].dst for a in actions] == ["main", "develop"]


def test_blank_lines_and_indentation_do_not_produce_empty_segments():
    actions = classify("git fetch\n\n   \n  git push origin main\n")
    assert [a.kind for a in actions] == ["push"]


def test_newline_inside_a_quoted_argument_does_not_split_the_command():
    # The naive fix -- str.split("\n") before lexing -- breaks exactly here:
    # each half lexes as unbalanced quotes and the whole command is dropped.
    # A multi-line commit message must stay one token.
    actions = classify('git commit -m "first line\nsecond line"')
    assert [a.kind for a in actions] == ["commit"]


def test_a_command_after_a_multi_line_quoted_argument_is_still_seen():
    actions = classify('git commit -m "first\nsecond"\ngit push origin main')
    assert [a.kind for a in actions] == ["commit", "push"]
    assert actions[1].refs[0].dst == "main"


def test_newline_and_operator_separators_mix():
    actions = classify("git fetch && git push origin main\ngit push origin develop")
    assert [a.refs[0].dst for a in actions] == ["main", "develop"]


# --- shell comments --------------------------------------------------------
#
# commenters was disabled, so a trailing comment's words became positional
# args. `git push origin feature/x  # deploy to main` parsed 'main' as a
# refspec and the guard emitted a hard DENY citing a protected branch the
# command never touched -- a false block with an untrue reason, which is the
# failure mode most corrosive to an advisory hook's credibility.


def test_a_trailing_comment_is_not_parsed_as_refspecs():
    actions = classify("git push origin feature/x  # deploy to main")
    assert [r.dst for r in actions[0].refs] == ["feature/x"]


def test_a_comment_mentioning_a_protected_branch_is_ignored():
    actions = classify("git push origin feature/x # not develop")
    assert [r.dst for r in actions[0].refs] == ["feature/x"]


def test_a_hash_inside_quotes_is_still_a_literal():
    # posix shlex resolves quotes before comments, so enabling commenters
    # must not eat a '#' the user actually meant -- e.g. an issue reference
    # in a commit message.
    actions = classify('git commit -m "fix #123 for real"')
    assert [a.kind for a in actions] == ["commit"]


def test_a_comment_does_not_swallow_a_following_line():
    # shlex's own comment handling reads to end of line and consumes the
    # newline with it, which would silently re-merge these two commands and
    # lose the push. Comments are stripped by hand for exactly this reason.
    actions = classify('git commit -m "wip" # done for now\ngit push origin main')
    assert [a.kind for a in actions] == ["commit", "push"]
    assert actions[1].refs[0].dst == "main"


# --- pushes that carry no refspec but write every branch -------------------


def test_push_all_is_flagged():
    assert classify("git push --all origin")[0].pushes_every_branch is True


def test_push_mirror_is_flagged():
    assert classify("git push --mirror origin")[0].pushes_every_branch is True


def test_an_ordinary_push_is_not_flagged():
    assert classify("git push origin main")[0].pushes_every_branch is False


def test_a_push_with_no_refspec_is_not_flagged():
    assert classify("git push")[0].pushes_every_branch is False


# --- Strategy flags were detected with `"-s" in args`, a membership test
# over every token. Any flag VALUE that happened to equal a strategy flag
# was read as the strategy -- and the merge-strategy rule blocks outright on
# a mismatch, so a correct command got a hard DENY citing a strategy it
# never asked for. -----------------------------------------------------


def test_a_flag_value_that_looks_like_a_strategy_flag_is_not_the_strategy():
    action = classify("gh pr merge 1 --body '-s' --merge")[0]
    assert action.strategy == "merge"


def test_a_strategy_is_not_invented_from_a_body_alone():
    action = classify("gh pr merge 1 --body '-s'")[0]
    assert action.strategy is None


def test_a_subject_that_looks_like_a_strategy_flag_is_not_the_strategy():
    action = classify("gh pr merge 1 --subject '--rebase' --squash")[0]
    assert action.strategy == "squash"


def test_the_first_real_strategy_flag_wins():
    assert classify("gh pr merge 1 --squash")[0].strategy == "squash"
    assert classify("gh pr merge 1 -r")[0].strategy == "rebase"
    assert classify("gh pr merge 1 -m")[0].strategy == "merge"
