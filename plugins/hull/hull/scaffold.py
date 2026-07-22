"""Pure helpers for hull:init. No subprocess, no git/gh -- the skill gathers
signals and does I/O; this module maps data to data and reads the
filesystem via pathlib only."""
from __future__ import annotations

from pathlib import Path
from typing import NamedTuple

from hull.config import BRANCH_RE, NAME_RE, SECRET_NAME_RE
from hull.scanners import REGISTRY, SCANNER_IDS


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
SIGNAL_KEYS = frozenset({"name", "scanner", "pushBranches", "licenseSecret"})


#: The signals `check_preconditions` understands: everything `propose_config`
#: takes, plus `ownerType`. `ownerType` is deliberately NOT in SIGNAL_KEYS --
#: it is an observation about the remote repository, not a setting, and it has
#: no home in .hull.json. Keeping it out of SIGNAL_KEYS means propose_config
#: still rejects it loudly if it is ever handed the precondition dict by
#: mistake, which is the failure a caller most wants to hear about rather than
#: silently ignore.
PRECONDITION_SIGNAL_KEYS = SIGNAL_KEYS | {"ownerType"}


#: The exact string `gh repo view --json owner -q .owner.type` prints for an
#: organization-owned repo. Named rather than inlined at the comparison below
#: because the org blocker turns on this literal matching exactly, and the
#: domain check turns on the same set -- one constant means the guard and the
#: validation cannot come to disagree about what "an organization" is.
OWNER_TYPE_ORGANIZATION = "Organization"

#: Every value `ownerType` may take, None aside. Enforced as a DOMAIN, not
#: merely as a type: the blocker below fires on an exact match against
#: OWNER_TYPE_ORGANIZATION, so a near-miss like "organization" or "org" would
#: sail through an isinstance check, produce no blockers, and silently disable
#: the one guard standing between an org-owned repo and a workflow that cannot
#: pass -- with nothing left on disk afterwards to notice it by. That is the
#: same failure PRECONDITION_SIGNAL_KEYS exists to prevent for the signal's
#: NAME; the value deserves the same treatment, and the caller here is a skill
#: reading prose, which is exactly the caller most likely to lower-case it.
OWNER_TYPES = frozenset({OWNER_TYPE_ORGANIZATION, "User"})


def _reject_unknown(signals, allowed):
    if not isinstance(signals, dict):
        raise ValueError(f"signals must be a dict (got {signals!r}).")
    unknown = set(signals) - allowed
    if unknown:
        raise ValueError(
            f"unknown signal key(s) {', '.join(sorted(unknown))}. "
            f"Allowed keys: {', '.join(sorted(allowed))}."
        )


def _reject_unknown_signals(signals):
    _reject_unknown(signals, SIGNAL_KEYS)


def _valid_license_secret(signals):
    """Validate an optional `licenseSecret` signal, returning it or None.

    Same regex the config loader applies (config.SECRET_NAME_RE), for the same
    reason propose_config re-validates `name` and `scanner`: this function's
    contract is that valid signals produce a config load_config will accept,
    and this particular value is the one that ends up inside a
    `${{ secrets.<NAME> }}` expression in the rendered YAML. Validating it in
    both places is not redundancy for its own sake -- it is the difference
    between a caller learning about a bad value now, in front of the user,
    and learning about it after .hull.json has already been written.
    """
    secret = signals.get("licenseSecret")
    if secret is None:
        return None
    if not isinstance(secret, str) or not SECRET_NAME_RE.fullmatch(secret):
        raise ValueError(
            f"signals['licenseSecret'] must be a GitHub Actions secret name "
            f"matching {SECRET_NAME_RE.pattern} (got {secret!r})."
        )
    return secret


def propose_config(signals):
    """Map detected repository signals to a .hull.json dict.

    `signals` may set `name` (default "security"), `scanner` (default
    "gitleaks"), `pushBranches` (omitted when absent) and `licenseSecret`
    (omitted when absent -- the name of the Actions secret holding the
    scanner's license key, which `check_preconditions` will demand for an
    organization-owned repo). All are validated against config.py's own validators
    (NAME_RE, SCANNER_IDS) before the dict is built. Valid signals in -> a
    dict guaranteed to load via config.load_config (enforced by test).
    Invalid signals raise ValueError -- naming the bad field -- before
    anything is returned, so a caller can never persist a config that hull
    itself would reject.
    """
    _reject_unknown_signals(signals)
    name = signals.get("name", "security")
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"signals['name'] must be a string matching {NAME_RE.pattern} "
            f"(got {name!r})."
        )

    scanner = signals.get("scanner", "gitleaks")
    if not isinstance(scanner, str) or scanner not in SCANNER_IDS:
        raise ValueError(
            f"signals['scanner'] must be one of {', '.join(SCANNER_IDS)} "
            f"(got {scanner!r})."
        )

    out = {"name": name, "scanner": scanner}
    push_branches = _valid_push_branches(signals)
    if push_branches is not None:
        out["pushBranches"] = push_branches
    # Omitted entirely when not signalled, for the same reason pushBranches
    # is: absent means "hull has nothing to pass", and writing an explicit
    # null would put a key in every scaffolded .hull.json that the loader
    # then has to treat as if it were missing anyway.
    license_secret = _valid_license_secret(signals)
    if license_secret is not None:
        out["licenseSecret"] = license_secret
    return out


class Preconditions(NamedTuple):
    """The result of `check_preconditions`, with the two channels kept apart.

    They are separated because they demand different behaviour from the
    caller, and collapsing them into one list of strings would leave the skill
    guessing which is which:

    - `blockers` are conditions under which the workflow hull would write
      CANNOT pass, no matter what the repository's code looks like. A
      non-empty `blockers` means: do not scaffold, show these verbatim, stop.
    - `advisories` are things the user must know but which do not make
      scaffolding wrong. They are reported alongside a successful init, never
      instead of it.

    Empty `blockers` (`()`) means clear to proceed.
    """

    blockers: tuple[str, ...] = ()
    advisories: tuple[str, ...] = ()


def check_preconditions(signals) -> Preconditions:
    """Decide whether scaffolding can produce a workflow that is able to pass.

    Pure: it is handed facts (`ownerType`, the chosen `scanner`, the chosen
    `licenseSecret`) and returns strings. It runs no `gh`, reads no network,
    and touches no filesystem -- the skill gathers `ownerType` with
    `gh repo view --json owner -q .owner.type` and passes the result in.

    `ownerType` is `"Organization"`, `"User"`, or None when it could not be
    determined (no remote yet, `gh` unauthenticated, offline). None is treated
    as "no blocker": refusing to scaffold because a lookup failed would make
    hull unusable exactly where it is most useful -- a brand new repo -- and
    the advisory channel still carries the caveat.

    Anything else -- including a near-miss like `"organization"` or `"org"` --
    raises ValueError rather than being read as "not an organization". The
    blocker fires on an exact match, so a silently-accepted variant would look
    like a clean check while leaving the guard switched off.

    Unknown signal keys raise ValueError, naming them, for the same reason
    propose_config does: a dropped signal here means a guard silently did not
    run, and there is nothing left on disk afterwards to notice it by.
    """
    _reject_unknown(signals, PRECONDITION_SIGNAL_KEYS)

    owner_type = signals.get("ownerType")
    # isinstance first: an unhashable value (a list, a dict) raises TypeError
    # rather than returning False from a frozenset membership test, and the
    # contract here is that bad signals raise ValueError naming the field.
    if owner_type is not None and (
        not isinstance(owner_type, str) or owner_type not in OWNER_TYPES
    ):
        raise ValueError(
            f"signals['ownerType'] must be "
            f"{' or '.join(repr(t) for t in sorted(OWNER_TYPES))}, or None "
            f"(got {owner_type!r}). Pass the value of "
            f"`gh repo view --json owner -q .owner.type` verbatim, or None if "
            f"the lookup failed -- a near-miss like 'organization' would "
            f"silently disable the organization guard rather than fail."
        )

    scanner = signals.get("scanner", "gitleaks")
    if not isinstance(scanner, str) or scanner not in SCANNER_IDS:
        raise ValueError(
            f"signals['scanner'] must be one of {', '.join(SCANNER_IDS)} "
            f"(got {scanner!r})."
        )
    license_secret = _valid_license_secret(signals)
    license_env = REGISTRY[scanner].license_env

    blockers: list[str] = []
    advisories: list[str] = []

    # The whole point of this guard. Without it, hull:init commits a workflow
    # that is red on its very first run, for a reason that has nothing to do
    # with the repo's code and is not stated anywhere in the file it wrote.
    if (owner_type == OWNER_TYPE_ORGANIZATION and license_env
            and license_secret is None):
        blockers.append(
            f"This repository is owned by a GitHub Organization, and the "
            f"{scanner} action requires a license key for organization-owned "
            f"repos (public or private alike). With no {license_env} in the "
            f"job's environment the action exits 1 before scanning anything, "
            f"so the workflow hull would write here cannot pass. Remedy: get "
            f"a free {scanner} license key, add it to this repository (or its "
            f"organization) as an Actions secret, and set \"licenseSecret\" in "
            f".hull.json to that secret's name (conventionally "
            f"\"{license_env}\") so hull renders it into the scan step -- or "
            f"choose a scanner with no license gate."
        )

    # Non-fatal, but it will look like a hull bug the first time someone sees
    # it, so it is said out loud at init rather than left to be discovered.
    if license_env is not None:
        advisories.append(
            f"Fork pull requests cannot read repository or organization "
            f"secrets -- GitHub withholds them from `pull_request` runs whose "
            f"head is a fork, by design, so an untrusted contributor cannot "
            f"exfiltrate them. {license_env} therefore arrives empty on a fork "
            f"PR, and the {scanner} job will fail on those PRs even once a "
            f"license secret is configured. If this repo accepts fork "
            f"contributions (keel's contributions setting of \"fork\" or "
            f"\"both\"), expect that red check and treat it as expected rather "
            f"than as a finding."
        )

    return Preconditions(tuple(blockers), tuple(advisories))


def SECURITY_FILES(name):
    """Candidate paths init may write, in the order it reports them.

    `name` is validated via config.NAME_RE.fullmatch as defense in depth:
    it flows into a workflow file path below, so a path-escaping name
    (e.g. "../evil") must never reach that join.
    """
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ValueError(
            f"name must be a string matching {NAME_RE.pattern} (got {name!r})."
        )
    return [".hull.json", f".github/workflows/{name}.yml"]


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
