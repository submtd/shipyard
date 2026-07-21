import pytest

from rigging import stacks
from rigging.config import Config
from rigging.plan import CiPlan, Job, build_plan


def test_single_python_stack_yields_one_job():
    cfg = Config(name="ci", stacks={"python": ("3.9", "3.12")})
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
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    job = build_plan(cfg).jobs[0]

    assert job.steps == (
        stacks.Step(uses="actions/checkout@v4"),
        stacks.Step(
            uses="actions/setup-python@v5",
            with_={"python-version": "${{ matrix.python }}"},
        ),
        stacks.Step(run="pip install pytest"),
        stacks.Step(run="python -m pytest"),
    )


def test_two_stack_config_yields_two_jobs_in_config_order():
    cfg = Config(
        name="ci",
        stacks={"node": ("20",), "python": ("3.12",)},
    )
    plan = build_plan(cfg)

    assert len(plan.jobs) == 2
    assert [job.id for job in plan.jobs] == ["node", "python"]


def test_node_job_wires_node_version_and_npm_steps():
    cfg = Config(name="ci", stacks={"node": ("18", "20")})
    job = build_plan(cfg).jobs[0]

    assert job.id == "node"
    assert job.runs_on == "ubuntu-latest"
    assert job.matrix_var == "node"
    assert job.versions == ("18", "20")
    assert job.steps == (
        stacks.Step(uses="actions/checkout@v4"),
        stacks.Step(
            uses="actions/setup-node@v5",
            with_={"node-version": "${{ matrix.node }}"},
        ),
        stacks.Step(run="npm ci"),
        stacks.Step(run="npm test"),
    )


def test_ciplan_is_frozen_dataclass():
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    plan = build_plan(cfg)
    with pytest.raises(Exception):
        plan.name = "changed"


def test_job_is_frozen_dataclass():
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    job = build_plan(cfg).jobs[0]
    with pytest.raises(Exception):
        job.id = "changed"
