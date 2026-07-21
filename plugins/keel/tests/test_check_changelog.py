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


def test_main_falls_back_to_non_origin_merge_base(tmp_path, monkeypatch, capsys):
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
    out = capsys.readouterr().out
    assert rc == 0
    assert calls[0] == ["merge-base", "origin/main", "HEAD"]
    assert calls[1] == ["merge-base", "main", "HEAD"]
    # Discriminating: rc == 0 is also produced by the "could not determine
    # merge base" warning-skip path, so it alone can't prove the fallback
    # sha was actually used. Assert the show step ran against the RESOLVED
    # sha, and that no warning was emitted on this (successful) path.
    assert ["show", "abc123:CHANGELOG.md"] in calls
    assert "::warning::" not in out


# --- non-UTF-8 CHANGELOG.md (FIX 3) -------------------------------------

def test_main_handles_non_utf8_changelog_without_crashing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    # A raw non-UTF-8 byte (0x92) in the working-tree file must not raise
    # UnicodeDecodeError; the gate should decode leniently and still detect
    # gained Unreleased content.
    (tmp_path / "CHANGELOG.md").write_bytes(
        b"# Changelog\n\n## [Unreleased]\n\n### Added\n- new thing \x92\n")
    before = "# Changelog\n\n## [Unreleased]\n"

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return before
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "feature/x"])
    assert rc == 0


# --- requireChangelog fail-safe (FIX 4) ---------------------------------

def test_load_cfg_require_changelog_zero_fails_safe(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({"requireChangelog": 0}))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["require_changelog"] is True


def test_load_cfg_require_changelog_null_fails_safe(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({"requireChangelog": None}))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["require_changelog"] is True


def test_load_cfg_require_changelog_explicit_false_still_disables(tmp_path):
    # A genuine bool False must still work -- only non-bool values fail safe.
    (tmp_path / ".keel.json").write_text(json.dumps({"requireChangelog": False}))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["require_changelog"] is False


# --- unknown topology validation (FIX 5) --------------------------------

def test_load_cfg_unknown_topology_degrades_to_known_value(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk "}))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["topology"] in ("gitflow", "trunk")
    assert cfg["topology"] != "trunk "


def test_load_cfg_valid_topology_passes_through(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    cfg = cc.load_cfg(tmp_path)
    assert cfg["topology"] == "trunk"


# --- fork bypass of trunk name-exemption (FIX 6) ------------------------

def test_main_fork_headed_main_not_exempt_under_trunk(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    monkeypatch.setenv("KEEL_PR_IS_FORK", "true")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "main"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_same_repo_head_named_main_still_exempt_under_trunk(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")
    # No KEEL_PR_IS_FORK set -- same-repo behavior must be unchanged: a head
    # named "main" is still exempt (this is also the local CLI invocation
    # path, where no CI env is present).
    rc = cc.main(["prog", "main", "main"])
    assert rc == 0


# --- fork never exempt: release/* prefix bypass (FIX 7) -----------------

def test_main_fork_headed_release_not_exempt_under_trunk(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    monkeypatch.setenv("KEEL_PR_IS_FORK", "true")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "release/1.0"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_fork_headed_release_not_exempt_under_gitflow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # No .keel.json -- defaults to gitflow topology.
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    monkeypatch.setenv("KEEL_PR_IS_FORK", "true")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "release/1.0"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_fork_headed_develop_not_exempt_under_gitflow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # No .keel.json -- defaults to gitflow topology, integration == "develop".
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    monkeypatch.setenv("KEEL_PR_IS_FORK", "true")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "develop"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_fork_headed_main_not_exempt_under_gitflow(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    # No .keel.json -- defaults to gitflow topology, production == "main".
    changelog = "# Changelog\n\n## [Unreleased]\n\n### Added\n- same thing\n"
    (tmp_path / "CHANGELOG.md").write_text(changelog)
    monkeypatch.setenv("KEEL_PR_IS_FORK", "true")

    def fake_run_git(args):
        if args[:1] == ["merge-base"]:
            return "abc123\n"
        if args[:1] == ["show"]:
            return changelog
        return None

    monkeypatch.setattr(cc, "_run_git", fake_run_git)
    rc = cc.main(["prog", "main", "main"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "::error::" in out


def test_main_same_repo_head_named_release_still_exempt_under_trunk(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")
    # No KEEL_PR_IS_FORK set -- same-repo behavior must be unchanged: a
    # legitimate internal release/* PR is still exempt under trunk.
    rc = cc.main(["prog", "main", "release/1.0"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "exempt" in out
