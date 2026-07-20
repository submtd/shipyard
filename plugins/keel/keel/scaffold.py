"""Pure helpers for keel:init. No subprocess, no git/gh -- the skill gathers
signals and does I/O; this module maps data to data and reads the filesystem."""
from __future__ import annotations

from pathlib import Path

# Candidate lifecycle artifacts init may scaffold, in the order it reports them.
LIFECYCLE_FILES = [
    ".keel.json",
    "CHANGELOG.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/ISSUE_TEMPLATE/feature_request.md",
    ".github/workflows/changelog.yml",
    "scripts/check_changelog.py",
    "CODEOWNERS",
    "LICENSE",
]


def propose_config(signals):
    """Map detected repository signals to a .keel.json dict (camelCase keys).

    Only `has_develop` is required. Everything else has a sensible default the
    caller can override. The result is guaranteed to load via config.load_config
    (enforced by test).
    """
    has_develop = signals["has_develop"]
    topology = "gitflow" if has_develop else "trunk"
    branches = {"production": "main"}
    if topology == "gitflow":
        branches["integration"] = "develop"
    return {
        "topology": topology,
        "branches": branches,
        "contributions": signals.get("contributions", "both"),
        "reviewPolicy": signals.get("review_policy", "review"),
        "requireChangelog": signals.get("require_changelog", True),
    }


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
