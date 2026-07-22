"""Pure helpers for rigging:init. No subprocess, no git/gh -- the skill
gathers signals and does I/O; this module maps data to data and reads the
filesystem."""
from __future__ import annotations

from pathlib import Path

from rigging.config import BRANCH_RE, NAME_RE, VERSION_RE
from rigging.stacks import NODE_PACKAGE_MANAGERS, STACK_IDS


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
SIGNAL_KEYS = frozenset({"name", "stacks", "versions", "pushBranches",
                         "unsupported", "packageManagers"})


def _valid_unsupported(signals):
    """Validate the optional `unsupported` signal, returning a {id: reason} dict.

    This is `detect.unsupported_reasons(root)` passed straight through by the
    skill. It exists so the refusal is load-bearing rather than advisory: the
    skill is prose, and prose can be skimmed, misread, or overridden by a user
    who says "just do it anyway". A `ValueError` out of `propose_config`
    cannot be skimmed -- it stops the scaffold at the one place that decides
    what goes on disk.

    Absent or empty is the normal case and must behave EXACTLY as before this
    signal existed -- no reordering of keys, no extra validation, nothing
    observable in the returned dict. The signal only ever subtracts
    possibilities; it can never change what a successful proposal looks like.
    """
    unsupported = signals.get("unsupported")
    if unsupported is None:
        return {}
    if not isinstance(unsupported, dict):
        raise ValueError(
            f"signals['unsupported'] must be a dict of stack id -> reason "
            f"string (got {unsupported!r})."
        )
    for stack_id, reason in unsupported.items():
        if not isinstance(stack_id, str) or not isinstance(reason, str) or not reason:
            raise ValueError(
                f"signals['unsupported'] entries must map a stack id string "
                f"to a non-empty reason string (got {stack_id!r}: {reason!r})."
            )
    return unsupported


def _valid_package_managers(signals, stack_ids):
    """Validate the optional `packageManagers` signal.

    A mapping of stack id -> manager id, normally `detect.node_package_manager`'s
    answer. A manager named for a stack that is not being proposed is a caller
    mistake rather than something to drop: a dropped signal here means the
    scaffolded repo silently gets the default manager, and the resulting red
    install step surfaces far from its cause.
    """
    managers = signals.get("packageManagers")
    if managers is None:
        return {}
    if not isinstance(managers, dict):
        raise ValueError(
            f"signals['packageManagers'] must be a dict of stack id -> "
            f"manager id (got {managers!r})."
        )
    for stack_id, manager_id in managers.items():
        if stack_id not in stack_ids:
            raise ValueError(
                f"signals['packageManagers'] names stack {stack_id!r}, which "
                f"is not in signals['stacks']."
            )
        # Mirrors config._valid_package_manager's own stack-id check -- a
        # packageManager only means anything for node. Without this,
        # propose_config would happily emit `stacks.<id>.packageManager` for
        # a stack load_config rejects it on, breaking propose_config's
        # contract that valid signals produce a config load_config accepts.
        # This is the third site hardcoding "node" (alongside
        # config._valid_package_manager and plan._manager_steps); if you
        # change one, check the other two.
        if stack_id != "node":
            raise ValueError(
                f"signals['packageManagers'] names stack {stack_id!r}, which "
                f"has no package manager to select."
            )
        # isinstance first: an unhashable manager_id (a list, a dict) would
        # raise TypeError from the dict-membership test below rather than the
        # ValueError this validator's contract promises for a bad field.
        if not isinstance(manager_id, str) or manager_id not in NODE_PACKAGE_MANAGERS:
            raise ValueError(
                f"signals['packageManagers'][{stack_id!r}] must be one of "
                f"{', '.join(NODE_PACKAGE_MANAGERS)} (got {manager_id!r})."
            )
    return managers


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

    Optional `signals["unsupported"]` is `detect.unsupported_reasons(root)`
    passed through unchanged -- a dict of stack id -> reason string. Any stack
    named in BOTH `stacks` and `unsupported` raises ValueError quoting the
    reason, so a workflow that provably cannot pass is never proposed, let
    alone written. Omitting the signal (or passing `{}`) leaves behaviour
    byte-identical to before it existed.

    Every signal is validated against config.py's/stacks.py's own domains
    before the dict is built. Valid signals in -> a dict guaranteed to load
    via config.load_config (enforced by test). Invalid signals raise
    ValueError -- naming the bad field -- before anything is returned, so a
    caller can never persist a config that rigging itself would reject.
    """
    _reject_unknown_signals(signals)
    unsupported = _valid_unsupported(signals)
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

    package_managers = _valid_package_managers(signals, set(stack_ids))

    stacks_out = {}
    for stack_id in stack_ids:
        if stack_id not in STACK_IDS:
            raise ValueError(
                f"signals['stacks'] contains unknown stack id {stack_id!r}. "
                f"Allowed ids: {', '.join(STACK_IDS)}."
            )
        # Checked per stack, inside the same loop that would otherwise emit
        # it, so there is no path that proposes a stack the caller was already
        # told rigging cannot drive. The reason is repeated verbatim in the
        # message rather than summarised: it is the only diagnosis the user
        # will see, and it already names the marker, the package manager, and
        # why the workflow could not pass.
        if stack_id in unsupported:
            raise ValueError(
                f"refusing to propose a config for stack {stack_id!r}: "
                f"{unsupported[stack_id]}"
            )
        versions = versions_by_id.get(stack_id)
        entry = {}
        if versions:
            for version in versions:
                if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                    raise ValueError(
                        f"signals['versions'][{stack_id!r}] entries must be "
                        f"non-empty strings matching {VERSION_RE.pattern} "
                        f"(got {version!r})."
                    )
            entry["versions"] = list(versions)
        if stack_id in package_managers:
            entry["packageManager"] = package_managers[stack_id]
        stacks_out[stack_id] = entry

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
