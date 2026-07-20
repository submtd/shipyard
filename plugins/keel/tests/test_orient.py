"""Tests for the SessionStart hook entrypoint (hooks/orient.py).

orient.py lives outside the `keel` package (it is the plugin's hook script,
loaded directly by Claude Code via `python3 .../hooks/orient.py`), so it is
imported here via importlib rather than a normal package import -- same
pattern as test_guard.py.
"""
import importlib.util
import json
import subprocess
from pathlib import Path

import pytest

ORIENT_PATH = Path(__file__).resolve().parents[1] / "hooks" / "orient.py"


def load_orient():
    spec = importlib.util.spec_from_file_location("keel_orient", ORIENT_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def orient():
    return load_orient()


def init_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "README.md").write_text("hi\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    return tmp_path, git


def run_orient(orient_module, monkeypatch, capsys, cwd):
    monkeypatch.chdir(cwd)
    exit_code = orient_module.run()
    out = capsys.readouterr().out.strip()
    return exit_code, out


def test_not_a_git_repo_produces_no_output(orient, monkeypatch, capsys, tmp_path):
    exit_code, out = run_orient(orient, monkeypatch, capsys, tmp_path)
    assert out == ""
    assert exit_code == 0


def test_no_config_produces_no_output(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert out == ""
    assert exit_code == 0


def test_malformed_config_says_keel_inactive_and_does_not_raise(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("not json{{{")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    payload = json.loads(out)
    assert "keel" in payload["additionalContext"]
    assert "inactive" in payload["additionalContext"]


def test_gitflow_config_names_topology_branches_policy_and_current_branch(orient, monkeypatch, capsys, tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / ".keel.json").write_text(json.dumps({
        "topology": "gitflow",
        "branches": {"production": "main", "integration": "develop"},
        "reviewPolicy": "approval",
    }))
    git("branch", "develop")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    payload = json.loads(out)
    ctx = payload["additionalContext"]
    assert "gitflow" in ctx
    assert "main" in ctx
    assert "develop" in ctx
    assert "approval" in ctx
    assert "main" in ctx.split("Current branch:")[1]


def test_trunk_config_describes_trunk_flow_without_integration_or_release(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text(json.dumps({"topology": "trunk"}))
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    payload = json.loads(out)
    ctx = payload["additionalContext"]
    assert "trunk" in ctx
    assert "main" in ctx
    # No separate integration branch or release branches for trunk.
    assert "develop" not in ctx
    assert "release/" not in ctx
    # Protected list must not list a distinct integration branch alongside production.
    protected_line = [l for l in ctx.splitlines() if l.startswith("- Protected:")][0]
    assert protected_line.count(",") == 0


def test_on_protected_branch_includes_start_work_nudge(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    payload = json.loads(out)
    assert "keel:start-work" in payload["additionalContext"]
    assert "protected branch 'main'" in payload["additionalContext"]


def test_on_feature_branch_omits_start_work_nudge(orient, monkeypatch, capsys, tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    git("checkout", "-qb", "feature/x")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    payload = json.loads(out)
    ctx = payload["additionalContext"]
    assert "Start work with" not in ctx
    assert "Current branch: feature/x" in ctx


def test_lists_all_ten_skills(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    payload = json.loads(out)
    ctx = payload["additionalContext"]
    for skill in ("keel:start-work", "keel:finish-work", "keel:respond-to-review",
                  "keel:sync", "keel:review", "keel:land", "keel:release",
                  "keel:ship", "keel:protect", "keel:doctor"):
        assert skill in ctx


def test_states_hook_is_advisory_and_branch_protection_is_real_boundary(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    payload = json.loads(out)
    ctx = payload["additionalContext"].lower()
    assert "advisory" in ctx
    assert "branch protection" in ctx
    assert "keel:protect" in ctx


def test_unexpected_internal_exception_is_swallowed(orient, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")

    def boom():
        raise RuntimeError("kaboom")

    monkeypatch.setattr(orient.gitio, "current_branch", boom)
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    assert exit_code == 0
    assert out == ""


# The two "produces no output" tests above go through run(), whose blanket
# except Exception would swallow an AttributeError from a removed guard and
# yield the same empty output. These call main() directly, with no exception
# net, so deleting either early return makes them fail loudly.

def test_no_config_guard_is_load_bearing(orient, monkeypatch, capsys, tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    monkeypatch.chdir(tmp_path)
    assert orient.main() == 0
    assert capsys.readouterr().out == ""


def test_not_a_git_repo_guard_is_load_bearing(orient, monkeypatch, capsys, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orient.gitio, "repo_root", lambda *a, **k: None)
    assert orient.main() == 0
    assert capsys.readouterr().out == ""


def test_orientation_notes_changes_requested_always_blocks(orient, monkeypatch, capsys, tmp_path):
    # doctor/SKILL.md says CHANGES_REQUESTED always blocks regardless of
    # reviewPolicy; orientation must say the same thing so the two do not
    # disagree about what keel enforces.
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text(json.dumps({"reviewPolicy": "none"}))
    exit_code, out = run_orient(orient, monkeypatch, capsys, repo)
    payload = json.loads(out)
    ctx = payload["additionalContext"]
    assert "CHANGES_REQUESTED" in ctx


def test_single_protected_branch_reads_it_not_them(orient):
    from keel.config import Config
    cfg = Config(topology="trunk", production="main", integration="main",
                 feature_prefix="feature/", release_prefix="release/",
                 hotfix_prefix="hotfix/", contributions="both",
                 review_policy="review", merge_to_integration="squash",
                 merge_to_production="merge", require_changelog=True)
    text = orient.orientation(cfg, "feature/x")
    assert "changes reach it via PR" in text
    assert "reach them via PR" not in text
