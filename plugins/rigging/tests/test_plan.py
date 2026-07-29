import pytest

from rigging import stacks
from rigging.config import Config, StackConfig
from rigging import plan
from rigging.plan import CiPlan, Job, build_plan


def test_single_python_stack_yields_one_job():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.9", "3.12"))})
    plan = build_plan(cfg)

    assert isinstance(plan, CiPlan)
    assert plan.name == "ci"
    assert len(plan.jobs) == 1

    job = plan.jobs[0]
    assert isinstance(job, Job)
    assert job.id == "python"
    assert job.runs_on == "ubuntu-latest"
    assert job.matrix_var == "python"
    assert job.versions == ("3.9", "3.12")


def test_python_job_steps_in_order():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    job = build_plan(cfg).jobs[0]

    # The install step's exact body is pinned by rigging.stacks's own tests
    # (test_stacks.py); here we only need it to match the registry, since a
    # job's steps are the registry's steps plus checkout/setup wrapping. The
    # test step no longer lives on steps -- it is resolved from
    # default_test (see test_stacks.py's default_test tests).
    (install_step,) = stacks.REGISTRY["python"].steps
    test_step = stacks.Step(run=plan.render_argv(stacks.REGISTRY["python"].default_test))

    assert job.steps == (
        plan.CHECKOUT_STEP,
        stacks.Step(
            uses=stacks.REGISTRY["python"].setup_uses,
            uses_version=stacks.REGISTRY["python"].setup_uses_version,
            with_={"python-version": "${{ matrix.python }}"},
        ),
        install_step,
        test_step,
    )


def test_two_stack_config_yields_two_jobs_in_config_order():
    cfg = Config(
        name="ci",
        stacks={
            "node": StackConfig(versions=("20",)),
            "python": StackConfig(versions=("3.12",)),
        },
    )
    plan = build_plan(cfg)

    assert len(plan.jobs) == 2
    assert [job.id for job in plan.jobs] == ["node", "python"]


def test_node_job_wires_node_version_and_npm_steps():
    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("18", "20"))})
    job = build_plan(cfg).jobs[0]

    assert job.id == "node"
    assert job.runs_on == "ubuntu-latest"
    assert job.matrix_var == "node"
    assert job.versions == ("18", "20")
    assert job.steps == (
        plan.CHECKOUT_STEP,
        stacks.Step(
            uses=stacks.REGISTRY["node"].setup_uses,
            uses_version=stacks.REGISTRY["node"].setup_uses_version,
            with_={"node-version": "${{ matrix.node }}", "cache": "npm"},
        ),
        stacks.Step(run="npm ci"),
        stacks.Step(run="npm test"),
    )


def test_ciplan_is_frozen_dataclass():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    plan = build_plan(cfg)
    with pytest.raises(Exception):
        plan.name = "changed"


def test_job_is_frozen_dataclass():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    job = build_plan(cfg).jobs[0]
    with pytest.raises(Exception):
        job.id = "changed"


def test_render_argv_leaves_simple_words_unquoted():
    """npm's output must be byte-identical, so the common case has to render
    without quotes."""
    from rigging.plan import render_argv

    assert render_argv(("npm", "ci")) == "npm ci"


def test_render_argv_quotes_what_the_shell_would_otherwise_read():
    from rigging.plan import render_argv

    assert render_argv(("a", "b c")) == "a 'b c'"
    assert render_argv(("a", "b;c")) == "a 'b;c'"
    assert render_argv(("a", "$HOME")) == "a '$HOME'"


def test_node_job_steps_come_from_the_manager():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("20",))})
    steps = build_plan(cfg).jobs[0].steps
    assert [s.run for s in steps if s.run] == ["npm ci", "npm test"]


def test_configured_manager_drives_the_node_job():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={
        "node": StackConfig(versions=("20",), package_manager="npm")})
    assert [s.run for s in build_plan(cfg).jobs[0].steps if s.run] == [
        "npm ci", "npm test"]


def test_unset_manager_falls_back_to_the_default():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("20",))})
    assert [s.run for s in build_plan(cfg).jobs[0].steps if s.run] == [
        "npm ci", "npm test"]


def _setup_node_with(cfg):
    """The setup-node step's with_ mapping for a single-job plan."""
    (job,) = build_plan(cfg).jobs
    (setup,) = [s for s in job.steps
                if s.uses == stacks.REGISTRY["node"].setup_uses]
    return setup.with_


@pytest.mark.parametrize("manager_id, cache_key", [
    ("npm", "npm"),
    ("pnpm", "pnpm"),
    ("yarn1", "yarn"),
])
def test_setup_node_carries_the_managers_cache_input(manager_id, cache_key):
    cfg = Config(name="ci", stacks={
        "node": StackConfig(versions=("20",), package_manager=manager_id)})
    assert _setup_node_with(cfg) == {
        "node-version": "${{ matrix.node }}", "cache": cache_key}


@pytest.mark.parametrize("manager_id", ["yarn-berry", "bun"])
def test_setup_node_omits_cache_when_the_manager_has_no_key(manager_id):
    cfg = Config(name="ci", stacks={
        "node": StackConfig(versions=("20",), package_manager=manager_id)})
    assert _setup_node_with(cfg) == {"node-version": "${{ matrix.node }}"}


def test_cache_input_renders_after_node_version():
    """with_ renders in insertion order; node-version staying first keeps the
    golden diff to a single added line."""
    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("20",))})
    assert list(_setup_node_with(cfg)) == ["node-version", "cache"]


def test_python_setup_step_gains_no_cache_input():
    """The issue is node-only; setup-python's `cache: pip` is a separate
    decision."""
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    (job,) = build_plan(cfg).jobs
    (setup,) = [s for s in job.steps
                if s.uses == stacks.REGISTRY["python"].setup_uses]
    assert setup.with_ == {"python-version": "${{ matrix.python }}"}
