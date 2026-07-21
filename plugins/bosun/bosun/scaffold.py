"""Pure helpers for bosun:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from bosun import ecosystems


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

    detected = set(ecosystem_ids)
    ecosystems_out = {}
    for ecosystem_id, spec in ecosystems.REGISTRY.items():
        if not (spec.always_on or ecosystem_id in detected):
            continue
        interval = intervals_by_id.get(ecosystem_id)
        if interval is not None:
            if interval not in ecosystems.INTERVALS:
                raise ValueError(
                    f"signals['intervals'][{ecosystem_id!r}] must be one "
                    f"of {ecosystems.INTERVALS} (got {interval!r})."
                )
            ecosystems_out[ecosystem_id] = {"interval": interval}
        else:
            ecosystems_out[ecosystem_id] = {}

    return {"ecosystems": ecosystems_out}


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
