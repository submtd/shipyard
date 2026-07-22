"""Pure helpers for hull:init. No subprocess, no git/gh -- the skill gathers
signals and does I/O; this module maps data to data and reads the
filesystem via pathlib only."""
from __future__ import annotations

from pathlib import Path

from hull.config import BRANCH_RE, NAME_RE
from hull.scanners import SCANNER_IDS


def _valid_push_branches(signals):
    """Validate an optional `pushBranches` signal, returning it or None.

    None means "omit the key entirely" so config.load_config supplies the
    default -- writing today's default out explicitly would freeze it into
    every scaffolded repo. Rejected here as well as in load_config because
    propose_config's contract is that valid signals produce a config
    load_config accepts.
    """
    branches = signals.get("pushBranches")
    if branches is None:
        return None
    if not isinstance(branches, (tuple, list)) or not branches:
        raise ValueError(
            f"signals['pushBranches'] must be a non-empty list/tuple of "
            f"branch names (got {branches!r})."
        )
    for branch in branches:
        if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch):
            raise ValueError(
                f"signals['pushBranches'] entries must be strings matching "
                f"{BRANCH_RE.pattern} (got {branch!r})."
            )
    return list(branches)


#: Every signal `propose_config` understands. An unrecognised key is an error
#: rather than something to ignore: silently dropping it means the caller
#: believes they configured something they did not, and the scaffold quietly
#: takes a default instead. That is the same reasoning the config loaders
#: already apply to unknown FILE keys -- and it matters more here, because a
#: dropped signal leaves nothing on disk to inspect afterwards.
SIGNAL_KEYS = frozenset({"name", "scanner", "pushBranches"})


def _reject_unknown_signals(signals):
    if not isinstance(signals, dict):
        raise ValueError(f"signals must be a dict (got {signals!r}).")
    unknown = set(signals) - SIGNAL_KEYS
    if unknown:
        raise ValueError(
            f"unknown signal key(s) {', '.join(sorted(unknown))}. "
            f"Allowed keys: {', '.join(sorted(SIGNAL_KEYS))}."
        )


def propose_config(signals):
    """Map detected repository signals to a .hull.json dict.

    `signals` may set `name` (default "security") and `scanner` (default
    "gitleaks"). Both are validated against config.py's own validators
    (NAME_RE, SCANNER_IDS) before the dict is built. Valid signals in -> a
    dict guaranteed to load via config.load_config (enforced by test).
    Invalid signals raise ValueError -- naming the bad field -- before
    anything is returned, so a caller can never persist a config that hull
    itself would reject.
    """
    _reject_unknown_signals(signals)
    name = signals.get("name", "security")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"signals['name'] must be a string matching {NAME_RE.pattern} "
            f"(got {name!r})."
        )

    scanner = signals.get("scanner", "gitleaks")
    if not isinstance(scanner, str) or scanner not in SCANNER_IDS:
        raise ValueError(
            f"signals['scanner'] must be one of {', '.join(SCANNER_IDS)} "
            f"(got {scanner!r})."
        )

    out = {"name": name, "scanner": scanner}
    push_branches = _valid_push_branches(signals)
    if push_branches is not None:
        out["pushBranches"] = push_branches
    return out


def SECURITY_FILES(name):
    """Candidate paths init may write, in the order it reports them.

    `name` is validated via config.NAME_RE.fullmatch as defense in depth:
    it flows into a workflow file path below, so a path-escaping name
    (e.g. "../evil") must never reach that join.
    """
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"name must be a string matching {NAME_RE.pattern} (got {name!r})."
        )
    return [".hull.json", f".github/workflows/{name}.yml"]


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
