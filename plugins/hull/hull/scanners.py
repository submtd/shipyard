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
    with_: Optional[dict] = None
    run: Optional[str] = None
    env: Optional[dict] = None


@dataclass(frozen=True)
class ScannerSpec:
    """Everything needed to scaffold a secret-scanner's CI job."""

    id: str
    action_ref: str
    checkout_fetch_depth: str
    env: dict


REGISTRY: dict[str, ScannerSpec] = {
    "gitleaks": ScannerSpec(
        id="gitleaks",
        action_ref="gitleaks/gitleaks-action@v2",
        checkout_fetch_depth="0",
        env={"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"},
    ),
}

SCANNER_IDS: tuple[str, ...] = tuple(REGISTRY)
