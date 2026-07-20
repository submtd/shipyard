"""Turn a Verdict into the PreToolUse hook's stdout payload."""

DOCTOR = "Run keel:doctor to see the full picture."


def _sentence(text):
    """End `text` with punctuation so appended sentences do not run together."""
    text = text.strip()
    if text and text[-1] not in ".!?":
        return text + "."
    return text


def render(verdict):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}
    if verdict.decision == "block":
        out["hookSpecificOutput"]["permissionDecision"] = "deny"
        out["hookSpecificOutput"]["permissionDecisionReason"] = (
            f"[keel/{verdict.rule}] {_sentence(verdict.message)} {DOCTOR}"
        )
    elif verdict.decision == "warn":
        out["systemMessage"] = f"[keel/{verdict.rule}] {verdict.message}"
    return out
