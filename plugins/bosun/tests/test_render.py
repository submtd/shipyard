"""DependabotPlan -> dependabot.yml tests.

Mirrors rigging/tests/test_render.py's and hull/tests/test_render.py's
shape: golden byte-for-byte comparison, determinism, and quoting
invariants.

Unlike hull/rigging, bosun's injection-safety guarantee is NOT enforced by
scanning rendered output for adversarial content -- there is no free-text
value that ever reaches `render()`. `interval` is enum-validated against
`ecosystems.INTERVALS`, ecosystem ids are whitelisted against
`ecosystems.ECOSYSTEM_IDS`, and `directory` is hardcoded `"/"` in
`plan.build_plan`, all at the config layer (`config.load_config`). A
hostile string (e.g. `${{ secrets.EVIL }}` or an embedded `run:` line)
cannot reach `render()` through the real `.bosun.json` -> `load_config`
entrypoint -- it is rejected as a `ConfigError` first.
`test_hostile_config_values_are_rejected_before_render` below is the actual
proof of that guarantee, mirroring hull's/rigging's assertion-5
end-to-end config-layer guard. `test_declarative_output_has_no_expressions_or_run_lines`
just below it is a separate, narrower thing: a structural regression check
that well-formed, schema-legal `dependabot.yml` output never happens to
contain `${{` or `run:` -- it says nothing about hostile input, because
none of its inputs are hostile.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from bosun.config import Config, ConfigError, EcosystemConfig, load_config
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


def test_declarative_output_has_no_expressions_or_run_lines():
    """Structural regression check, NOT an injection-safety proof: for
    well-formed inputs (enum-valid intervals, registry-fixed ecosystem
    ids), rendered dependabot.yml never happens to contain `${{` or
    `run:`, because the declarative Dependabot schema has no expression or
    run-step syntax to emit in the first place. Every value exercised here
    is already known-safe, so this cannot fail regardless of whether
    `render()` would escape or reject hostile input -- it is not evidence
    that hostile input is handled safely. See
    `test_hostile_config_values_are_rejected_before_render` for the actual
    injection-safety guarantee, which is enforced at the config layer."""
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


@pytest.mark.parametrize("hostile_config", [
    {"ecosystems": {"python": {"interval": "${{ secrets.EVIL }}"}}},
    {"ecosystems": {"python": {"interval": "weekly\nrun: rm -rf /"}}},
    {"ecosystems": {"${{ github.token }}": {}}},
])
def test_hostile_config_values_are_rejected_before_render(tmp_path, hostile_config):
    """bosun's actual injection-safety guarantee: `render()` never sees
    hostile content because `load_config` rejects it first. `interval` is
    checked against the closed `ecosystems.INTERVALS` enum and ecosystem
    ids are checked against the closed `ecosystems.ECOSYSTEM_IDS`
    whitelist (`config.py`'s `_valid_interval` and the `ecosystem_id not
    in ecosystems.ECOSYSTEM_IDS` check) -- there is no free-text value
    anywhere in `.bosun.json` that survives to reach `render()`. This
    mirrors hull's/rigging's assertion-5 end-to-end config-layer guard
    (`test_hostile_name_rejected_before_render` /
    `test_hostile_version_string_rejected_before_render`)."""
    write(tmp_path, hostile_config)
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_updates_header_present():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    out = render(build_plan(cfg))
    assert "updates:\n" in out
