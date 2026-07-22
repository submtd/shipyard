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


class _Unparseable:
    """Sentinel: package.json exists but could not be read or parsed as a
    JSON object (unreadable bytes, malformed JSON, or a top-level value that
    is not an object, e.g. an array)."""

    def __repr__(self):
        return "UNPARSEABLE"


#: Returned by `_package_json` when package.json exists but is not usable.
#: A bare `None` cannot carry this distinction from "no package.json file at
#: all" -- and callers need exactly that distinction (see `_package_json`'s
#: docstring) -- so this is a dedicated sentinel rather than another falsy
#: value that would collapse back into the same ambiguity.
UNPARSEABLE = _Unparseable()


def _package_json(root):
    """Parse package.json once, in one place.

    Returns:
      - a `dict`, when package.json exists and parses as a JSON object
      - `None`, when there is no package.json file at root
      - `UNPARSEABLE`, when package.json exists but is unreadable, is not
        valid JSON, or parses to something other than a JSON object

    `_declared_package_manager`, `_declared_yarn_major`, and the pnpm branch
    of `node_package_manager` all used to open, read, and `json.loads`
    package.json independently, with the same try/except -- three chances
    for the parsing to drift apart. This is the one place that does it now.

    The three-way return matters: "absent" and "unparseable" are different
    facts (one names nothing, corepack's config can't exist; the other names
    a file the pnpm setup action will fail trying to read) and callers that
    need to react differently to each -- see the pnpm branch in
    `node_package_manager` -- cannot do so if both collapse to the same
    `None`.
    """
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return UNPARSEABLE
    if not isinstance(data, dict):
        return UNPARSEABLE
    return data


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
    The lockfile markers are checked independently: a repo with a corrupt
    package.json and a pnpm-lock.yaml is refused too, but by that separate
    check (which diagnoses the parse failure by name), not by this function
    returning None.
    """
    data = _package_json(root)
    if not isinstance(data, dict):
        return None
    declared = data.get("packageManager")
    if not isinstance(declared, str) or not declared.strip():
        return None
    # Split on the FIRST "@" only: scoped names are not legal here, but a
    # version like "pnpm@9.12.0+sha512..." must not confuse the name.
    return declared.split("@", 1)[0].strip().lower()


def _declared_package_manager_version(root):
    """Return the version component of package.json's `packageManager`
    field (everything after the first `@`, stripped), or None when the
    field is absent, has no `@`, or the version component is empty.

    `_declared_package_manager` deliberately discards this -- it only ever
    needed the name. pnpm needs the version too: `pnpm/action-setup` reads
    the pnpm version to install from this exact field, and a bare `"pnpm"`
    or trailing-`@` `"pnpm@"` names the manager without giving that action
    anything to resolve. This is the version-half of that same field, kept
    as its own function rather than folded into `_declared_package_manager`
    so a bare name and a versioned one stay distinguishable to callers that
    care (today: only the pnpm branches of `node_package_manager`).
    """
    data = _package_json(root)
    if not isinstance(data, dict):
        return None
    declared = data.get("packageManager")
    if not isinstance(declared, str) or "@" not in declared:
        return None
    _, _, version = declared.partition("@")
    version = version.strip()
    return version or None


def _declared_yarn_major(root):
    """Return 1 or 2 for a declared yarn version, or None if undeclared.

    2 means "berry or later" -- every major from 2 up takes the same
    `--immutable` flag, so they need no further distinction.
    """
    data = _package_json(root)
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
            # Name every lockfile found, not just an arbitrary one -- more
            # than one can be present (e.g. bun.lockb and bun.lock), and the
            # message has to stay accurate in that case too.
            lockfiles = ", ".join(sorted(found))
            verb = "belongs" if len(found) == 1 else "belong"
            return None, (
                f"package.json declares `packageManager` as {declared}, but "
                f"the repo root has {lockfiles}, which {verb} to {family}. "
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
        if family == "pnpm" and declared != "pnpm":
            # pnpm/action-setup takes its version from package.json's
            # `packageManager` field when no `version:` input is given, and
            # ERRORS when neither is present -- its README: "Optional when
            # there is a packageManager field in the package.json. otherwise,
            # this field is required". Selecting pnpm off the lockfile alone
            # would therefore render a workflow that fails on its setup step
            # every run. That is exactly as true of a package.json the
            # action-setup step cannot even read a field from, so an
            # unparseable file refuses too -- with its own diagnosis, since
            # the fix (a valid file) differs from the fix for a parseable
            # file that is merely missing the field.
            parsed = _package_json(root)
            if not isinstance(parsed, dict):
                return None, (
                    "found pnpm-lock.yaml at the repo root, but package.json "
                    "could not be parsed. The pnpm setup action reads the "
                    "pnpm version from package.json's `packageManager` "
                    "field, and cannot read that field from a file it "
                    "cannot parse -- so rigging would be writing a job that "
                    "cannot get as far as installing anything. Fix "
                    "package.json so it is valid JSON with a "
                    "`packageManager` field (e.g. \"pnpm@9.12.0\") and "
                    "re-run."
                )
            return None, (
                "found pnpm-lock.yaml at the repo root, but package.json has "
                "no `packageManager` field. The pnpm setup action reads the "
                "pnpm version from that field, and fails outright when it is "
                "missing and no version is pinned in the workflow -- so "
                "rigging would be writing a job that cannot get as far as "
                "installing anything. Add a `packageManager` field to "
                "package.json (e.g. \"pnpm@9.12.0\") and re-run."
            )
        if family == "pnpm" and not _declared_package_manager_version(root):
            # declared == "pnpm" here (the branch above already handled
            # every case where it doesn't), so the field names pnpm but
            # carries no version -- e.g. `"packageManager": "pnpm"` or
            # `"pnpm@"`. That satisfies "declares pnpm" but gives
            # pnpm/action-setup nothing to resolve, which is the same
            # failure as the missing-field case above, just with a
            # different fix.
            return None, (
                "found pnpm-lock.yaml at the repo root, and package.json "
                "declares `packageManager` as pnpm, but it pins no version "
                "(e.g. \"pnpm\" or \"pnpm@\" instead of \"pnpm@9.12.0\"). "
                "The pnpm setup action reads the pnpm version from that "
                "field, and fails outright when it cannot resolve one -- so "
                "rigging would be writing a job that cannot get as far as "
                "installing anything. Pin a version in package.json's "
                "`packageManager` field (e.g. \"pnpm@9.12.0\") and re-run."
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
    if declared is not None and declared not in stacks.NODE_PACKAGE_MANAGERS:
        # A declared manager rigging cannot drive is not "no signal" -- it is
        # a definite instruction rigging cannot follow. Falling through to
        # npm here would render an `npm ci` workflow for a repo whose
        # dependencies npm never installed, silently doing something other
        # than what the repo asked for.
        known = ", ".join(sorted(stacks.NODE_PACKAGE_MANAGERS))
        return None, (
            f"package.json declares `packageManager` as {declared}, but "
            f"rigging does not know how to drive that package manager. It "
            f"can drive: {known}. Use one of those, or open an issue if "
            f"{declared} should be supported."
        )
    if declared == "pnpm" and not _declared_package_manager_version(root):
        # No lockfile at all yet, but the field already names pnpm without a
        # version -- e.g. a freshly `pnpm init`ed repo before the first
        # install. Same failure as the lockfile-present case above (nothing
        # for pnpm/action-setup to resolve), so it gets the same refusal
        # rather than silently falling through to npm.
        return None, (
            "package.json declares `packageManager` as pnpm, but it pins no "
            "version (e.g. \"pnpm\" or \"pnpm@\" instead of \"pnpm@9.12.0\"). "
            "The pnpm setup action reads the pnpm version from that field, "
            "and fails outright when it cannot resolve one -- so rigging "
            "would be writing a job that cannot get as far as installing "
            "anything. Pin a version in package.json's `packageManager` "
            "field (e.g. \"pnpm@9.12.0\") and re-run."
        )
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
