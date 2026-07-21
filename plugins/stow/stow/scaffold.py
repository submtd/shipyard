"""Pure helpers for stow:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from stow.stacks import BASE, REGISTRY, STACK_IDS

#: Files stow manages in place (splices managed blocks into, rather than
#: writing wholesale). Only .gitignore today.
MANAGED_FILES = [".gitignore"]


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
    whatever key order the .stow.json happens to use."""
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
