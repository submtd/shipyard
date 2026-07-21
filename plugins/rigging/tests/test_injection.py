"""Injection-safety guarantees -- rigging's core security promise.

No rendered workflow ever contains an attacker-controllable `${{ ... }}`
expression. This is enforced at two layers:

1. Data layer: no `Step.run` in the stack registry may contain `${{` --
   a future stack contribution can't smuggle an expression into a run
   command.
2. Rendered-output layer: every `- run:` block in generated YAML is scanned
   for `${{`, and every `${{ ... }}` expression that DOES appear anywhere
   in the output (e.g. in a `with:` block) must be one of the whitelisted
   `${{ matrix.<var> }}` forms -- nothing else, and never `github.*`.

Stdlib only: re, json, pathlib, pytest.
"""
import json
import re

import pytest

from rigging.config import ConfigError, load_config
from rigging.plan import build_plan
from rigging.render import iter_run_blocks, render
from rigging.stacks import REGISTRY

WHITELIST_RE = re.compile(r"^\$\{\{\s*matrix\.[a-z0-9_]+\s*\}\}$")
EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}")


def write_config(tmp_path, data):
    (tmp_path / ".rigging.json").write_text(json.dumps(data))
    return tmp_path


def render_for(tmp_path, stacks):
    cfg = load_config(write_config(tmp_path, {"name": "ci", "stacks": stacks}))
    plan = build_plan(cfg)
    return render(plan)


# --- Assertion 1: data-layer guarantee ------------------------------------


def test_registry_steps_never_embed_an_expression():
    for stack_id, spec in REGISTRY.items():
        for step in spec.steps:
            if step.run is not None:
                assert "${{" not in step.run, (
                    f"stack {stack_id!r} step.run contains '${{{{': {step.run!r}"
                )


# --- Rendered-output fixtures: python-only, node-only, polyglot ----------


@pytest.fixture
def python_output(tmp_path):
    return render_for(tmp_path, {"python": {"versions": ["3.12"]}})


@pytest.fixture
def node_output(tmp_path):
    return render_for(tmp_path, {"node": {"versions": ["20"]}})


@pytest.fixture
def polyglot_output(tmp_path):
    return render_for(
        tmp_path,
        {"python": {"versions": ["3.12"]}, "node": {"versions": ["20"]}},
    )


@pytest.fixture
def all_outputs(python_output, node_output, polyglot_output):
    return {
        "python": python_output,
        "node": node_output,
        "polyglot": polyglot_output,
    }


# --- Assertion 2: rendered-output run scan --------------------------------


def test_run_blocks_never_contain_an_expression(all_outputs):
    for label, output in all_outputs.items():
        for block in iter_run_blocks(output):
            assert "${{" not in block, (
                f"{label}: run block contains '${{{{': {block!r}"
            )


# --- Assertion 3: whitelisted-expression-only -----------------------------


def test_every_expression_is_whitelisted_matrix_form(all_outputs):
    for label, output in all_outputs.items():
        expressions = EXPRESSION_RE.findall(output)
        assert expressions, f"{label}: expected at least one ${{{{ }}}} expression"
        for expr in expressions:
            assert WHITELIST_RE.fullmatch(expr), (
                f"{label}: expression {expr!r} is not a whitelisted "
                f"'${{{{ matrix.<var> }}}}' form"
            )


# --- Assertion 4: no github context ---------------------------------------


def test_no_github_context_reference(all_outputs):
    for label, output in all_outputs.items():
        assert "github." not in output, (
            f"{label}: rendered output references 'github.'"
        )


# --- Assertion 5: end-to-end config-layer guard ---------------------------


@pytest.mark.parametrize("hostile_version", [
    "1.0; rm -rf",
    "1.0}}",
    "${{ github.token }}",
])
def test_hostile_version_string_rejected_before_render(tmp_path, hostile_version):
    write_config(tmp_path, {
        "name": "ci",
        "stacks": {"python": {"versions": [hostile_version]}},
    })
    with pytest.raises(ConfigError):
        load_config(tmp_path)
