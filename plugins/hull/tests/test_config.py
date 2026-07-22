"""Loader/validator tests for .hull.json.

Mirrors rigging/tests/test_config.py's shape: absent config, malformed
JSON, non-object root, defaults, explicit values, and injection-shaped
name rejection (fullmatch, not match -- a trailing newline or an
embedded `${{ ... }}` expression must not slip through).
"""
from __future__ import annotations

import json

import pytest

from hull.config import Config, ConfigError, load_config


def write(tmp_path, data):
    (tmp_path / ".hull.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".hull.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".hull.json" in str(e.value)


def test_non_object_root_raises(tmp_path):
    (tmp_path / ".hull.json").write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_empty_object_yields_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {}))
    assert cfg == Config(name="security", scanner="gitleaks")


def test_explicit_values_preserved(tmp_path):
    cfg = load_config(write(tmp_path, {"name": "my-Scan_1", "scanner": "gitleaks"}))
    assert cfg.name == "my-Scan_1"
    assert cfg.scanner == "gitleaks"


def test_name_with_trailing_newline_raises(tmp_path):
    """Proves fullmatch (not match/search) is used -- `$` in a naive regex
    would let a trailing newline slip through re.match."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"name": "security\n"}))
    assert "name" in str(e.value)


@pytest.mark.parametrize("name", ["a/b", "../x", "${{ github.token }}"])
def test_invalid_name_raises_naming_field(tmp_path, name):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"name": name}))
    assert "name" in str(e.value)


def test_unknown_scanner_raises_naming_scanner_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"scanner": "semgrep"}))
    msg = str(e.value)
    assert "scanner" in msg
    assert "semgrep" in msg
    assert "gitleaks" in msg


def test_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {}))
    assert isinstance(cfg, Config)
    with pytest.raises(Exception):
        cfg.name = "changed"


# --- unknown keys ----------------------------------------------------------


def test_unknown_top_level_key_raises_naming_it(tmp_path):
    # A user who writes "permissions" believes they configured the
    # workflow's token scope. They didn't, and nothing said so.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"name": "security", "permissions": "write-all"}))
    assert "permissions" in str(e.value)


def test_known_keys_together_still_load(tmp_path):
    cfg = load_config(write(tmp_path, {"name": "security", "scanner": "gitleaks"}))
    assert (cfg.name, cfg.scanner) == ("security", "gitleaks")


# --- pushBranches -------------------------------------------------------


def test_push_branches_defaults_to_the_conventional_trunk(tmp_path):
    (tmp_path / ".hull.json").write_text(json.dumps({"scanner": "gitleaks"}))
    assert load_config(tmp_path).push_branches == ("main",)


def test_push_branches_is_read_from_the_config(tmp_path):
    cfg = dict({"scanner": "gitleaks"}, pushBranches=["main", "release/1.x"])
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).push_branches == ("main", "release/1.x")


@pytest.mark.parametrize("bad", [[], "main", {}, [""], ["a b"], [1], ["-x"], ["a$b"]])
def test_push_branches_rejects_what_it_cannot_safely_render(tmp_path, bad):
    """The value is rendered straight into YAML, so anything needing quoting
    or escaping is refused rather than emitted and hoped for. An empty list
    is refused too: it renders `branches: []`, which silently disables push
    CI entirely -- exactly the failure the key exists to prevent."""
    cfg = dict({"scanner": "gitleaks"}, pushBranches=bad)
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


# --- licenseSecret ---------------------------------------------------------
#
# Issue #24: gitleaks-action v3 exits 1 for an organization-owned repo when
# GITLEAKS_LICENSE is unset, and .hull.json had no slot to supply it -- so
# hull:init committed a workflow that could not pass and offered no fix. The
# key holds a secret NAME, never a key, and lands inside a
# `${{ secrets.<NAME> }}` expression, which is why it is validated far more
# strictly than any other string in this file.


def test_license_secret_defaults_to_none(tmp_path):
    assert load_config(write(tmp_path, {})).license_secret is None


def test_license_secret_is_read_from_the_config(tmp_path):
    cfg = load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE"}))
    assert cfg.license_secret == "GITLEAKS_LICENSE"


def test_license_secret_accepts_a_leading_underscore(tmp_path):
    """GitHub allows an underscore-leading secret name, so hull must too --
    strict is not the same as arbitrary."""
    cfg = load_config(write(tmp_path, {"licenseSecret": "_MY_LICENSE_2"}))
    assert cfg.license_secret == "_MY_LICENSE_2"


@pytest.mark.parametrize("bad", [
    "${{ secrets.X }}",          # a whole expression, not a name
    "X }} ${{ github.token",     # closes hull's expression and opens another
    'X" \n on: {}',              # breaks out of the quoted scalar
    "MY-LICENSE",                # dash: not a GitHub secret name
    "MY.LICENSE",                # dot: would read as a context path
    "MY LICENSE",                # whitespace
    "1LICENSE",                  # leading digit
    "",
    5,
    [],
])
def test_license_secret_rejects_what_it_cannot_safely_interpolate(tmp_path, bad):
    """Every one of these would either restructure the Actions expression
    hull wraps it in or the YAML around it. Refused at load time so the
    renderer is never handed one."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"licenseSecret": bad}))
    assert "licenseSecret" in str(e.value)


def test_license_secret_with_trailing_newline_raises(tmp_path):
    """Same fullmatch proof as `name` above: a naive `$` anchor under
    re.match would let a trailing newline -- and the YAML break it implies --
    straight through."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE\n"}))
    assert "licenseSecret" in str(e.value)


def test_all_known_keys_together_still_load(tmp_path):
    cfg = load_config(write(tmp_path, {
        "name": "security",
        "scanner": "gitleaks",
        "pushBranches": ["main", "develop"],
        "licenseSecret": "GITLEAKS_LICENSE",
    }))
    assert cfg == Config(name="security", scanner="gitleaks",
                         push_branches=("main", "develop"),
                         license_secret="GITLEAKS_LICENSE")


def test_license_secret_rejected_for_a_scanner_with_no_license_gate(tmp_path, monkeypatch):
    """A `licenseSecret` set for a scanner that has nowhere to put it is not
    harmless -- it is a user believing they configured something that is
    silently discarded, which is the exact failure the unknown-key check
    exists to prevent. Every registered scanner today has a license gate, so
    the licenseless case is staged with a patched registry entry rather than
    left untested until a second scanner lands."""
    import dataclasses

    from hull import scanners

    licenseless = dataclasses.replace(scanners.REGISTRY["gitleaks"],
                                      license_env=None)
    monkeypatch.setitem(scanners.REGISTRY, "gitleaks", licenseless)

    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE"}))
    assert "licenseSecret" in str(e.value)
