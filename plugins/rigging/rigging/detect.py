"""Stack detection from repo-root marker files.

Pure module. Stdlib only; no subprocess, no os, no networking -- pathlib
existence checks and `json.loads` on a file this module read itself. A later
task enforces this invariant over the whole engine via an AST test.
"""
from __future__ import annotations

import json
from pathlib import Path

from rigging import stacks


def detect_stacks(root) -> tuple[str, ...]:
    """Return the ids of stacks (registry order) whose markers exist at root."""
    root = Path(root)
    detected = []
    for stack_id, spec in stacks.REGISTRY.items():
        # is_file, not exists: a *directory* with a marker's name holds no
        # configuration, and detecting off one scaffolds the wrong stack.
        if any((root / filename).is_file() for filename in spec.detect_files):
            detected.append(stack_id)
    return tuple(detected)


def _declared_package_manager(root):
    """Return the package manager named by package.json's `packageManager`
    field, lowercased and stripped of its version, or None for "no signal".

    corepack's `packageManager` field is a string like `"pnpm@9.12.0"` (a
    name, `@`, and a version, optionally with a `+sha...` integrity suffix).
    We only care about the name.

    Every failure mode here -- no package.json, unreadable bytes, malformed
    JSON, a top-level array instead of an object, a non-string field -- is
    deliberately treated as *no signal* rather than as an error. This function
    exists to answer "is some other package manager definitely in charge?",
    and a package.json we cannot parse is not evidence that one is. Crashing
    detection over a broken package.json would also be a strictly worse
    outcome than the bug it guards against: the repo would get no scaffold and
    no diagnosis, instead of a scaffold plus whatever the lockfile check says.
    The lockfile markers are checked independently, so a repo with a corrupt
    package.json AND a pnpm-lock.yaml is still correctly refused.
    """
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    declared = data.get("packageManager")
    if not isinstance(declared, str) or not declared.strip():
        return None
    # Split on the FIRST "@" only: scoped names are not legal here, but a
    # version like "pnpm@9.12.0+sha512..." must not confuse the name.
    return declared.split("@", 1)[0].strip().lower()


def _node_unsupported_reason(root):
    """Return why rigging cannot drive this repo's node stack, or None."""
    for filename, manager in stacks.FOREIGN_NODE_LOCKFILES.items():
        # is_file, not exists, for the same reason detect_stacks uses it: a
        # *directory* named `yarn.lock` records no dependency graph, and
        # refusing to scaffold off one would be as wrong as scaffolding off
        # one.
        if (root / filename).is_file():
            return (
                f"found {filename} at the repo root, which means this project's "
                f"dependencies are managed by {manager}, not "
                f"{stacks.NODE_PACKAGE_MANAGER}. rigging's node stack runs "
                f"`npm ci` then `npm test`, and `npm ci` fails outright without "
                f"a package-lock.json -- so the workflow rigging would write "
                f"here could never go green, no matter what the project's own "
                f"tests do. rigging will not scaffold a workflow that cannot "
                f"pass."
            )

    declared = _declared_package_manager(root)
    if declared is not None and declared != stacks.NODE_PACKAGE_MANAGER:
        return (
            f"found a `packageManager` field in package.json naming "
            f"{declared}, which means this project is driven by {declared}, not "
            f"{stacks.NODE_PACKAGE_MANAGER}. rigging's node stack runs "
            f"`npm ci` then `npm test`, and neither line works under "
            f"{declared} -- so the workflow rigging would write here could "
            f"never go green, no matter what the project's own tests do. "
            f"rigging will not scaffold a workflow that cannot pass."
        )
    return None


#: Per-stack "can rigging actually drive this?" checks, keyed by stack id.
#: A stack with no entry here has nothing that can disqualify it today
#: (python's steps are tolerant by construction -- they install pytest
#: themselves and treat requirements.txt as optional).
_UNSUPPORTED_CHECKS = {
    "node": _node_unsupported_reason,
}


def unsupported_reasons(root) -> dict[str, str]:
    """Return {stack_id: reason} for each DETECTED stack rigging cannot drive.

    An empty dict means every detected stack is drivable and init may proceed
    normally; this is the overwhelmingly common case, and the function is
    written so that the absent-signal path costs nothing.

    Note what this does NOT do: it does not remove anything from
    `detect_stacks`. Silently dropping node from detection would leave a
    JavaScript repo with a python-only workflow (or no workflow at all) and no
    statement anywhere about why -- the exact "quietly did something other
    than what you asked" failure this codebase refuses everywhere else. The
    stack is still detected and still reported; the reason travels alongside
    it, and the caller (the init skill) is what stops. Keeping the two
    separate also means a future increment that teaches rigging to drive pnpm
    deletes a reason and changes nothing about detection.
    """
    root = Path(root)
    reasons = {}
    for stack_id in detect_stacks(root):
        check = _UNSUPPORTED_CHECKS.get(stack_id)
        if check is None:
            continue
        reason = check(root)
        if reason is not None:
            reasons[stack_id] = reason
    return reasons
