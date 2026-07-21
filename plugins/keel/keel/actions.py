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
    #: True for `git push --all` / `--mirror`, which carry no refspec but
    #: write every local branch. Without this the protected-write rule saw
    #: `refs == ()` and fell back to checking only the current branch, so
    #: from a feature branch the check passed while the command pushed
    #: production and integration straight to the remote.
    pushes_every_branch: bool = False


#: Newline is a command separator here, not whitespace. That takes two
#: changes acting together and both are load-bearing:
#:
#:   1. "\n" is added to punctuation_chars, so the lexer emits it as its own
#:      token instead of folding it into the neighbouring word.
#:   2. "\n" is removed from `whitespace`, because shlex checks whitespace
#:      first -- left there, the newline is consumed before punctuation
#:      handling ever sees it.
#:
#: Doing only (2) glues the lines together ("status\ngit"); doing neither is
#: the bug this replaced -- `_segments` listed "\n" as a separator but shlex
#: in whitespace_split mode never emitted one, so an entire multi-line
#: script collapsed into a single segment and every command after the first
#: was silently discarded. Multi-line scripts are the Bash tool's normal
#: output, so that was the common case, not an edge case.
#:
#: Splitting the raw string on "\n" before lexing would be simpler and
#: wrong: it cuts multi-line quoted arguments (a heredoc'd or wrapped commit
#: message) in half, and each half then fails to lex as unbalanced quotes.
#: Letting shlex own the split keeps quotes intact -- see
#: test_newline_inside_a_quoted_argument_does_not_split_the_command.
_PUNCTUATION_CHARS = "();<>|&\n"

_WHITESPACE = " \t\r"

_OPERATOR_SEPARATORS = ("&&", "||", ";", "|", "&")


def _is_newline(token):
    """True for a newline separator. A run of blank lines arrives as a
    single all-newline token ("\\n\\n"), so match on composition rather than
    equality."""
    return bool(token) and set(token) == {"\n"}


def _segments(command):
    """Split on shell separators, honouring quotes.

    shlex in POSIX mode keeps quoted text intact, so a ';' inside a commit
    message never becomes a separator.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=_PUNCTUATION_CHARS)
    lexer.whitespace = _WHITESPACE
    lexer.whitespace_split = True
    # Comments are stripped here rather than by shlex. shlex's own comment
    # handling reads to end of line and swallows the newline with it, which
    # would undo the separator above and re-merge the two commands -- see
    # test_a_comment_does_not_swallow_a_following_line. So the lexer keeps
    # emitting '#' tokens and we drop them ourselves, up to but not
    # including the newline.
    #
    # Leaving comments unstripped (the previous behaviour) was worse than
    # cosmetic: the words of a trailing "# deploy to main" became positional
    # args, so `git push origin feature/x # deploy to main` parsed 'main' as
    # a refspec and the guard emitted a hard DENY naming a protected branch
    # the command never touched. A false block with an untrue reason is the
    # most corrosive thing an advisory hook can do.
    lexer.commenters = ""
    out, current, in_comment = [], [], False
    try:
        for token in lexer:
            # Newline first, and unconditionally: it both ends a comment and
            # separates commands. A comment runs to end of line only, so an
            # operator inside one is commented text, not a separator.
            if _is_newline(token):
                out.append(current)
                current = []
                in_comment = False
            elif in_comment:
                continue
            elif token in _OPERATOR_SEPARATORS:
                out.append(current)
                current = []
            elif token.startswith("#"):
                in_comment = True
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


def _global_flag_value(args, names):
    """Value of a global git flag (one of `names`) if it appears BEFORE the
    first positional (the subcommand). This is the same "flags belong to
    whichever side of the subcommand they're on" rule _positionals() and
    classify() already rely on: `git -C /x commit` changes directory, but
    `git commit -C HEAD~1` is the commit subcommand's own (unrelated) flag
    and must not be mistaken for the global one. Used by gitio.target_cwd so
    it shares this tokenizer instead of re-scanning the whole token list."""
    i = 0
    while i < len(args):
        a = args[i]
        if a in names and i + 1 < len(args):
            return args[i + 1]
        if a in GIT_VALUE_FLAGS:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        break  # first positional: the subcommand. Stop -- anything after
               # this point belongs to the subcommand, not to git itself.
    return None


def _parse_push(args):
    """`args` excludes the 'git' program token: it starts at the subcommand."""
    refs = []
    positionals = _positionals(args, GIT_VALUE_FLAGS)
    # positionals[0] is 'push'; [1] is the remote if present; rest are refspecs.
    for spec in positionals[2:]:
        # '+' is a modifier on the WHOLE refspec ('+src:dst'), not on src
        # alone -- strip it before splitting so a force-push refspec still
        # resolves to the same dst a plain push to that branch would.
        body = spec[1:] if spec.startswith("+") else spec
        if ":" in body:
            src, dst = body.split(":", 1)
        else:
            src = dst = body
        # A ref is a tag only when it says so explicitly. '--tags' elsewhere in
        # the command does NOT make a branch refspec a tag. Checked on the
        # pre-normalized dst so a 'refs/tags/...' destination is unaffected
        # by the 'refs/heads/' stripping below.
        is_tag = bool(TAG_REF.match(dst))
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        refs.append(PushRef(src=src or None, dst=dst, is_tag=is_tag))
    # Checked against the raw args, not positionals: these are flags, and
    # they make the refspec list irrelevant to what actually gets written.
    pushes_every_branch = "--all" in args or "--mirror" in args
    return Action(
        kind="push",
        refs=tuple(refs),
        pushes_every_branch=pushes_every_branch,
    )


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
