"""Build a CI plan from validated config.

Pure data transformation. Stdlib only; no subprocess, no os, no networking
-- a later task enforces this invariant over the whole engine via an AST
test.
"""
from __future__ import annotations

import shlex
from dataclasses import dataclass

from rigging import config, stacks

CHECKOUT_STEP = stacks.Step(
    uses="actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
    uses_version="v7",
)


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
    #: Branches whose pushes trigger the workflow. See config.Config.
    push_branches: tuple[str, ...] = config.DEFAULT_PUSH_BRANCHES


def render_argv(argv: tuple[str, ...]) -> str:
    """Render an argv tuple as one shell line, quoting each element.

    `shlex.quote` is what makes a metacharacter inert, but note what it does
    NOT do: GitHub substitutes `${{ ... }}` at the YAML layer, before any
    shell sees the line, so quoting is no defence against an Actions
    expression. That is rejected at validation instead -- quoting handles the
    shell, and the shell is not the only reader of this string.
    """
    return " ".join(shlex.quote(part) for part in argv)


def _manager_steps(stack_id: str, manager_id: str):
    """The setup and run steps contributed by a stack's package manager.

    Returns `((), (), ())` for a stack that has no manager concept -- today
    every stack but node.
    """
    if stack_id != "node":
        return (), (), ()
    manager = stacks.NODE_PACKAGE_MANAGERS[manager_id]
    runs = (
        stacks.Step(run=render_argv(manager.install)),
        stacks.Step(run=render_argv(manager.test)),
    )
    return manager.setup_steps, manager.post_setup_steps, runs


def _build_job(stack_id: str, versions: tuple[str, ...],
               manager_id: str = stacks.DEFAULT_NODE_PACKAGE_MANAGER) -> Job:
    spec = stacks.REGISTRY[stack_id]
    setup_step = stacks.Step(
        uses=spec.setup_uses,
        uses_version=spec.setup_uses_version,
        with_={spec.setup_with_key: "${{ matrix.%s }}" % spec.matrix_var},
    )
    # The manager's own installer runs before setup-node, matching pnpm's
    # documented order. Nothing here depends on it today (no dependency
    # caching is configured), but the documented order is the one that stays
    # correct if caching is ever added.
    manager_setup, manager_post_setup, manager_runs = _manager_steps(stack_id, manager_id)
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        matrix_var=spec.matrix_var,
        versions=versions,
        steps=(
            CHECKOUT_STEP, *manager_setup, setup_step,
            *manager_post_setup, *spec.steps, *manager_runs,
        ),
    )


def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, stack_cfg.versions,
                   stack_cfg.package_manager or stacks.DEFAULT_NODE_PACKAGE_MANAGER)
        for stack_id, stack_cfg in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
