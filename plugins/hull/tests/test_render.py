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
from hull.plan import CHECKOUT_USES, CHECKOUT_VERSION, build_plan
from hull.scanners import REGISTRY
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
    assert f'uses: "{CHECKOUT_USES}"' in out
    assert 'fetch-depth: "0"' in out
    assert f'uses: "{REGISTRY["gitleaks"].action_ref}"' in out
    assert 'GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}"' in out


def test_permissions_and_on_present():
    cfg = Config(name="security", scanner="gitleaks")
    out = render(build_plan(cfg))

    assert "on:\n  push:\n    branches: [\"main\"]\n  pull_request:\n" in out
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
        f'      - uses: "{CHECKOUT_USES}"  # {CHECKOUT_VERSION}\n'
    )
    assert iter_run_blocks(text) == ["line one\nline two"]


def test_push_is_restricted_to_the_configured_branches():
    """Same reasoning as rigging's: `on: [push, pull_request]` ran the scan
    twice for every PR raised from a branch in the same repo. The two
    generators must agree on trigger shape -- a repo scaffolded by both ends
    up with these workflows side by side."""
    text = render(build_plan(Config(name="security", scanner="gitleaks",
                                    push_branches=("main",))))
    assert "on: [push, pull_request]" not in text
    assert 'branches: ["main"]' in text
    assert "  pull_request:" in text


# --- Token permissions -----------------------------------------------------
#
# Found by an end-to-end run in a fresh PRIVATE repo: every `pull_request`
# scan failed with 403 "Resource not accessible by integration", while every
# `push` scan passed. gitleaks-action v3 calls
# GET /repos/{o}/{r}/pulls/{n}/commits to enumerate a PR's commits, and
# `contents: read` alone does not grant that. Shipyard's own dogfooding
# cannot catch this, because shipyard is public and hull's whole point is
# scanning repos that are not.


def test_gitleaks_job_can_read_pull_requests():
    text = render(build_plan(Config(name="security", scanner="gitleaks")))
    assert "pull-requests: read" in text


def test_contents_read_is_still_granted():
    """Least privilege, not no privilege: the scan still needs the code."""
    text = render(build_plan(Config(name="security", scanner="gitleaks")))
    assert "contents: read" in text


def test_permissions_stay_least_privilege():
    """Every permission rendered must be a read scope. A write scope here
    would hand a token that can push to whatever the scanner action runs."""
    text = render(build_plan(Config(name="security", scanner="gitleaks")))
    block = text.split("permissions:\n", 1)[1].split("jobs:", 1)[0]
    granted = [l.strip() for l in block.splitlines() if l.strip()]
    assert granted, "no permissions rendered at all"
    for line in granted:
        assert line.endswith(": read"), f"non-read permission granted: {line}"


# --- licenseSecret ---------------------------------------------------------
#
# Issue #24. Two goldens, not one: the licensed output is pinned byte-for-byte
# like the default, and the default golden above continues to prove that a
# config without the key renders exactly what hull rendered before it existed.


def test_license_plan_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE"}))
    assert render(build_plan(cfg)) == read_golden("security-license.yml")


def test_license_secret_renders_as_a_quoted_secrets_reference(tmp_path):
    cfg = load_config(write(tmp_path, {"licenseSecret": "ORG_GITLEAKS_KEY"}))
    out = render(build_plan(cfg))
    assert 'GITLEAKS_LICENSE: "${{ secrets.ORG_GITLEAKS_KEY }}"' in out


def test_default_output_is_a_strict_prefix_of_the_licensed_output(tmp_path):
    """Adopting licenseSecret must ADD a line and change nothing else --
    that is what makes the upgrade reviewable in a diff."""
    default = load_config(write(tmp_path, {}))
    plain = render(build_plan(default))
    licensed = read_golden("security-license.yml")
    assert licensed.startswith(plain.rstrip("\n"))


def test_licensed_output_still_grants_only_read_permissions(tmp_path):
    """A license changes what the job can authenticate as, not what the
    workflow token may do."""
    cfg = load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE"}))
    text = render(build_plan(cfg))
    block = text.split("permissions:\n", 1)[1].split("jobs:", 1)[0]
    for line in [l.strip() for l in block.splitlines() if l.strip()]:
        assert line.endswith(": read"), f"non-read permission granted: {line}"
