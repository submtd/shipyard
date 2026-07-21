import json
from pathlib import Path

from rigging.config import Config, load_config
from rigging.plan import build_plan
from rigging.render import iter_run_blocks, render

GOLDEN = Path(__file__).parent / "golden"


def write(tmp_path, data):
    (tmp_path / ".rigging.json").write_text(json.dumps(data))
    return tmp_path


def read_golden(name):
    return (GOLDEN / name).read_text()


def test_python_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "name": "ci",
        "stacks": {"python": {"versions": ["3.9", "3.12"]}},
    }))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("python.yml")


def test_node_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "name": "ci",
        "stacks": {"node": {"versions": ["20"]}},
    }))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("node.yml")


def test_polyglot_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "name": "ci",
        "stacks": {
            "python": {"versions": ["3.12"]},
            "node": {"versions": ["20"]},
        },
    }))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("polyglot.yml")


def test_version_that_looks_like_a_float_is_quoted_not_coerced():
    cfg = Config(name="ci", stacks={"python": ("3.10",)})
    plan = build_plan(cfg)
    out = render(plan)

    assert 'python: ["3.10"]' in out
    assert ": 3.10" not in out
    assert ": 3.1" not in out
    assert "[3.10]" not in out
    assert "[3.1]" not in out


def test_render_is_deterministic():
    cfg = Config(name="ci", stacks={"python": ("3.9", "3.12"), "node": ("20",)})
    plan = build_plan(cfg)
    assert render(plan) == render(plan)


def test_output_contains_expected_fragments():
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    out = render(build_plan(cfg))

    assert 'runs-on: "ubuntu-latest"' in out
    assert '"actions/checkout@v4"' in out
    assert "permissions:\n  contents: read" in out


def test_iter_run_blocks_returns_unquoted_bodies_in_order():
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    out = render(build_plan(cfg))

    assert iter_run_blocks(out) == ["pip install pytest", "python -m pytest"]


def test_iter_run_blocks_for_polyglot_plan_covers_both_jobs():
    cfg = Config(name="ci", stacks={"python": ("3.12",), "node": ("20",)})
    out = render(build_plan(cfg))

    assert iter_run_blocks(out) == [
        "pip install pytest",
        "python -m pytest",
        "npm ci",
        "npm test",
    ]
