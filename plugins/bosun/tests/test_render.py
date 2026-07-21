"""DependabotPlan -> dependabot.yml tests.

Mirrors rigging/tests/test_render.py's and hull/tests/test_render.py's
shape: golden byte-for-byte comparison, determinism, and quoting
invariants. dependabot.yml is purely declarative -- there is no `run:`/
`uses:` step and no `${{ }}` expression syntax anywhere in this schema, so
the declarative-only guard here (no `${{`, no `run:` line) stands in for
hull's/rigging's injection tests.
"""
from __future__ import annotations

import json
from pathlib import Path

from bosun.config import Config, EcosystemConfig, load_config
from bosun.plan import build_plan
from bosun.render import render

GOLDEN = Path(__file__).parent / "golden"


def write(tmp_path, data):
    (tmp_path / ".bosun.json").write_text(json.dumps(data))
    return tmp_path


def read_golden(name):
    return (GOLDEN / name).read_text()


def test_github_actions_only_plan_matches_shipyard_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"githubActions": {}}}))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("shipyard.yml")


def test_multi_ecosystem_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ecosystems": {
            "githubActions": {},
            "python": {},
            "node": {},
        },
    }))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("multi.yml")


def test_default_interval_plan_matches_defaults_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {}}}))
    plan = build_plan(cfg)
    assert render(plan) == read_golden("defaults.yml")


def test_render_is_deterministic():
    cfg = Config(
        ecosystems={
            "githubActions": EcosystemConfig(interval="weekly"),
            "python": EcosystemConfig(interval="daily"),
            "node": EcosystemConfig(interval="monthly"),
        }
    )
    plan = build_plan(cfg)
    assert render(plan) == render(plan)


def test_version_is_bare_integer_not_quoted():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    out = render(build_plan(cfg))

    assert out.startswith("version: 2\n")
    assert 'version: "2"' not in out


def test_string_scalars_are_double_quoted():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    out = render(build_plan(cfg))

    assert 'package-ecosystem: "github-actions"' in out
    assert 'directory: "/"' in out
    assert 'interval: "weekly"' in out


def test_render_ends_with_exactly_one_trailing_newline():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    out = render(build_plan(cfg))
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_declarative_only_guard_no_expressions_or_run_steps():
    """dependabot.yml has no injection surface: no `${{ }}` expressions and
    no `run:` steps anywhere in the schema. This replaces hull's injection
    test for bosun."""
    cfg = Config(
        ecosystems={
            "githubActions": EcosystemConfig(interval="weekly"),
            "python": EcosystemConfig(interval="daily"),
            "node": EcosystemConfig(interval="monthly"),
        }
    )
    out = render(build_plan(cfg))

    assert "${{" not in out
    assert "run:" not in out


def test_updates_header_present():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    out = render(build_plan(cfg))
    assert "updates:\n" in out
