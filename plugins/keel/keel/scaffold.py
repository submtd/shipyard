"""Pure helpers for keel:init. No subprocess, no git/gh -- the skill gathers
signals and does I/O; this module maps data to data and reads the filesystem."""
from __future__ import annotations

from pathlib import Path

from keel.config import CONTRIBUTIONS, REVIEW_POLICIES

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


def _non_empty_string_signal(signals, key, default):
    value = signals.get(key, default)
    if not isinstance(value, str) or not value:
        raise ValueError(
            f"signals[{key!r}] must be a non-empty string (got {value!r})."
        )
    return value


def propose_config(signals):
    """Map detected repository signals to a .keel.json dict (camelCase keys).

    Only `has_develop` is required. Everything else has a sensible default the
    caller can override: `production` (str, default "main"), `integration`
    (str, default "develop", only used when `has_develop` is true),
    `contributions` (one of keel.config.CONTRIBUTIONS, default "both"),
    `review_policy` (one of keel.config.REVIEW_POLICIES, default "review"),
    `require_changelog` (bool, default True).

    Every signal is validated against config.py's own domains before the
    dict is built. Valid signals in -> a dict guaranteed to load via
    config.load_config (enforced by test). Invalid signals raise ValueError
    -- naming the bad field and its allowed values -- before anything is
    returned, so a caller can never persist a config that keel itself would
    reject.
    """
    has_develop = signals["has_develop"]
    topology = "gitflow" if has_develop else "trunk"

    production = _non_empty_string_signal(signals, "production", "main")
    branches = {"production": production}
    if topology == "gitflow":
        branches["integration"] = _non_empty_string_signal(
            signals, "integration", "develop")

    contributions = signals.get("contributions", "both")
    if contributions not in CONTRIBUTIONS:
        raise ValueError(
            f"signals['contributions'] must be one of {CONTRIBUTIONS} "
            f"(got {contributions!r})."
        )

    review_policy = signals.get("review_policy", "review")
    if review_policy not in REVIEW_POLICIES:
        raise ValueError(
            f"signals['review_policy'] must be one of {REVIEW_POLICIES} "
            f"(got {review_policy!r})."
        )

    require_changelog = signals.get("require_changelog", True)
    if not isinstance(require_changelog, bool):
        raise ValueError(
            f"signals['require_changelog'] must be a bool "
            f"(got {require_changelog!r})."
        )

    return {
        "topology": topology,
        "branches": branches,
        "contributions": contributions,
        "reviewPolicy": review_policy,
        "requireChangelog": require_changelog,
    }


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
