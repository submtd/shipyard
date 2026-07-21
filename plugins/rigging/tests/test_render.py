import json
from pathlib import Path

from rigging.config import Config, load_config
from rigging.plan import build_plan
from rigging.render import iter_run_blocks, render

try:
    import yaml as _yaml
except ImportError:  # pragma: no cover - CI's python job installs pytest only
    _yaml = None

GOLDEN = Path(__file__).parent / "golden"

# The python stack's install step, mirroring GitHub's official python starter
# workflow: upgrade pip, install pytest, and conditionally install the
# project's own declared requirements. Kept here so the golden-comparison and
# iter_run_blocks expectations don't drift from rigging.stacks's own copy
# silently -- if one changes without the other, these tests fail loudly.
PYTHON_INSTALL_RUN = (
    "python -m pip install --upgrade pip\n"
    "pip install pytest\n"
    "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"
)


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
    assert 'name: "ci"' in out


def test_iter_run_blocks_returns_unquoted_bodies_in_order():
    cfg = Config(name="ci", stacks={"python": ("3.12",)})
    out = render(build_plan(cfg))

    assert iter_run_blocks(out) == [PYTHON_INSTALL_RUN, "python -m pytest"]


def test_iter_run_blocks_for_polyglot_plan_covers_both_jobs():
    cfg = Config(name="ci", stacks={"python": ("3.12",), "node": ("20",)})
    out = render(build_plan(cfg))

    assert iter_run_blocks(out) == [
        PYTHON_INSTALL_RUN,
        "python -m pytest",
        "npm ci",
        "npm test",
    ]


def test_iter_run_blocks_block_scalar_ends_at_next_step():
    text = (
        "      - run: |\n"
        "          line one\n"
        "          line two\n"
        '      - uses: "actions/checkout@v4"\n'
    )
    assert iter_run_blocks(text) == ["line one\nline two"]


def test_iter_run_blocks_block_scalar_at_end_of_document():
    text = "      - run: |\n          only line\n"
    assert iter_run_blocks(text) == ["only line"]


# --- FIX 1 (Critical): the workflow `name:` must always be quoted ---------
#
# render.py line ~62 used to emit `f"name: {plan.name}"` unquoted -- the only
# scalar VALUE not routed through `_quote`. A config name that is charset-valid
# (NAME_RE: `^[A-Za-z0-9_-]+$`) but also looks like a YAML int/bool/null/dash
# token (e.g. "123", "-", "true", "null") would make the emitted YAML
# mis-parse as a non-string, or fail to parse at all (`name: -` is not valid
# YAML). Regression-pinned here with a numeric and a dash name.


def test_numeric_name_is_quoted():
    cfg = Config(name="123", stacks={"python": ("3.12",)})
    out = render(build_plan(cfg))

    assert out.startswith('name: "123"\n')
    assert "name: 123\n" not in out

    if _yaml is not None:
        loaded = _yaml.safe_load(out)
        assert loaded["name"] == "123"
        assert isinstance(loaded["name"], str)


def test_dash_name_is_quoted_and_is_valid_yaml():
    cfg = Config(name="-", stacks={"python": ("3.12",)})
    out = render(build_plan(cfg))

    assert out.startswith('name: "-"\n')

    if _yaml is not None:
        # Unquoted `name: -` is not valid YAML at all (a bare `-` starts a
        # block sequence entry); this is the "CI never runs" failure mode.
        loaded = _yaml.safe_load(out)
        assert loaded["name"] == "-"
        assert isinstance(loaded["name"], str)
