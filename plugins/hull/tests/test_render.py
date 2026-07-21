"""ScanPlan -> YAML tests.

Mirrors rigging/tests/test_render.py's shape: golden byte-for-byte
comparison, determinism, and quoting invariants -- ported for hull's
single-scanner `ScanPlan` (one job, no `strategy`/`matrix` block, since a
scanner run is a single pass over the repo rather than a per-version
matrix -- see hull.plan).
"""
from __future__ import annotations

import json
from pathlib import Path

from hull.config import Config, load_config
from hull.plan import build_plan
from hull.render import iter_run_blocks, render

GOLDEN = Path(__file__).parent / "golden"


def write(tmp_path, data):
    (tmp_path / ".hull.json").write_text(json.dumps(data))
    return tmp_path


def read_golden(name):
    return (GOLDEN / name).read_text()


def test_default_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {}))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("security.yml")


def test_render_is_deterministic():
    cfg = Config(name="security", scanner="gitleaks")
    plan = build_plan(cfg)
    assert render(plan) == render(plan)


def test_every_scalar_value_is_quoted():
    cfg = Config(name="security", scanner="gitleaks")
    out = render(build_plan(cfg))

    assert 'name: "security"' in out
    assert 'runs-on: "ubuntu-latest"' in out
    assert 'uses: "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"' in out
    assert 'fetch-depth: "0"' in out
    assert 'uses: "gitleaks/gitleaks-action@ff98106e4c7b2bc287b24eaf42907196329070c7"' in out
    assert 'GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}"' in out


def test_permissions_and_on_present():
    cfg = Config(name="security", scanner="gitleaks")
    out = render(build_plan(cfg))

    assert "on: [push, pull_request]" in out
    assert "permissions:\n  contents: read" in out


def test_workflow_name_matches_config_name(tmp_path):
    """The filename==name lesson (ballast): a non-default config name still
    ends up as the rendered `name:` value, never hardcoded 'security'."""
    cfg = load_config(write(tmp_path, {"name": "sec2"}))
    out = render(build_plan(cfg))
    assert out.startswith('name: "sec2"\n')


def test_render_ends_with_exactly_one_trailing_newline():
    cfg = Config(name="security", scanner="gitleaks")
    out = render(build_plan(cfg))
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_iter_run_blocks_finds_none_for_default_plan():
    """No run steps in increment 1 -- gitleaks is a single `uses:` action."""
    cfg = Config(name="security", scanner="gitleaks")
    out = render(build_plan(cfg))
    assert iter_run_blocks(out) == []


def test_iter_run_blocks_returns_unquoted_single_line_body():
    text = '      - run: "echo hi"\n'
    assert iter_run_blocks(text) == ["echo hi"]


def test_iter_run_blocks_block_scalar_ends_at_next_step():
    text = (
        "      - run: |\n"
        "          line one\n"
        "          line two\n"
        '      - uses: "actions/checkout@11d5960a326750d5838078e36cf38b85af677262"\n'
    )
    assert iter_run_blocks(text) == ["line one\nline two"]
