"""Build a CI plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- a later task enforces this invariant over the whole engine via an AST
test.
"""
from __future__ import annotations

from dataclasses import dataclass

from rigging import config, stacks

CHECKOUT_STEP = stacks.Step(uses="actions/checkout@v4")


@dataclass(frozen=True)
class Job:
    """One CI job for a configured stack."""

    id: str
    runs_on: str
    matrix_var: str
    versions: tuple[str, ...]
    steps: tuple[stacks.Step, ...]


@dataclass(frozen=True)
class CiPlan:
    """The full CI plan: one job per configured stack, in config order."""

    name: str
    jobs: tuple[Job, ...]


def _build_job(stack_id: str, versions: tuple[str, ...]) -> Job:
    spec = stacks.REGISTRY[stack_id]
    setup_step = stacks.Step(
        uses=spec.setup_uses,
        with_={spec.setup_with_key: "${{ matrix.%s }}" % spec.matrix_var},
    )
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        matrix_var=spec.matrix_var,
        versions=versions,
        steps=(CHECKOUT_STEP, setup_step, *spec.steps),
    )


def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, versions) for stack_id, versions in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs)
