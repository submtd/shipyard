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
    assert plan.permissions == ("contents: read", "pull-requests: read")
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


# --- licenseSecret ---------------------------------------------------------
#
# Issue #24. When configured, the scan step's env gains the scanner's license
# env var pointing at the named secret; when not, the env must be byte-
# identical to what hull emitted before the key existed (the golden file is
# the other half of that proof).


def test_license_secret_adds_the_scanners_license_env_var():
    cfg = Config(name="security", scanner="gitleaks",
                 license_secret="GITLEAKS_LICENSE")
    job = build_plan(cfg).jobs[0]
    assert job.steps[1].env == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}",
        "GITLEAKS_LICENSE": "${{ secrets.GITLEAKS_LICENSE }}",
    }


def test_license_secret_name_may_differ_from_the_env_var_name():
    """The env var is fixed by the tool; the SECRET's name is the repo's
    choice, and an org that already stores the key under another name must
    not have to rename it."""
    cfg = Config(name="security", scanner="gitleaks",
                 license_secret="ORG_GITLEAKS_KEY")
    env = build_plan(cfg).jobs[0].steps[1].env
    assert env["GITLEAKS_LICENSE"] == "${{ secrets.ORG_GITLEAKS_KEY }}"


def test_github_token_keeps_its_position_when_a_license_is_added():
    """The license entry is APPENDED, so adopting licenseSecret shows up as
    added lines in the workflow diff rather than a reordering of it."""
    cfg = Config(name="security", scanner="gitleaks",
                 license_secret="GITLEAKS_LICENSE")
    env = build_plan(cfg).jobs[0].steps[1].env
    assert list(env) == ["GITHUB_TOKEN", "GITLEAKS_LICENSE"]


def test_env_is_unchanged_when_no_license_secret_is_configured():
    cfg = Config(name="security", scanner="gitleaks")
    assert build_plan(cfg).jobs[0].steps[1].env == REGISTRY["gitleaks"].env


def test_build_plan_does_not_mutate_the_registry_spec_env():
    """The plan copies the registry's env before adding to it -- mutating the
    shared spec would leak one repo's license secret name into every later
    plan built in the same process."""
    before = dict(REGISTRY["gitleaks"].env)
    build_plan(Config(name="security", scanner="gitleaks",
                      license_secret="GITLEAKS_LICENSE"))
    assert REGISTRY["gitleaks"].env == before


def test_license_plan_is_deterministic():
    cfg = Config(name="security", scanner="gitleaks",
                 license_secret="GITLEAKS_LICENSE")
    assert build_plan(cfg) == build_plan(cfg)


def test_scan_step_carries_the_specs_scan_with(monkeypatch):
    """The registry's scan_with reaches the rendered step rather than being
    dropped between plan and render. Staged with a patched registry because
    no scanner declares scan_with yet -- monkeypatch.setitem, matching how
    every other registry-staging test in this suite is written."""
    import dataclasses

    from hull import scanners

    withful = dataclasses.replace(scanners.REGISTRY["gitleaks"],
                                  scan_with={"extra_args": "--flag"})
    monkeypatch.setitem(scanners.REGISTRY, "gitleaks", withful)
    job = build_plan(Config(name="security", scanner="gitleaks")).jobs[0]
    assert job.steps[1].with_ == {"extra_args": "--flag"}


def test_scan_step_has_no_with_when_the_spec_declares_none():
    job = build_plan(Config(name="security", scanner="gitleaks")).jobs[0]
    assert job.steps[1].with_ is None
