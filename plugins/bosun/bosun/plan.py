"""Build a Dependabot plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- same engine-purity invariant as rigging's plan.py and hull's plan.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from bosun import config, ecosystems


@dataclass(frozen=True)
class Update:
    """One Dependabot update entry for a configured ecosystem."""

    package_ecosystem: str
    directory: str
    interval: str


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
        )
        for ecosystem_id in ecosystems.REGISTRY
        if ecosystem_id in cfg.ecosystems
    )
    return DependabotPlan(version=2, updates=updates)
