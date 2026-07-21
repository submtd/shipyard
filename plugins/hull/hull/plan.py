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
    permissions: str
    jobs: tuple[Job, ...]


def _build_job(scanner_id: str) -> Job:
    spec = scanners.REGISTRY[scanner_id]
    checkout_step = scanners.Step(
        uses="actions/checkout@11d5960a326750d5838078e36cf38b85af677262",
        uses_version="v4",
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
    return ScanPlan(name=cfg.name, permissions="contents: read", jobs=(job,))
