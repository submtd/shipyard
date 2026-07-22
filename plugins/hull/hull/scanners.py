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


REGISTRY: dict[str, ScannerSpec] = {
    "gitleaks": ScannerSpec(
        id="gitleaks",
        action_ref="gitleaks/gitleaks-action@e0c47f4f8be36e29cdc102c57e68cb5cbf0e8d1e",
        action_ref_version="v3",
        checkout_fetch_depth="0",
        env={"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"},
        permissions=("contents: read", "pull-requests: read"),
    ),
}

SCANNER_IDS: tuple[str, ...] = tuple(REGISTRY)
