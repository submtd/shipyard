import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "check_changelog", REPO / "scripts" / "check_changelog.py")
cc = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cc)


def test_no_keel_import_anywhere():
    src = (REPO / "scripts" / "check_changelog.py").read_text()
    assert "import keel" not in src and "from keel" not in src


def test_unreleased_body_collects_nested_subheadings():
    text = "# Changelog\n\n## [Unreleased]\n\n### Added\n- a thing\n\n## 1.0.0\n\n### Added\n- old\n"
    body = cc.unreleased_body(text)
    assert "a thing" in body
    assert "old" not in body


def test_unreleased_body_empty_when_no_entries():
    text = "# Changelog\n\n## [Unreleased]\n\n## 1.0.0\n- old\n"
    assert cc.unreleased_body(text).strip() == ""


def test_kind_of_branch_matches_prefixes():
    cfg = {"topology": "trunk", "production": "main", "integration": "main",
           "feature_prefix": "feature/", "release_prefix": "release/",
           "hotfix_prefix": "hotfix/"}
    assert cc.kind_of_branch("release/1.0", cfg) == "release"
    assert cc.kind_of_branch("fix/x", cfg) == "other"
    assert cc.kind_of_branch("main", cfg) == "production"
