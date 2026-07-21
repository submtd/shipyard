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
        load_config(write(tmp_path, {"scanner": "trufflehog"}))
    msg = str(e.value)
    assert "scanner" in msg
    assert "trufflehog" in msg
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
