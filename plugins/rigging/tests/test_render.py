import json
from pathlib import Path

import pytest

from rigging.config import Config, StackConfig, load_config
from rigging import stacks
from rigging.plan import CHECKOUT_STEP, build_plan
from rigging.render import iter_run_blocks, render, _step_lines

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
    "pip install 'pytest>=8,<9'\n"
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
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.10",))})
    plan = build_plan(cfg)
    out = render(plan)

    assert 'python: ["3.10"]' in out
    assert ": 3.10" not in out
    assert ": 3.1" not in out
    assert "[3.10]" not in out
    assert "[3.1]" not in out


def test_render_is_deterministic():
    cfg = Config(name="ci", stacks={
        "python": StackConfig(versions=("3.9", "3.12")),
        "node": StackConfig(versions=("20",)),
    })
    plan = build_plan(cfg)
    assert render(plan) == render(plan)


def test_output_contains_expected_fragments():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    out = render(build_plan(cfg))

    assert 'runs-on: "ubuntu-latest"' in out
    assert f'"{CHECKOUT_STEP.uses}"' in out
    assert "permissions:\n  contents: read" in out
    assert 'name: "ci"' in out


def test_iter_run_blocks_returns_unquoted_bodies_in_order():
    cfg = Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))})
    out = render(build_plan(cfg))

    assert iter_run_blocks(out) == [PYTHON_INSTALL_RUN, "python -m pytest"]


def test_iter_run_blocks_for_polyglot_plan_covers_both_jobs():
    cfg = Config(name="ci", stacks={
        "python": StackConfig(versions=("3.12",)),
        "node": StackConfig(versions=("20",)),
    })
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
        f'      - uses: "{CHECKOUT_STEP.uses}"  # {CHECKOUT_STEP.uses_version}\n'
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
    cfg = Config(name="123", stacks={"python": StackConfig(versions=("3.12",))})
    out = render(build_plan(cfg))

    assert out.startswith('name: "123"\n')
    assert "name: 123\n" not in out

    if _yaml is not None:
        loaded = _yaml.safe_load(out)
        assert loaded["name"] == "123"
        assert isinstance(loaded["name"], str)


def test_dash_name_is_quoted_and_is_valid_yaml():
    cfg = Config(name="-", stacks={"python": StackConfig(versions=("3.12",))})
    out = render(build_plan(cfg))

    assert out.startswith('name: "-"\n')

    if _yaml is not None:
        # Unquoted `name: -` is not valid YAML at all (a bare `-` starts a
        # block sequence entry); this is the "CI never runs" failure mode.
        loaded = _yaml.safe_load(out)
        assert loaded["name"] == "-"
        assert isinstance(loaded["name"], str)


# --- SHA pins and their human-readable comment ---------------------------
#
# A SHA pin is unreadable on its own, so the convention (and what Dependabot
# maintains) is a trailing `# v4` comment. It must sit OUTSIDE the quoted
# scalar: inside, it becomes part of the ref and GitHub fails to resolve the
# action.


def test_version_comment_renders_outside_the_quoted_scalar():
    step = stacks.Step(uses="actions/checkout@" + "a" * 40, uses_version="v4")
    assert _step_lines(step) == [
        '      - uses: "actions/checkout@' + "a" * 40 + '"  # v4'
    ]


def test_no_comment_when_uses_version_is_absent():
    step = stacks.Step(uses="actions/checkout@" + "a" * 40)
    assert _step_lines(step) == ['      - uses: "actions/checkout@' + "a" * 40 + '"']


def test_step_name_is_rendered_rather_than_silently_dropped():
    # `name` was declared on Step and emitted by nothing, so a registry
    # entry written as Step(name=...) lost it with no error and no test.
    step = stacks.Step(name="install deps", uses="actions/checkout@" + "a" * 40)
    assert _step_lines(step)[0] == '      - name: "install deps"'


# --- Triggers. `on: [push, pull_request]` runs the whole matrix twice for
# every PR opened from a branch in the same repo: once for the push, once
# for the pull_request. Restricting push to the long-lived branches keeps
# both signals without paying for either twice. -------------------------


def test_push_is_restricted_to_the_configured_branches():
    text = render(build_plan(Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))},
                                    push_branches=("main",))))
    assert "on: [push, pull_request]" not in text
    assert 'branches: ["main"]' in text


def test_every_configured_push_branch_is_rendered():
    text = render(build_plan(Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))},
                                    push_branches=("main", "develop"))))
    assert 'branches: ["main", "develop"]' in text


def test_pull_request_stays_unrestricted():
    text = render(build_plan(Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))},
                                    push_branches=("main",))))
    assert "  pull_request:" in text


def test_the_python_stack_bounds_its_pytest_version():
    """An unpinned `pip install pytest` means a pytest major release can
    break CI in a repo whose own code never changed. A bounded range keeps
    patches flowing without letting a major in unannounced."""
    text = render(build_plan(Config(name="ci", stacks={"python": StackConfig(versions=("3.12",))},
                                    push_branches=("main",))))
    assert "pip install pytest\n" not in text, "the bare, unbounded install"
    assert "pytest>=8,<9" in text


@pytest.mark.parametrize("manager,golden", [
    ("pnpm", "node-pnpm.yml"),
    ("yarn1", "node-yarn1.yml"),
    ("yarn-berry", "node-yarn-berry.yml"),
    ("bun", "node-bun.yml"),
])
def test_each_manager_matches_its_golden(tmp_path, manager, golden):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": manager}}}))
    assert render(build_plan(cfg)) == read_golden(golden)


def test_npm_goldens_did_not_move(tmp_path):
    """Adding four managers must not perturb the one that already worked."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert render(build_plan(cfg)) == read_golden("node.yml")


def test_yarn_majors_render_incompatible_flags(tmp_path):
    """The whole reason they are separate entries. If these two ever render
    the same install line, one of them is broken."""
    def install_line(manager):
        cfg = load_config(write(tmp_path, {
            "stacks": {"node": {"packageManager": manager}}}))
        return [l for l in render(build_plan(cfg)).splitlines()
                if "yarn install" in l][0]

    assert "--frozen-lockfile" in install_line("yarn1")
    assert "--immutable" in install_line("yarn-berry")


def test_manager_setup_runs_before_setup_node(tmp_path):
    """pnpm and bun install the manager itself; doing that after setup-node
    would work today but breaks the moment dependency caching is added."""
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": "pnpm"}}}))
    out = render(build_plan(cfg))
    assert out.index("pnpm/action-setup") < out.index("actions/setup-node")


def test_corepack_enable_lands_between_setup_node_and_install(tmp_path):
    """Order is the whole point: corepack ships WITH node, so enabling it
    before setup-node would run against whatever node the image happened to
    have, and after the install line would be too late."""
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": "yarn-berry"}}}))
    out = render(build_plan(cfg))
    assert out.index("actions/setup-node") < out.index("corepack enable")
    assert out.index("corepack enable") < out.index("yarn install --immutable")


def test_other_managers_gained_no_post_setup_step(tmp_path):
    for manager in ("npm", "yarn1", "pnpm", "bun"):
        cfg = load_config(write(tmp_path, {
            "stacks": {"node": {"packageManager": manager}}}))
        assert "corepack" not in render(build_plan(cfg))
