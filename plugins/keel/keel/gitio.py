"""All git subprocess I/O. Every call is timed out. Failures return None."""
from __future__ import annotations

import re
import shlex
import subprocess
from pathlib import Path

GIT_TIMEOUT = 5.0

# Recognizably GitHub-style remotes only:
#   SSH scp-like form:  git@host:owner/repo(.git)
#   URL form w/ scheme: https://host/owner/repo(.git), ssh://git@host/owner/repo(.git)
# A bare local filesystem path (e.g. /Users/x/repos/myproject) must not match.
_SLUG = re.compile(
    r"^(?:[\w.-]+@[\w.-]+:|\w+://(?:[^@/]+@)?[^/]+/)"
    r"([^/]+)/([^/]+?)(?:\.git)?/?$"
)
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


def origin_slug(cwd=None):
    url = run_git(["remote", "get-url", "origin"], cwd=cwd)
    if not url:
        return None
    match = _SLUG.search(url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}".lower()


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


def _file_exists_at_ref(ref, path, cwd=None):
    """Whether `path` exists in the tree at `ref`. None if this can't be
    determined (ref doesn't resolve, or the check itself errors/times out)
    -- distinct from a confident "absent"."""
    resolves = _ref_resolves(ref, cwd=cwd)
    if resolves is not True:
        return None
    proc = _run_git_raw(["cat-file", "-e", f"{ref}:{path}"], cwd=cwd)
    if proc is None:
        return None
    return proc.returncode == 0


def _changelog_at_ref(ref, cwd=None):
    """Return CHANGELOG.md's content at `ref`, or "" if absent there, or
    None if the git command itself failed (network, timeout, corrupt repo,
    etc.). This is the crux of Finding 3: `git show <ref>:CHANGELOG.md`
    returns non-zero both when the file is absent AND when the command
    fails outright, so a naive `run_git([...]) or ""` would silently turn a
    failure into "the file was empty" -- a confident, wrong answer. We
    disambiguate by first asking git directly whether the path exists at
    that ref (`cat-file -e`); only once we know the file is genuinely
    absent do we treat a `show` miss as "".
    """
    exists = _file_exists_at_ref(ref, "CHANGELOG.md", cwd=cwd)
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
    """
    merge_base = run_git(["merge-base", "HEAD", base], cwd=cwd)
    if merge_base is None:
        return None
    before = _changelog_at_ref(merge_base, cwd=cwd)
    if before is None:
        return None
    after = _changelog_at_ref("HEAD", cwd=cwd)
    if after is None:
        return None
    return _unreleased_body(after) != _unreleased_body(before)


def target_cwd(command, default):
    """Resolve the directory a command actually operates on."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return default
    for i, token in enumerate(tokens):
        if token == "-C" and i + 1 < len(tokens):
            return tokens[i + 1]
    if tokens and tokens[0] == "cd" and len(tokens) > 1:
        return tokens[1]
    return default
