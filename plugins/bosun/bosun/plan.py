"""Build a Dependabot plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- same engine-purity invariant as rigging's plan.py and hull's plan.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from bosun import config, ecosystems


@dataclass(frozen=True)
class Update:
    """One Dependabot update entry for a configured ecosystem."""

    package_ecosystem: str
    directory: str
    interval: str
    #: The branch this update's PRs open against, or None to leave
    #: `target-branch` out of the rendered entry entirely. Carried per-Update
    #: even though config holds one repo-wide value, because that is the
    #: level Dependabot's own schema puts it at -- the plan mirrors the file
    #: it will become, and collapsing that here would make render() reach
    #: back up into config for it.
    target_branch: Optional[str] = None


@dataclass(frozen=True)
class DependabotPlan:
    """The full Dependabot plan: one update per configured ecosystem, in
    registry order."""

    version: int
    updates: tuple[Update, ...]


def build_plan(cfg: config.Config) -> DependabotPlan:
    updates = tuple(
        Update(
            package_ecosystem=ecosystems.REGISTRY[ecosystem_id].package_ecosystem,
            directory="/",
            interval=cfg.ecosystems[ecosystem_id].interval,
            target_branch=cfg.target_branch,
        )
        for ecosystem_id in ecosystems.REGISTRY
        if ecosystem_id in cfg.ecosystems
    )
    return DependabotPlan(version=2, updates=updates)
