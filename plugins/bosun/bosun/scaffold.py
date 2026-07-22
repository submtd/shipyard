"""Pure helpers for bosun:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

import json
from pathlib import Path

from bosun import ecosystems
from bosun.config import BRANCH_RE


#: Every signal `propose_config` understands. An unrecognised key is an error
#: rather than something to ignore: silently dropping it means the caller
#: believes they configured something they did not, and the scaffold quietly
#: takes a default instead. That is the same reasoning the config loaders
#: already apply to unknown FILE keys -- and it matters more here, because a
#: dropped signal leaves nothing on disk to inspect afterwards.
SIGNAL_KEYS = frozenset({"ecosystems", "intervals", "targetBranch"})


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
    """Map detected repository signals to a .bosun.json dict.

    `signals["ecosystems"]` is a list/tuple of detected always-off
    ecosystem ids (the output of `detect.detect_ecosystems`, e.g.
    `["python"]` or `[]`). `githubActions` -- the always-on ecosystem -- is
    never part of that list (detect_ecosystems never surfaces it); this is
    where the always-on policy lives, not in render or plan. propose_config
    adds it itself, unconditionally, so the emitted config always has at
    least one entry even when nothing was detected.

    Optional `signals["intervals"]`, a dict of ecosystem id -> interval
    string (any id it names, including "githubActions"); an ecosystem
    without an entry there emits `{}` so config.load_config fills in its
    "weekly" default.

    Every signal is validated against ecosystems.py's own domains
    (ECOSYSTEM_IDS, INTERVALS) before the dict is built. Valid signals in
    -> a dict guaranteed to load via config.load_config (enforced by
    test). Invalid signals raise ValueError -- naming the bad field --
    before anything is returned, so a caller can never persist a config
    that bosun itself would reject.
    """
    _reject_unknown_signals(signals)
    ecosystem_ids = signals.get("ecosystems")
    if not isinstance(ecosystem_ids, (tuple, list)):
        raise ValueError(
            f"signals['ecosystems'] must be a list/tuple of ecosystem ids "
            f"(got {ecosystem_ids!r})."
        )
    for ecosystem_id in ecosystem_ids:
        if ecosystem_id not in ecosystems.ECOSYSTEM_IDS:
            raise ValueError(
                f"signals['ecosystems'] contains unknown ecosystem id "
                f"{ecosystem_id!r}. Allowed ids: "
                f"{', '.join(ecosystems.ECOSYSTEM_IDS)}."
            )

    intervals_by_id = signals.get("intervals")
    if intervals_by_id is None:
        intervals_by_id = {}
    elif not isinstance(intervals_by_id, dict):
        raise ValueError(
            f"signals['intervals'] must be a dict of ecosystem id -> "
            f"interval string (got {intervals_by_id!r})."
        )

    for interval_id, interval in intervals_by_id.items():
        if interval_id not in ecosystems.ECOSYSTEM_IDS:
            raise ValueError(
                f"signals['intervals'] contains unknown ecosystem id "
                f"{interval_id!r}. Allowed ids: "
                f"{', '.join(ecosystems.ECOSYSTEM_IDS)}."
            )
        if interval not in ecosystems.INTERVALS:
            raise ValueError(
                f"signals['intervals'][{interval_id!r}] must be one "
                f"of {ecosystems.INTERVALS} (got {interval!r})."
            )

    target_branch = signals.get("targetBranch")
    if target_branch is not None and (
        not isinstance(target_branch, str)
        or not BRANCH_RE.fullmatch(target_branch)
    ):
        raise ValueError(
            f"signals['targetBranch'] must be a string matching "
            f"{BRANCH_RE.pattern} (got {target_branch!r})."
        )

    detected = set(ecosystem_ids)
    ecosystems_out = {}
    for ecosystem_id, spec in ecosystems.REGISTRY.items():
        if not (spec.always_on or ecosystem_id in detected):
            continue
        interval = intervals_by_id.get(ecosystem_id)
        if interval is not None:
            ecosystems_out[ecosystem_id] = {"interval": interval}
        else:
            ecosystems_out[ecosystem_id] = {}

    out = {"ecosystems": ecosystems_out}
    # Omitted when unset so config.load_config's "use the repository default
    # branch" behaviour stays the written-down default, rather than being
    # frozen into every scaffolded repo as an explicit branch name.
    if target_branch is not None:
        out["targetBranch"] = target_branch
    return out


def keel_integration_branch(root):
    """Return the integration branch `.keel.json` declares, or None.

    bosun and keel ship in one suite and are routinely adopted together, so
    bosun can usually answer its own hardest question without asking: under
    a gitflow topology keel already knows that `develop`, not the repository
    default branch, is where changes are supposed to land. Rendering a
    `dependabot.yml` with no `target-branch` in such a repo opens weekly
    dependency PRs straight against production, bypassing integration and
    the changelog gate keel enforces -- two plugins in the same suite
    contradicting each other.

    Deliberately reads and interprets the file here rather than importing
    keel: each plugin in this suite is self-contained and installable on its
    own, so a hard dependency on keel's package would be a new and much
    larger coupling than reading a documented config file. The trade-off is
    that this must degrade quietly -- an absent, unreadable, malformed, or
    keel-invalid `.keel.json` returns None, meaning "no answer from keel",
    and the caller falls back to asking the user. It is a convenience, never
    a validator: keel's own loader is the authority on whether that file is
    sound, and duplicating its diagnostics here would let the two drift.

    Returns None under a `trunk` topology too, and that is the correct
    answer rather than a gap: under trunk the integration branch IS the
    repository default branch, so the right rendered output is one with no
    `target-branch` key at all.
    """
    path = Path(root) / ".keel.json"
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(raw, dict):
        return None
    # keel's own default when the key is absent; mirrored rather than
    # imported for the self-containment reason above.
    if raw.get("topology", "gitflow") == "trunk":
        return None
    branches = raw.get("branches", {})
    # An absent `branches` is normal -- keel supplies its own defaults for
    # everything under it. A `branches` of the wrong TYPE is a file keel
    # itself would reject, and guessing a default off a file we already know
    # is broken is worse than admitting we have no answer.
    if not isinstance(branches, dict):
        return None
    branch = branches.get("integration", "develop")
    if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch):
        return None
    return branch


def DEPENDABOT_FILES():
    """Candidate paths init may write, in the order it reports them."""
    return [".bosun.json", ".github/dependabot.yml"]


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
