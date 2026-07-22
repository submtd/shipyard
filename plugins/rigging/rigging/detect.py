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


def _package_json_parses(root):
    """True when package.json exists and parses as a JSON object.

    Used only to distinguish "parsed fine, and there is confirmedly no
    `packageManager` field" from "we could not read this file at all" --
    `_declared_package_manager` collapses both to None, which is correct for
    its own question ("is some other manager definitely in charge?") but not
    for the pnpm refusal below, which must fire on confirmed absence and
    stay silent on an unparseable file (not evidence of anything; the
    lockfile still decides).
    """
    path = root / "package.json"
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return False
    return isinstance(data, dict)


def _declared_yarn_major(root):
    """Return 1 or 2 for a declared yarn version, or None if undeclared.

    2 means "berry or later" -- every major from 2 up takes the same
    `--immutable` flag, so they need no further distinction.
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
    if not isinstance(declared, str) or "@" not in declared:
        return None
    name, _, version = declared.partition("@")
    if name.strip().lower() != "yarn":
        return None
    major = version.strip().split(".", 1)[0]
    if not major.isdigit():
        return None
    return 1 if int(major) == 1 else 2


def _yarn_id(root):
    """Which yarn toolchain, or None when it cannot be determined."""
    major = _declared_yarn_major(root)
    if major is None:
        return None
    return "yarn1" if major == 1 else "yarn-berry"


def node_package_manager(root):
    """Select the package manager driving this repo, or explain why not.

    Returns `(manager_id, reason)`; exactly one is non-None. `(None, None)`
    means there is no node stack here at all, which is not a refusal.

    Ambiguity is refused rather than resolved by precedence. Two different
    lockfiles at the root means the repo is mid-migration or carrying a stale
    file, and either answer is as likely to be wrong as right -- a wrong guess
    renders a workflow that dies on its install step, which is precisely the
    failure this module was built to prevent.
    """
    root = Path(root)
    if not (root / "package.json").is_file():
        return None, None

    found = {}
    for manager_id, manager in stacks.NODE_PACKAGE_MANAGERS.items():
        for lockfile in manager.lockfiles:
            if (root / lockfile).is_file():
                found.setdefault(lockfile, set()).add(manager_id)

    # yarn1 and yarn-berry share yarn.lock, so one lockfile mapping to both
    # is not ambiguity between managers -- it is one manager whose major is
    # still unknown. Collapse them before counting.
    families = set()
    for lockfile, ids in found.items():
        families.add("yarn" if ids <= {"yarn1", "yarn-berry"} else sorted(ids)[0])

    if len(families) > 1:
        names = ", ".join(sorted(found))
        return None, (
            f"found more than one package manager's lockfile at the repo "
            f"root ({names}). That means this project is mid-migration or "
            f"carrying a stale lockfile, and rigging will not guess which "
            f"one is authoritative -- the wrong guess renders a workflow "
            f"whose install step fails on every run. Remove the lockfile "
            f"that is no longer in use and re-run."
        )

    declared = _declared_package_manager(root)

    if families:
        family = next(iter(families))
        if declared is not None and declared != family:
            lockfile = next(iter(found))
            return None, (
                f"package.json declares `packageManager` as {declared}, but "
                f"the repo root has {lockfile}, which belongs to {family}. "
                f"rigging will not guess which one is authoritative; make "
                f"them agree and re-run."
            )
        if family == "yarn":
            yarn_id = _yarn_id(root)
            if yarn_id is None:
                return None, (
                    "found yarn.lock at the repo root, but nothing says which "
                    "yarn major this project uses. Yarn 1 installs with "
                    "`--frozen-lockfile` and Yarn 2+ with `--immutable`, and "
                    "each flag is an error on the other -- so rigging cannot "
                    "write an install step that works without knowing. Add a "
                    "`packageManager` field to package.json (e.g. "
                    "\"yarn@4.0.0\") and re-run."
                )
            return yarn_id, None
        if family == "pnpm" and declared != "pnpm" and _package_json_parses(root):
            # pnpm/action-setup takes its version from package.json's
            # `packageManager` field when no `version:` input is given, and
            # ERRORS when neither is present -- its README: "Optional when
            # there is a packageManager field in the package.json. otherwise,
            # this field is required". Selecting pnpm off the lockfile alone
            # would therefore render a workflow that fails on its setup step
            # every run.
            return None, (
                "found pnpm-lock.yaml at the repo root, but package.json has "
                "no `packageManager` field. The pnpm setup action reads the "
                "pnpm version from that field, and fails outright when it is "
                "missing and no version is pinned in the workflow -- so "
                "rigging would be writing a job that cannot get as far as "
                "installing anything. Add a `packageManager` field to "
                "package.json (e.g. \"pnpm@9.12.0\") and re-run."
            )
        return family, None

    # No lockfile. The declared field still decides, and a bare package.json
    # means npm: npm ships with node, so no other manager's marker IS the
    # signal.
    if declared == "yarn":
        yarn_id = _yarn_id(root)
        return (yarn_id, None) if yarn_id else (None, (
            "package.json declares yarn as its packageManager, but without a "
            "major version rigging cannot tell whether to install with "
            "`--frozen-lockfile` (Yarn 1) or `--immutable` (Yarn 2+). Pin it "
            "as e.g. \"yarn@4.0.0\" and re-run."
        ))
    if declared is not None and declared in stacks.NODE_PACKAGE_MANAGERS:
        return declared, None
    return stacks.DEFAULT_NODE_PACKAGE_MANAGER, None


def _node_unsupported_reason(root):
    """Return why rigging cannot drive this repo's node stack, or None."""
    _, reason = node_package_manager(root)
    return reason


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
