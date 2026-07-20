"""Classify a Bash command string into lifecycle intents.

Deliberately NOT an adversarial parser -- see the plan's Global Constraints.
The goal is to recognise honest commands correctly, never to be unevadable.
Critically, it must not fabricate actions out of quoted text.
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass

# Flags that consume the following token as their value. Used so that a flag
# value is never mistaken for a positional argument.
GH_CREATE_VALUE_FLAGS = {
    "--base", "-B", "--head", "-H", "--repo", "-R", "--title", "-t",
    "--body", "-b", "--body-file", "-F", "--reviewer", "-r", "--assignee", "-a",
    "--label", "-l", "--milestone", "-m", "--project", "-p",
}
GH_MERGE_VALUE_FLAGS = {
    "--repo", "-R", "--body", "-b", "--body-file", "-F",
    "--subject", "-t", "--match-head-commit", "--author-email",
}
GH_ANY_VALUE_FLAGS = GH_CREATE_VALUE_FLAGS | GH_MERGE_VALUE_FLAGS
GIT_VALUE_FLAGS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
}

TAG_REF = re.compile(r"^refs/tags/")


@dataclass(frozen=True)
class PushRef:
    src: str | None
    dst: str
    is_tag: bool


@dataclass(frozen=True)
class Action:
    kind: str
    refs: tuple[PushRef, ...] = ()
    base: str | None = None
    head: str | None = None
    pr_number: str | None = None
    strategy: str | None = None
    repo: str | None = None


def _segments(command):
    """Split on shell separators, honouring quotes.

    shlex in POSIX mode keeps quoted text intact, so a ';' inside a commit
    message never becomes a separator.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    out, current = [], []
    try:
        for token in lexer:
            if token in ("&&", "||", ";", "|", "&", "\n"):
                out.append(current)
                current = []
            else:
                current.append(token)
    except ValueError:
        # Unbalanced quotes: give up on this command rather than guess.
        return []
    out.append(current)
    return [seg for seg in out if seg]


def _strip_env_prefix(tokens):
    i = 0
    while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
        i += 1
    if i < len(tokens) and tokens[i] == "env":
        i += 1
        while i < len(tokens) and "=" in tokens[i]:
            i += 1
    return tokens[i:]


def _positionals(args, value_flags):
    """Positional args, skipping flags and the values they consume."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in value_flags:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def _flag_value(args, *names):
    for i, tok in enumerate(args):
        for name in names:
            if tok == name and i + 1 < len(args):
                return args[i + 1]
            if tok.startswith(name + "="):
                return tok.split("=", 1)[1]
    return None


def _parse_push(args):
    """`args` excludes the 'git' program token: it starts at the subcommand."""
    refs = []
    positionals = _positionals(args, GIT_VALUE_FLAGS)
    # positionals[0] is 'push'; [1] is the remote if present; rest are refspecs.
    for spec in positionals[2:]:
        if ":" in spec:
            src, dst = spec.split(":", 1)
        else:
            src = dst = spec
        # A ref is a tag only when it says so explicitly. '--tags' elsewhere in
        # the command does NOT make a branch refspec a tag.
        is_tag = bool(TAG_REF.match(dst))
        refs.append(PushRef(src=src or None, dst=dst, is_tag=is_tag))
    return Action(kind="push", refs=tuple(refs))


def _classify_segment(tokens):
    rest = _strip_env_prefix(tokens)
    if not rest:
        return None
    prog, args = rest[0], rest[1:]

    if prog == "git":
        sub = next((a for a in _positionals([prog] + args, GIT_VALUE_FLAGS)[1:]), None)
        if sub == "commit":
            return Action(kind="commit")
        if sub == "push":
            return _parse_push(args)
        return None

    if prog == "gh":
        # First pass: detect subcommand using union of value flags
        pos = _positionals(args, GH_ANY_VALUE_FLAGS)
        if len(pos) >= 2 and pos[0] == "pr" and pos[1] == "create":
            # Re-parse with create-specific value flags to get all positionals
            pos = _positionals(args, GH_CREATE_VALUE_FLAGS)
            return Action(
                kind="pr-create",
                base=_flag_value(args, "--base", "-B"),
                head=_flag_value(args, "--head", "-H"),
                repo=_flag_value(args, "--repo", "-R"),
            )
        if len(pos) >= 2 and pos[0] == "pr" and pos[1] == "merge":
            # Re-parse with merge-specific value flags to get all positionals
            pos = _positionals(args, GH_MERGE_VALUE_FLAGS)
            if "--squash" in args or "-s" in args:
                strategy = "squash"
            elif "--merge" in args or "-m" in args:
                strategy = "merge"
            elif "--rebase" in args or "-r" in args:
                strategy = "rebase"
            else:
                strategy = None
            return Action(
                kind="pr-merge",
                pr_number=pos[2] if len(pos) >= 3 else None,
                strategy=strategy,
                repo=_flag_value(args, "--repo", "-R"),
            )
        return None

    return None


def classify(command):
    actions = []
    for seg in _segments(command):
        action = _classify_segment(seg)
        if action is not None:
            actions.append(action)
    return actions
