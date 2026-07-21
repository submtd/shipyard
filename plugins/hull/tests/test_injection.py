"""Injection-safety guarantees -- hull's core security promise.

The STRUCTURAL guarantee is: no `${{ github.* }}` EXPRESSION -- nor any
expression outside the `${{ secrets.GITHUB_TOKEN }}` whitelist -- is ever
emitted. This mirrors rigging/tests/test_injection.py, enforced at the same
two layers:

1. Data layer: no run step embedded anywhere in `scanners.REGISTRY` may
   contain `${{` -- a future scanner contribution can't smuggle an
   expression into a run command. No `ScannerSpec` carries a `steps` field
   in this increment (gitleaks is a single `uses:` action, not a `run`),
   so this guards ahead of a later increment that adds one.
2. Rendered-output layer: every `- run:` block in generated YAML (there are
   none in increment 1, but `iter_run_blocks` is still exercised so this
   guards the day a scanner does have one) is scanned for `${{`, and every
   `${{ ... }}` expression that DOES appear anywhere in the output (in a
   step's `env`) must be the whitelisted `${{ secrets.GITHUB_TOKEN }}`
   form -- nothing else, and never `github.*`. Assertion 3
   (`test_every_expression_is_whitelisted_github_token`) is the
   load-bearing check for this guarantee; it is never weakened to
   accommodate anything outside the whitelist.

Stdlib only: re, json, pathlib, pytest.
"""
from __future__ import annotations

import json
import re

import pytest

from hull.config import ConfigError, load_config
from hull.plan import build_plan
from hull.render import iter_run_blocks, render
from hull.scanners import REGISTRY

WHITELIST_RE = re.compile(r"^\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}$")
EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}")


def write_config(tmp_path, data):
    (tmp_path / ".hull.json").write_text(json.dumps(data))
    return tmp_path


def render_default(tmp_path):
    cfg = load_config(write_config(tmp_path, {}))
    return render(build_plan(cfg))


# --- Assertion 1: data-layer guarantee ------------------------------------


def test_registry_steps_never_embed_an_expression():
    for scanner_id, spec in REGISTRY.items():
        for step in getattr(spec, "steps", ()):
            if step.run is not None:
                assert "${{" not in step.run, (
                    f"scanner {scanner_id!r} step.run contains '${{{{': "
                    f"{step.run!r}"
                )


# --- Assertion 2: rendered-output run scan --------------------------------


def test_run_blocks_never_contain_an_expression(tmp_path):
    output = render_default(tmp_path)
    for block in iter_run_blocks(output):
        assert "${{" not in block, f"run block contains '${{{{': {block!r}"


# --- Assertion 3: whitelisted-expression-only (LOAD-BEARING) --------------
#
# This is the actual structural guarantee: every `${{ ... }}` expression
# that appears anywhere in the rendered output must fullmatch the
# `${{ secrets.GITHUB_TOKEN }}` whitelist. Nothing else -- in particular no
# `${{ github.* }}` -- ever passes. Never weaken this assertion.


def test_every_expression_is_whitelisted_github_token(tmp_path):
    output = render_default(tmp_path)
    expressions = EXPRESSION_RE.findall(output)
    assert expressions, "expected at least one ${{ }} expression"
    for expr in expressions:
        assert WHITELIST_RE.fullmatch(expr), (
            f"expression {expr!r} is not the whitelisted "
            f"'${{{{ secrets.GITHUB_TOKEN }}}}' form"
        )


# --- Assertion 4: no github.* context reference ----------------------------


def test_no_github_context_reference(tmp_path):
    output = render_default(tmp_path)
    assert "github." not in output, "rendered output references 'github.'"


# --- Assertion 5: end-to-end config-layer guard ----------------------------


@pytest.mark.parametrize("hostile_name", [
    "${{ github.token }}",
    "x}}",
    "a; rm -rf",
])
def test_hostile_name_rejected_before_render(tmp_path, hostile_name):
    write_config(tmp_path, {"name": hostile_name})
    with pytest.raises(ConfigError):
        load_config(tmp_path)
