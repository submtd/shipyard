"""Tests for the PreToolUse hook entrypoint (hooks/guard.py).

guard.py lives outside the `keel` package (it is the plugin's hook script,
loaded directly by Claude Code via `python3 .../hooks/guard.py`), so it is
imported here via importlib rather than a normal package import.
"""
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

GUARD_PATH = Path(__file__).resolve().parents[1] / "hooks" / "guard.py"


def load_guard():
    spec = importlib.util.spec_from_file_location("keel_guard", GUARD_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def guard():
    return load_guard()


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


def run_guard(guard_module, monkeypatch, capsys, command, cwd, tool_name="Bash"):
    event = {
        "tool_name": tool_name,
        "cwd": str(cwd),
        "session_id": "s1",
        "tool_input": {"command": command},
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
    exit_code = guard_module.run()
    out = capsys.readouterr().out.strip()
    return exit_code, out


def test_non_bash_tool_produces_no_output(guard, monkeypatch, capsys, tmp_path):
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x",
                                tmp_path, tool_name="Read")
    assert out == ""
    assert exit_code == 0


def test_unclassifiable_command_produces_no_output(guard, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git status", repo)
    assert out == ""
    assert exit_code == 0


def test_not_a_git_repo_produces_no_output(guard, monkeypatch, capsys, tmp_path):
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x", tmp_path)
    assert out == ""
    assert exit_code == 0


def test_repo_with_no_config_produces_no_output(guard, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x", repo)
    assert out == ""
    assert exit_code == 0


def test_malformed_config_warns_and_does_not_block(guard, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("not json{{{")
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x", repo)
    assert exit_code == 0
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "keel" in payload["systemMessage"]
    assert "permissionDecision" not in payload.get("hookSpecificOutput", {})


def test_commit_on_protected_branch_denies(guard, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x", repo)
    assert exit_code == 0
    payload = json.loads(out)
    hso = payload["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "protected-write" in hso["permissionDecisionReason"]


def test_failed_gh_call_warns_not_blocks_on_merge(guard, monkeypatch, capsys, tmp_path):
    """Correction 2: gh unreachable (pr_facts -> None) must never be
    flattened into a confident 'no review' block."""
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")
    monkeypatch.setattr(guard.ghio, "pr_facts", lambda number, cwd=None: None)
    exit_code, out = run_guard(guard, monkeypatch, capsys,
                                "gh pr merge --squash 5", repo)
    assert exit_code == 0
    assert out != "", "expected a warn systemMessage, got no output"
    payload = json.loads(out)
    assert "hookSpecificOutput" not in payload or \
        "permissionDecision" not in payload["hookSpecificOutput"]
    assert "systemMessage" in payload


def test_unexpected_internal_exception_is_swallowed(guard, monkeypatch, capsys, tmp_path):
    repo, _ = init_repo(tmp_path)
    (repo / ".keel.json").write_text("{}")

    def boom(cwd=None):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(guard.gitio, "current_branch", boom)
    exit_code, out = run_guard(guard, monkeypatch, capsys, "git commit -m x", repo)
    assert exit_code == 0
    payload = json.loads(out)
    assert "systemMessage" in payload
    assert "kaboom" in payload["systemMessage"]
    assert "hookSpecificOutput" not in payload or \
        "permissionDecision" not in payload["hookSpecificOutput"]
