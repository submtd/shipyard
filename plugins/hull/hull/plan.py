"""Build a scan plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- same engine-purity invariant as rigging's plan.py.
"""
from __future__ import annotations

from dataclasses import dataclass

from hull import config, scanners


@dataclass(frozen=True)
class Job:
    """One scan job for the configured scanner. No matrix -- a scanner run
    is a single pass over the repo, not one per version."""

    id: str
    runs_on: str
    steps: tuple[scanners.Step, ...]


@dataclass(frozen=True)
class ScanPlan:
    """The full scan plan: one job for the configured scanner."""

    name: str
    permissions: tuple[str, ...]
    jobs: tuple[Job, ...]
    #: Branches whose pushes trigger the workflow. See config.Config.
    push_branches: tuple[str, ...] = config.DEFAULT_PUSH_BRANCHES


#: The checkout pin, named rather than inlined so tests (and
#: scripts/sync_action_pins.py) have one place to read it from. rigging's
#: plan.py has had CHECKOUT_STEP for the same reason; hull inlining it is
#: why hull's tests used to restate the SHA literal in four places.
CHECKOUT_USES = "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"
CHECKOUT_VERSION = "v7"


def _build_job(scanner_id: str) -> Job:
    spec = scanners.REGISTRY[scanner_id]
    checkout_step = scanners.Step(
        uses=CHECKOUT_USES,
        uses_version=CHECKOUT_VERSION,
        with_={"fetch-depth": spec.checkout_fetch_depth},
    )
    scan_step = scanners.Step(uses=spec.action_ref, env=spec.env,
                              uses_version=spec.action_ref_version)
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        steps=(checkout_step, scan_step),
    )


def build_plan(cfg: config.Config) -> ScanPlan:
    job = _build_job(cfg.scanner)
    return ScanPlan(name=cfg.name,
                    permissions=scanners.REGISTRY[cfg.scanner].permissions,
                    jobs=(job,),
                    push_branches=cfg.push_branches)
