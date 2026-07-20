import json
from pathlib import Path

import pytest

from keel.scaffold import propose_config, classify_files
from keel.config import load_config, ConfigError


def test_no_develop_proposes_trunk():
    cfg = propose_config({"has_develop": False})
    assert cfg["topology"] == "trunk"
    assert cfg["branches"] == {"production": "main"}
    assert "integration" not in cfg["branches"]


def test_develop_proposes_gitflow_with_integration():
    cfg = propose_config({"has_develop": True})
    assert cfg["topology"] == "gitflow"
    assert cfg["branches"] == {"production": "main", "integration": "develop"}


def test_signals_flow_through():
    cfg = propose_config({
        "has_develop": False,
        "contributions": "fork",
        "review_policy": "approval",
        "require_changelog": False,
    })
    assert cfg["contributions"] == "fork"
    assert cfg["reviewPolicy"] == "approval"
    assert cfg["requireChangelog"] is False


def test_defaults_when_signals_absent():
    cfg = propose_config({"has_develop": False})
    assert cfg["contributions"] == "both"
    assert cfg["reviewPolicy"] == "review"
    assert cfg["requireChangelog"] is True


@pytest.mark.parametrize("has_develop", [True, False])
@pytest.mark.parametrize("contributions", ["fork", "branch", "both"])
@pytest.mark.parametrize("review_policy", ["approval", "review", "none"])
def test_every_proposed_config_round_trips_through_load_config(
        tmp_path, has_develop, contributions, review_policy):
    # The one non-negotiable guarantee: init can never write a .keel.json that
    # keel itself would reject.
    cfg = propose_config({
        "has_develop": has_develop,
        "contributions": contributions,
        "review_policy": review_policy,
    })
    (tmp_path / ".keel.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)  # must not raise
    assert loaded is not None
    assert loaded.topology == cfg["topology"]
    assert loaded.contributions == contributions
    assert loaded.review_policy == review_policy


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT")
    result = classify_files(tmp_path, ["LICENSE", "CHANGELOG.md", ".keel.json"])
    assert result == {"LICENSE": "present", "CHANGELOG.md": "absent",
                      ".keel.json": "absent"}


def test_classify_files_handles_nested_paths(tmp_path):
    nested = tmp_path / ".github" / "ISSUE_TEMPLATE"
    nested.mkdir(parents=True)
    (nested / "bug_report.md").write_text("x")
    result = classify_files(tmp_path, [".github/ISSUE_TEMPLATE/bug_report.md",
                                       ".github/PULL_REQUEST_TEMPLATE.md"])
    assert result == {".github/ISSUE_TEMPLATE/bug_report.md": "present",
                      ".github/PULL_REQUEST_TEMPLATE.md": "absent"}
