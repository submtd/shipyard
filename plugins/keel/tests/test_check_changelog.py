import importlib.util
import json
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


# --- load_cfg degrade tests ---------------------------------------------

def test_load_cfg_no_file_yields_defaults(tmp_path):
    cfg = cc.load_cfg(tmp_path)
    assert cfg == {
        "topology": "gitflow",
        "production": "main",
        "integration": "develop",
        "feature_prefix": "feature/",
        "release_prefix": "release/",
        "hotfix_prefix": "hotfix/",
        "require_changelog": True,
    }


def test_load_cfg_invalid_json_yields_defaults(tmp_path):
    (tmp_path / ".keel.json").write_text("{not valid json")
    cfg = cc.load_cfg(tmp_path)
    assert cfg == {
        "topology": "gitflow",
        "production": "main",
        "integration": "develop",
        "feature_prefix": "feature/",
        "release_prefix": "release/",
        "hotfix_prefix": "hotfix/",
        "require_changelog": True,
    }


def test_load_cfg_top_level_array_yields_defaults(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps([1, 2, 3]))
    cfg = cc.load_cfg(tmp_path)
    assert cfg == {
        "topology": "gitflow",
        "production": "main",
        "integration": "develop",
        "feature_prefix": "feature/",
        "release_prefix": "release/",
        "hotfix_prefix": "hotfix/",
        "require_changelog": True,
    }


def test_load_cfg_degrades_wrong_typed_values(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({
        "topology": 7,
        "branches": {"production": 5, "integration": []},
        "prefixes": {"feature": 5, "release": [], "hotfix": None},
    }))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["topology"] == "gitflow"
    assert cfg["production"] == "main"
    assert cfg["integration"] == "develop"
    assert cfg["feature_prefix"] == "feature/"
    assert cfg["release_prefix"] == "release/"
    assert cfg["hotfix_prefix"] == "hotfix/"
    # Must not raise for any branch name -- this is the crash this test guards.
    for name in ("feature/x", "release/1.0", "hotfix/y", "main", "develop",
                 "other/thing", "", "5"):
        cc.kind_of_branch(name, cfg)


# --- main() merge-base tests --------------------------------------------

def test_main_gate_fails_when_unreleased_matches_merge_base(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            assert args[1] == "abc123:CHANGELOG.md"
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_gate_passes_when_unreleased_gained_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- new thing\n")
    before = "# Changelog\n\n## [Unreleased]\n\n### Added\n- old thing\n"

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return before
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    assert rc == 0


def test_main_warns_when_merge_base_unresolvable(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")
    calls = []

    def fake_run_git(args):
        calls.append(args)
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "::warning::" in out
    assert "merge base" in out.lower()
    # Both merge-base invocations must have been attempted; no "show" call
    # should happen once the merge base is unresolvable.
    assert calls == [["merge-base", "origin/main", "HEAD"], ["merge-base", "main", "HEAD"]]


def test_main_warns_when_changelog_unreadable_at_merge_base(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "::warning::" in out
    # The warning must reference the resolved merge-base sha, not the base ref.
    assert "abc123" in out


def test_main_falls_back_to_non_origin_merge_base(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- new thing\n")
    before = "# Changelog\n\n## [Unreleased]\n"
    calls = []

    def fake_run_git(args):
        calls.append(args)
        if args[:1] == ["merge-base"]:
            if args[1].startswith("origin/"):
                return None
            return "abc123\n"
        if args[:1] == ["show"]:
            return before
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    assert rc == 0
    assert calls[0] == ["merge-base", "origin/main", "HEAD"]
    assert calls[1] == ["merge-base", "main", "HEAD"]
