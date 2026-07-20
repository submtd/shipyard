"""All git subprocess I/O. Every call is timed out. Failures return None."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

from . import actions as _actions

GIT_TIMEOUT = 5.0

_UNRELEASED = re.compile(r"^(#{1,6})\s*\[?unreleased\]?", re.IGNORECASE)


def run_git(args, cwd=None):
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT, errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def repo_root(cwd=None):
    out = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(out) if out else None


def current_branch(cwd=None):
    out = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=cwd)
    return out or None


def _unreleased_body(text):
    """Return the Unreleased section's body, stripped of blank lines.

    Collection stops only at a heading at the SAME or SHALLOWER level than
    the Unreleased heading itself (e.g. a following '## 1.0.0' after a
    '## [Unreleased]'). Deeper nested headings (e.g. '### Added' under
    '## [Unreleased]', the standard Keep-a-Changelog layout) are part of the
    body and must be collected, not treated as terminators.
    """
    lines, collecting, depth, body = text.splitlines(), False, None, []
    for line in lines:
        stripped = line.strip()
        match = _UNRELEASED.match(stripped)
        if match:
            collecting = True
            depth = len(match.group(1))
            continue
        if collecting and stripped.startswith("#"):
            heading_depth = len(stripped) - len(stripped.lstrip("#"))
            if heading_depth <= depth:
                break
        if collecting:
            body.append(line)
    return "\n".join(b for b in body if b.strip())


def _run_git_raw(args, cwd=None):
    """Like run_git, but returns the CompletedProcess (or None if the
    subprocess itself couldn't be run) so callers can distinguish exit
    codes rather than collapsing them all into None/stdout."""
    try:
        return subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT, errors="replace",
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _ref_resolves(ref, cwd=None):
    """Whether `ref` names a real commit -- used to tell "ref is bogus /
    unreachable" (unknown) apart from "ref is fine, path just isn't there
    in it" (legitimately absent)."""
    proc = _run_git_raw(["rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"], cwd=cwd)
    if proc is None:
        return None
    return proc.returncode == 0


def _file_exists_at_ref(ref, path, cwd=None, known_resolvable=False):
    """Whether `path` exists in the tree at `ref`. None if this can't be
    determined (ref doesn't resolve, or the check itself errors/times out)
    -- distinct from a confident "absent".

    `known_resolvable=True` skips the `rev-parse --verify` guard call when
    the caller already knows `ref` resolves (e.g. it came straight out of a
    successful `git merge-base`) -- see Important 7 (timeout budget).
    """
    if not known_resolvable:
        resolves = _ref_resolves(ref, cwd=cwd)
        if resolves is not True:
            return None
    proc = _run_git_raw(["cat-file", "-e", f"{ref}:{path}"], cwd=cwd)
    if proc is None:
        return None
    return proc.returncode == 0


def _changelog_at_ref(ref, cwd=None, known_resolvable=False):
    """Return CHANGELOG.md's content at `ref`, or "" if absent there, or
    None if the git command itself failed (network, timeout, corrupt repo,
    etc.). This is the crux of Finding 3: `git show <ref>:CHANGELOG.md`
    returns non-zero both when the file is absent AND when the command
    fails outright, so a naive `run_git([...]) or ""` would silently turn a
    failure into "the file was empty" -- a confident, wrong answer. We
    disambiguate by first asking git directly whether the path exists at
    that ref (`cat-file -e`); only once we know the file is genuinely
    absent do we treat a `show` miss as "".

    `known_resolvable=True` (see _file_exists_at_ref) skips the redundant
    resolvability check for a ref the caller already proved valid.
    """
    exists = _file_exists_at_ref(ref, "CHANGELOG.md", cwd=cwd,
                                  known_resolvable=known_resolvable)
    if exists is None:
        return None
    if exists is False:
        return ""
    content = run_git(["show", f"{ref}:CHANGELOG.md"], cwd=cwd)
    if content is None:
        # The file exists per cat-file, but `show` failed anyway (e.g. a
        # timeout raced in between). Unknown, not empty.
        return None
    return content


def changelog_present(cwd=None):
    """Whether CHANGELOG.md exists at HEAD. None on git failure."""
    return _file_exists_at_ref("HEAD", "CHANGELOG.md", cwd=cwd)


def changelog_gained_content(base, cwd=None):
    """True if the Unreleased section grew relative to base. None if unknowable.

    Compares HEAD (the committed state of the branch) against the merge
    base -- not the working tree -- so uncommitted edits cannot satisfy the
    gate for content that will not actually be in the PR.

    `base` is tried as given first; if it does not resolve (a fresh clone
    that only ever checked out the feature branch has no local `develop`,
    only `origin/develop`), `origin/<base>` is tried as a fallback so the
    gate still evaluates instead of permanently warning.

    Kept to as few subprocess calls as the timeout budget allows (Important
    7): the two `_changelog_at_ref` lookups below are told the ref is
    already known-resolvable (`merge_base` came from a successful
    `merge-base`; `HEAD` resolved implicitly by the same call), skipping a
    redundant `rev-parse --verify` each would otherwise perform.
    """
    merge_base = run_git(["merge-base", "HEAD", base], cwd=cwd)
    if merge_base is None:
        merge_base = run_git(["merge-base", "HEAD", f"origin/{base}"], cwd=cwd)
    if merge_base is None:
        return None
    before = _changelog_at_ref(merge_base, cwd=cwd, known_resolvable=True)
    if before is None:
        return None
    after = _changelog_at_ref("HEAD", cwd=cwd, known_resolvable=True)
    if after is None:
        return None
    return _unreleased_body(after) != _unreleased_body(before)


_CWD_FLAGS = {"-C", "--git-dir", "--work-tree"}


def target_cwd(command, default):
    """Resolve the directory a command actually operates on.

    Root-cause fix: this used to be its own dumber scanner over the whole
    token list, independent of actions.py's tokenizer -- so it and
    actions.classify() disagreed about the same command string. It now
    reuses actions._segments()/_global_flag_value(), which are already
    positional-aware: a `-C`/`--git-dir`/`--work-tree` is only a cwd
    override when it appears BEFORE the git subcommand. `git commit -C
    HEAD~1` (commit's own "reuse this commit's message" flag) must resolve
    to `default`, not to "HEAD~1" as a path.
    """
    for seg in _actions._segments(command):
        if not seg:
            continue
        prog, rest = seg[0], seg[1:]
        if prog == "cd" and rest:
            return rest[0]
        if prog == "git":
            value = _actions._global_flag_value(rest, _CWD_FLAGS)
            if value is not None:
                return value
    return default
