"""Config -> ScanPlan tests.

Mirrors rigging/tests/test_plan.py's shape. Also asserts the injection
invariant specific to hull: the only reachable `${{ ... }}` expression in
the whole plan is the whitelisted GITHUB_TOKEN secret sitting in a step's
`env` -- never in a `run` body and never a bare `github.*` context
expression.
"""
from __future__ import annotations

import pytest

from hull.config import Config
from hull.plan import CHECKOUT_USES, CHECKOUT_VERSION, Job, ScanPlan, build_plan
from hull.scanners import REGISTRY, Step


def test_build_plan_yields_one_gitleaks_job():
    cfg = Config(name="security", scanner="gitleaks")
    plan = build_plan(cfg)

    assert isinstance(plan, ScanPlan)
    assert plan.name == "security"
    assert plan.permissions == "contents: read"
    assert len(plan.jobs) == 1

    job = plan.jobs[0]
    assert isinstance(job, Job)
    assert job.id == "gitleaks"
    assert job.runs_on == "ubuntu-latest"
    assert not hasattr(job, "matrix_var")
    assert not hasattr(job, "versions")


def test_job_steps_are_checkout_then_scanner_in_order():
    cfg = Config(name="security", scanner="gitleaks")
    job = build_plan(cfg).jobs[0]
    spec = REGISTRY["gitleaks"]

    assert job.steps == (
        Step(uses=CHECKOUT_USES, uses_version=CHECKOUT_VERSION,
             with_={"fetch-depth": "0"}),
        Step(uses=spec.action_ref, env=spec.env,
             uses_version=spec.action_ref_version),
    )


def test_checkout_step_fetch_depth_matches_spec():
    cfg = Config(name="security", scanner="gitleaks")
    job = build_plan(cfg).jobs[0]
    assert job.steps[0].with_ == {"fetch-depth": "0"}


def test_gitleaks_step_env_whitelists_github_token():
    cfg = Config(name="security", scanner="gitleaks")
    job = build_plan(cfg).jobs[0]
    assert job.steps[1].env == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}


def test_build_plan_is_deterministic():
    cfg = Config(name="security", scanner="gitleaks")
    assert build_plan(cfg) == build_plan(cfg)


def test_only_reachable_expression_is_whitelisted_github_token():
    """No run step, and no bare `github.*` context expression, anywhere in
    the plan -- the only `${{ ... }}` reachable is the GITHUB_TOKEN secret
    confined to a step's env mapping."""
    cfg = Config(name="security", scanner="gitleaks")
    plan = build_plan(cfg)

    expressions_found = []
    for job in plan.jobs:
        for step in job.steps:
            assert step.run is None
            if step.env:
                for value in step.env.values():
                    if "${{" in value:
                        expressions_found.append(value)
            if step.with_:
                for value in step.with_.values():
                    if isinstance(value, str) and "${{" in value:
                        expressions_found.append(value)

    assert expressions_found == ["${{ secrets.GITHUB_TOKEN }}"]
    assert "github." not in expressions_found[0]


def test_scanplan_is_frozen_dataclass():
    cfg = Config(name="security", scanner="gitleaks")
    plan = build_plan(cfg)
    with pytest.raises(Exception):
        plan.name = "changed"


def test_job_is_frozen_dataclass():
    cfg = Config(name="security", scanner="gitleaks")
    job = build_plan(cfg).jobs[0]
    with pytest.raises(Exception):
        job.id = "changed"
