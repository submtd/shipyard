"""Pure helpers for rigging:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from rigging.config import NAME_RE, VERSION_RE
from rigging.stacks import STACK_IDS


def propose_config(signals):
    """Map detected repository signals to a .rigging.json dict (camelCase
    keys, though rigging's schema is all-lowercase today).

    `signals["stacks"]` is a non-empty tuple/list of detected stack ids
    (from `detect_stacks`). Optional `signals["name"]` (default "ci").
    Optional `signals["versions"]`, a dict of stack id -> list of version
    strings; a stack without an entry there emits `{}` so config.load_config
    fills in its registry defaults.

    Every signal is validated against config.py's/stacks.py's own domains
    before the dict is built. Valid signals in -> a dict guaranteed to load
    via config.load_config (enforced by test). Invalid signals raise
    ValueError -- naming the bad field -- before anything is returned, so a
    caller can never persist a config that rigging itself would reject.
    """
    name = signals.get("name", "ci")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"signals['name'] must be a string matching {NAME_RE.pattern} "
            f"(got {name!r})."
        )

    stack_ids = signals.get("stacks")
    if not isinstance(stack_ids, (tuple, list)) or not stack_ids:
        raise ValueError(
            f"signals['stacks'] must be a non-empty list/tuple of stack "
            f"ids (got {stack_ids!r})."
        )

    versions_by_id = signals.get("versions")
    if versions_by_id is None:
        versions_by_id = {}
    elif not isinstance(versions_by_id, dict):
        raise ValueError(
            f"signals['versions'] must be a dict of stack id -> list of "
            f"version strings (got {versions_by_id!r})."
        )

    stacks_out = {}
    for stack_id in stack_ids:
        if stack_id not in STACK_IDS:
            raise ValueError(
                f"signals['stacks'] contains unknown stack id {stack_id!r}. "
                f"Allowed ids: {', '.join(STACK_IDS)}."
            )
        versions = versions_by_id.get(stack_id)
        if versions:
            for version in versions:
                if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                    raise ValueError(
                        f"signals['versions'][{stack_id!r}] entries must be "
                        f"non-empty strings matching {VERSION_RE.pattern} "
                        f"(got {version!r})."
                    )
            stacks_out[stack_id] = {"versions": list(versions)}
        else:
            stacks_out[stack_id] = {}

    return {"name": name, "stacks": stacks_out}


def CI_FILES(name):
    """Candidate paths init may write, in the order it reports them."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"name must be a string matching {NAME_RE.pattern} (got {name!r})."
        )
    return [".rigging.json", f".github/workflows/{name}.yml"]


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
