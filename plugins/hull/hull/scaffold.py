"""Pure helpers for hull:init. No subprocess, no git/gh -- the skill gathers
signals and does I/O; this module maps data to data and reads the
filesystem via pathlib only."""
from __future__ import annotations

from pathlib import Path

from hull.config import NAME_RE
from hull.scanners import SCANNER_IDS


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

    return {"name": name, "scanner": scanner}


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
