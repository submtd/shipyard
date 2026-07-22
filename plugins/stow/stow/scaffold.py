"""Pure helpers for stow:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from stow.stacks import BASE, REGISTRY, STACK_IDS

#: Files stow manages in place (splices managed blocks into, rather than
#: writing wholesale). Only .gitignore today.
MANAGED_FILES = [".gitignore"]


#: Every signal `propose_config` understands. An unrecognised key is an error
#: rather than something to ignore: silently dropping it means the caller
#: believes they configured something they did not, and the scaffold quietly
#: takes a default instead. That is the same reasoning the config loaders
#: already apply to unknown FILE keys -- and it matters more here, because a
#: dropped signal leaves nothing on disk to inspect afterwards.
SIGNAL_KEYS = frozenset({"stacks"})


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
    """Map detected repository signals to a .stow.json dict.

    `signals["stacks"]` is a list/tuple of registry stack ids (from
    `detect_stacks`) -- possibly empty, meaning base-only.

    Every id is validated against stacks.py's own domain before the dict is
    built. Valid signals in -> a dict guaranteed to load via
    config.load_config (enforced by test), including the empty-list case.
    Invalid signals raise ValueError -- naming the bad field -- before
    anything is returned, so a caller can never persist a config that stow
    itself would reject.
    """
    _reject_unknown_signals(signals)
    stack_ids = signals.get("stacks")
    if not isinstance(stack_ids, (tuple, list)):
        raise ValueError(
            f"signals['stacks'] must be a list/tuple of stack ids "
            f"(got {stack_ids!r})."
        )

    for stack_id in stack_ids:
        if stack_id not in STACK_IDS:
            raise ValueError(
                f"signals['stacks'] contains unknown stack id {stack_id!r}. "
                f"Allowed ids: {', '.join(STACK_IDS)}."
            )

    return {"stacks": {stack_id: {} for stack_id in stack_ids}}


def desired_sections(config):
    """Return the ordered list of StackSpec sections a config wants:
    BASE first, then each registry spec present in `config.stacks`, in
    REGISTRY order. Block order is therefore canonical -- independent of
    whatever key order the .stow.json happens to use.

    `config` of None means `load_config` found no .stow.json. The skill's
    section-4 one-liner pipes load_config straight in here, so that case is
    reachable by running the steps out of order -- and it used to surface as
    a bare AttributeError from two frames deep, naming neither the file nor
    the fix."""
    if config is None:
        raise ValueError(
            "no .stow.json found: stow cannot decide which sections a repo "
            "wants without one. Run stow:init's config step first."
        )
    return [BASE] + [
        REGISTRY[stack_id] for stack_id in STACK_IDS if stack_id in config.stacks
    ]


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
