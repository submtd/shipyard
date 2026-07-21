"""All `gh` subprocess I/O.

One call per concern, always timed out, cached for the life of the process.
Any failure degrades to None/UNKNOWN -- never to a false confident answer.
"""
import json
import subprocess

from .facts import Tri

GH_TIMEOUT = 8.0

# The cache lives only as long as the process. keel's hooks are one-shot -- a
# fresh interpreter per tool call that exits immediately -- so this deduplicates
# lookups within a single evaluation and then dies. That is also why caching a
# failed lookup is safe: a transient gh blip cannot outlive the hook run.

_PR_FIELDS = "baseRefName,headRefName,isCrossRepository,reviewDecision,reviews"
_cache = {}


def clear_cache():
    _cache.clear()


def _gh_json(args, cwd=None):
    try:
        proc = subprocess.run(
            ["gh", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _review_state(data):
    """Collapse reviewDecision + reviews into one state string."""
    decision = data.get("reviewDecision")
    if decision in ("CHANGES_REQUESTED", "APPROVED"):
        return decision
    states = {r.get("state") for r in (data.get("reviews") or []) if isinstance(r, dict)}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    if "COMMENTED" in states:
        return "COMMENTED"
    return None


def pr_facts(number, cwd=None, repo=None):
    """Fetch base/head/fork/review facts for a PR in a single `gh` call.

    Returns None if the `gh` call itself fails (not found, timeout,
    non-zero exit, malformed JSON) -- this means "unknown, could not
    reach GitHub". This is distinct from a successful call whose PR has
    no reviews yet, which returns a dict with review_state: None -- this
    means "known: no review posted". Callers (keel.rules) must not
    collapse these two cases: a failed gh call must never be treated as
    a confident "no review" that blocks a merge for the wrong reason.
    """
    # `repo` is part of the cache key, not just the argv: without it the
    # first repository's answer would be served for the second, which is
    # the same wrong-repo bug one layer down.
    key = ("pr", number, cwd, repo)
    if key in _cache:
        return _cache[key]
    args = ["pr", "view"]
    if number:
        args.append(str(number))
    if repo:
        args += ["--repo", repo]
    args += ["--json", _PR_FIELDS]
    data = _gh_json(args, cwd=cwd)
    if data is None:
        _cache[key] = None
        return None
    result = {
        "base": data.get("baseRefName") or None,
        "head": data.get("headRefName") or None,
        "is_fork": Tri.of(data.get("isCrossRepository")),
        "review_state": _review_state(data),
    }
    _cache[key] = result
    return result


def capability(cwd=None, repo=None):
    """Whether the current user can push/maintain the target repository."""
    key = ("cap", cwd, repo)
    if key in _cache:
        return _cache[key]
    # NB: no `-q` here. With `-q` gh emits a bare word like `ADMIN`, which is
    # not valid JSON, so json.loads would always fail and this path would
    # silently never work. Ask for the object and read the field ourselves.
    args = ["repo", "view"]
    if repo:
        args.append(repo)
    args += ["--json", "viewerPermission"]
    data = _gh_json(args, cwd=cwd)
    # `--json viewerPermission` restricts the payload to exactly that field, so
    # this is the only shape gh can return. Anything else means the call failed.
    if isinstance(data, dict) and data.get("viewerPermission"):
        result = Tri.of(data["viewerPermission"] in ("ADMIN", "MAINTAIN", "WRITE"))
    else:
        result = Tri.UNKNOWN
    _cache[key] = result
    return result
