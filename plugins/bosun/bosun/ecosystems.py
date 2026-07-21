"""The ecosystem registry: known dependency ecosystems and how to configure
Dependabot for them.

Pure data module. Stdlib only; no subprocess, no os, no networking -- same
engine-purity invariant as rigging's stacks.py and hull's scanners.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EcosystemSpec:
    """Everything needed to detect an ecosystem and configure its
    Dependabot update entry."""

    id: str
    package_ecosystem: str
    detect_files: tuple[str, ...]
    always_on: bool


REGISTRY: dict[str, EcosystemSpec] = {
    "githubActions": EcosystemSpec(
        id="githubActions",
        package_ecosystem="github-actions",
        detect_files=(),
        always_on=True,
    ),
    "python": EcosystemSpec(
        id="python",
        package_ecosystem="pip",
        detect_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        always_on=False,
    ),
    "node": EcosystemSpec(
        id="node",
        package_ecosystem="npm",
        detect_files=("package.json",),
        always_on=False,
    ),
}

ECOSYSTEM_IDS: tuple[str, ...] = tuple(REGISTRY)
INTERVALS: tuple[str, ...] = ("daily", "weekly", "monthly")
