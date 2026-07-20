from keel.render import render
from keel.rules import Verdict, ALLOW


def test_allow_produces_no_decision():
    out = render(ALLOW)
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_block_denies_with_reason():
    out = render(Verdict("block", "protected-write", "'main' is protected."))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "'main' is protected." in hso["permissionDecisionReason"]
    assert "keel" in hso["permissionDecisionReason"]
    assert "protected-write" in hso["permissionDecisionReason"]


def test_warn_does_not_deny_but_surfaces_a_message():
    out = render(Verdict("warn", "changelog", "Could not compare."))
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})
    assert "Could not compare." in out["systemMessage"]


def test_unpunctuated_message_does_not_run_into_the_doctor_hint():
    out = render(Verdict("block", "changelog",
                         "set requireChangelog: false in .keel.json"))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert ".keel.json. Run keel:doctor" in reason


def test_already_punctuated_message_is_not_double_punctuated():
    out = render(Verdict("block", "protected-write", "'main' is protected."))
    reason = out["hookSpecificOutput"]["permissionDecisionReason"]
    assert "protected.. Run" not in reason
    assert "protected. Run keel:doctor" in reason
