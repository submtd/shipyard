"""Tests for hull's scaffold helpers.

Mirrors rigging/tests/test_scaffold.py's shape: propose_config round-trips
through config.load_config, bad fields raise ValueError naming the field,
SECURITY_FILES rejects path-escaping names, classify_files reports
present/absent for both flat and nested candidate paths.
"""
from __future__ import annotations

import json

import pytest

from hull.config import load_config
from hull.scanners import SCANNER_IDS
from hull.scaffold import SECURITY_FILES, classify_files, propose_config


def test_propose_config_defaults():
    cfg = propose_config({})
    assert cfg == {"name": "security", "scanner": "gitleaks"}


def test_propose_config_defaults_round_trip_through_load_config(tmp_path):
    cfg = propose_config({})
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert loaded.name == "security"
    assert loaded.scanner == "gitleaks"


def test_propose_config_explicit_signals_round_trip_through_load_config(tmp_path):
    cfg = propose_config({"name": "my-Scan_1", "scanner": "gitleaks"})
    assert cfg == {"name": "my-Scan_1", "scanner": "gitleaks"}
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert loaded.name == "my-Scan_1"
    assert loaded.scanner == "gitleaks"


@pytest.mark.parametrize("bad_name", ["a/b", "../evil", "${{ github.token }}", "a.b", "", 5])
def test_propose_config_bad_name_raises_value_error_naming_field(bad_name):
    with pytest.raises(ValueError, match="name"):
        propose_config({"name": bad_name})


@pytest.mark.parametrize("bad_scanner", ["trufflehog", "", 5])
def test_propose_config_unknown_scanner_raises_value_error_naming_field(bad_scanner):
    with pytest.raises(ValueError, match="scanner"):
        propose_config({"scanner": bad_scanner})


def test_propose_config_scanner_ids_are_all_valid():
    for scanner_id in SCANNER_IDS:
        cfg = propose_config({"scanner": scanner_id})
        assert cfg["scanner"] == scanner_id


def test_security_files_returns_expected_paths_for_valid_name():
    assert SECURITY_FILES("security") == [
        ".hull.json",
        ".github/workflows/security.yml",
    ]


def test_security_files_uses_provided_name_in_workflow_path():
    assert SECURITY_FILES("my-Scan_1") == [
        ".hull.json",
        ".github/workflows/my-Scan_1.yml",
    ]


@pytest.mark.parametrize("bad_name", ["../evil", "a/b", "${{ x }}", "a.b", ""])
def test_security_files_rejects_path_escaping_name(bad_name):
    with pytest.raises(ValueError, match="name"):
        SECURITY_FILES(bad_name)


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / ".hull.json").write_text("{}")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "present",
        ".github/workflows/security.yml": "absent",
    }


def test_classify_files_handles_nested_workflow_path(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "security.yml").write_text("x")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "absent",
        ".github/workflows/security.yml": "present",
    }


def test_classify_files_both_absent(tmp_path):
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "absent",
        ".github/workflows/security.yml": "absent",
    }


def test_classify_files_both_present(tmp_path):
    (tmp_path / ".hull.json").write_text("{}")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "security.yml").write_text("x")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "present",
        ".github/workflows/security.yml": "present",
    }
