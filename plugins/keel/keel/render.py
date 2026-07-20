"""Turn a Verdict into the PreToolUse hook's stdout payload."""

DOCTOR = "Run keel:doctor to see the full picture."


def render(verdict):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}
    if verdict.decision == "block":
        out["hookSpecificOutput"]["permissionDecision"] = "deny"
        out["hookSpecificOutput"]["permissionDecisionReason"] = (
            f"[keel/{verdict.rule}] {verdict.message} {DOCTOR}"
        )
    elif verdict.decision == "warn":
        out["systemMessage"] = f"[keel/{verdict.rule}] {verdict.message}"
    return out
