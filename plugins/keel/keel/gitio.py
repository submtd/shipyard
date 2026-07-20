"""All git subprocess I/O. Every call is timed out. Failures return None."""
import re
import shlex
import subprocess
from pathlib import Path

GIT_TIMEOUT = 5.0

_SLUG = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
_UNRELEASED = re.compile(r"^#{1,3}\s*\[?unreleased\]?", re.IGNORECASE)


def run_git(args, cwd=None):
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT,
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
    """Return the Unreleased section's body, stripped of blank lines."""
    lines, collecting, body = text.splitlines(), False, []
    for line in lines:
        if _UNRELEASED.match(line.strip()):
            collecting = True
            continue
        if collecting and line.strip().startswith("#"):
            break
        if collecting:
            body.append(line)
    return "\n".join(b for b in body if b.strip())


def changelog_gained_content(base, cwd=None):
    """True if the Unreleased section grew relative to base. None if unknowable."""
    merge_base = run_git(["merge-base", "HEAD", base], cwd=cwd)
    if merge_base is None:
        return None
    before = run_git(["show", f"{merge_base}:CHANGELOG.md"], cwd=cwd) or ""
    root = repo_root(cwd=cwd)
    if root is None:
        return None
    path = root / "CHANGELOG.md"
    after = path.read_text() if path.is_file() else ""
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
