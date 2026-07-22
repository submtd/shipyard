"""The scanner registry: known secret-scanning tools and how to CI them.

Pure data module. Stdlib only; no subprocess, no os, no networking -- same
engine-purity invariant as rigging's stacks.py and ballast's stacks.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Step:
    """One workflow step. Either `uses` (an action) or `run` (a shell line).

    Shared step shape with rigging's `Step`, plus `env` -- a scanner action
    (like gitleaks) needs a step-scoped environment mapping (e.g.
    GITHUB_TOKEN) that rigging's stack steps never did.
    """

    name: Optional[str] = None
    uses: Optional[str] = None
    #: Human-readable tag for a SHA-pinned `uses`, rendered as a trailing
    #: YAML comment (`# v4`). It must stay OUTSIDE the quoted scalar --
    #: inside, it becomes part of the ref and the action fails to resolve.
    #: A registry constant, never user input, so it cannot carry injection.
    uses_version: Optional[str] = None
    with_: Optional[dict] = None
    run: Optional[str] = None
    env: Optional[dict] = None


@dataclass(frozen=True)
class ScannerSpec:
    """Everything needed to scaffold a secret-scanner's CI job."""

    id: str
    action_ref: str
    #: The tag the pinned action_ref SHA corresponds to, rendered as a
    #: trailing comment so the pin stays readable and Dependabot can bump
    #: both together.
    action_ref_version: str
    checkout_fetch_depth: str
    env: dict
    #: Workflow-level GITHUB_TOKEN scopes this scanner needs, least-privilege.
    #: Declared per scanner rather than fixed at the plan, because what a
    #: scanner reads is a property of the scanner: gitleaks enumerates a PR's
    #: commits via GET /repos/{o}/{r}/pulls/{n}/commits, which `contents:
    #: read` does not grant -- without `pull-requests: read` every
    #: pull_request run fails with 403 "Resource not accessible by
    #: integration". Read scopes only; see test_permissions_stay_least_privilege.
    permissions: tuple[str, ...] = ("contents: read",)
    #: The environment variable this scanner reads its LICENSE KEY from, or
    #: None when the scanner has no license gate at all. This is a property
    #: of the tool, not of the repo, so it belongs in the registry beside the
    #: action pin rather than in config.py -- config only decides WHICH
    #: secret name gets piped into it, and it needs this field to know
    #: whether piping anything in is even meaningful (see
    #: config._valid_license_secret, which rejects `licenseSecret` outright
    #: for a scanner whose license_env is None, rather than accepting a
    #: setting that would silently do nothing). Only the NAME lives here; the
    #: value is never a literal, it is always a `${{ secrets.<NAME> }}`
    #: reference assembled in plan.py, so no key material can ever end up in
    #: this registry or in a rendered workflow.
    license_env: Optional[str] = None
    #: The scan step's `with:` mapping, or None when the scanner needs no
    #: inputs at all. A registry constant, never user input -- which is what
    #: keeps it outside the injection surface: `with:` values are rendered as
    #: quoted YAML scalars exactly like `env:` values, but unlike
    #: `licenseSecret` nothing here is derived from .hull.json, so no
    #: validation is required for it and none is implied. A scanner needing a
    #: user-supplied `with:` value would be a genuinely new decision, not an
    #: extension of this one.
    scan_with: Optional[dict] = None


REGISTRY: dict[str, ScannerSpec] = {
    "gitleaks": ScannerSpec(
        id="gitleaks",
        action_ref="gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e",
        action_ref_version="v3",
        checkout_fetch_depth="0",
        env={"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"},
        permissions=("contents: read", "pull-requests: read"),
        # gitleaks-action v3 hard-exits (status 1, before scanning anything)
        # when the repository's owner is a GitHub Organization and
        # GITLEAKS_LICENSE is unset -- public or private, it makes no
        # difference. Naming the variable here is what lets hull both render
        # the license through to the action and refuse, at init time, to
        # scaffold a workflow that provably cannot go green.
        license_env="GITLEAKS_LICENSE",
    ),
    "trufflehog": ScannerSpec(
        id="trufflehog",
        action_ref="trufflesecurity/trufflehog@27b0417c16317ca9a472a9a8092acce143b49c55",
        action_ref_version="v3.95.9",
        checkout_fetch_depth="0",
        # Nothing to pass: trufflehog needs no token and no license, which is
        # the entire reason this entry exists. The renderer omits a falsy
        # env rather than emitting an empty mapping.
        env={},
        # Narrower than gitleaks deliberately, and not an oversight: this
        # action reads base and head from the event payload instead of
        # enumerating a pull request's commits through the API, and that API
        # call is exactly why gitleaks additionally needs pull-requests:read.
        permissions=("contents: read",),
        # AGPL 3.0 open source, no license key, no organization gate. This is
        # the property the whole entry exists for -- see check_preconditions,
        # which keys its organization blocker off license_env being set.
        license_env=None,
        # trufflehog's own documented recommendation. `verified` means the
        # credential was live-tested and works; `unknown` means it has no
        # verifier for that shape and could not test it. Both are reported
        # because a secret the tool CANNOT verify is exactly the kind it
        # should not stay quiet about -- in a private repo, internal and
        # custom token formats are often most of them. `unverified` is
        # excluded: reporting everything trains a team to ignore the check,
        # which is the failure mode the organization blocker exists to
        # prevent in the first place.
        scan_with={"extra_args": "--results=verified,unknown"},
    ),
}

SCANNER_IDS: tuple[str, ...] = tuple(REGISTRY)
