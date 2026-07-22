"""Pure helpers for rigging:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from rigging.config import BRANCH_RE, NAME_RE, VERSION_RE
from rigging.stacks import STACK_IDS


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
SIGNAL_KEYS = frozenset({"name", "stacks", "versions", "pushBranches"})


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
    _reject_unknown_signals(signals)
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

    out = {"name": name, "stacks": stacks_out}
    push_branches = _valid_push_branches(signals)
    if push_branches is not None:
        out["pushBranches"] = push_branches
    return out


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
