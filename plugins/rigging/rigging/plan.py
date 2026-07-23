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
    """The setup, post-setup, and INSTALL steps a stack's package manager
    contributes. The test step is resolved separately (see _resolve_test_argv)
    so a testCommand can override it. Returns ((), (), ()) for a stack with no
    manager concept -- today every stack but node.
    """
    if stack_id != "node":
        return (), (), ()
    manager = stacks.NODE_PACKAGE_MANAGERS[manager_id]
    install_run = (stacks.Step(run=render_argv(manager.install)),)
    return manager.setup_steps, manager.post_setup_steps, install_run


def _resolve_test_argv(stack_id: str, manager_id: str,
                       test_command: tuple[str, ...] | None) -> tuple[str, ...]:
    """The effective test argv for a job: an explicit testCommand wins; else
    the node manager's default; else the stack's own default_test."""
    if test_command is not None:
        return test_command
    if stack_id == "node":
        return stacks.NODE_PACKAGE_MANAGERS[manager_id].test
    return stacks.REGISTRY[stack_id].default_test


def _build_job(stack_id: str, versions: tuple[str, ...],
               manager_id: str = stacks.DEFAULT_NODE_PACKAGE_MANAGER,
               test_command: tuple[str, ...] | None = None) -> Job:
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
    manager_setup, manager_post_setup, manager_install = _manager_steps(stack_id, manager_id)
    test_argv = _resolve_test_argv(stack_id, manager_id, test_command)
    # An empty test argv would render `- run: ""` -- a silent no-op test step,
    # a green-but-testless workflow. It is unreachable today (python's
    # default_test is non-empty; node resolves via a manager whose test is
    # non-empty), so this asserts the invariant rather than handling a live
    # case: a future non-node stack registered without a default_test fails
    # loudly here instead of shipping CI that tests nothing.
    assert test_argv, f"{stack_id}: no test command resolved (empty test argv)"
    test_step = stacks.Step(run=render_argv(test_argv))
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        matrix_var=spec.matrix_var,
        versions=versions,
        steps=(
            CHECKOUT_STEP, *manager_setup, setup_step,
            *manager_post_setup, *spec.steps, *manager_install, test_step,
        ),
    )


def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, stack_cfg.versions,
                   stack_cfg.package_manager or stacks.DEFAULT_NODE_PACKAGE_MANAGER,
                   stack_cfg.test_command)
        for stack_id, stack_cfg in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
