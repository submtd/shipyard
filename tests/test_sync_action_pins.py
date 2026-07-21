"""Tests for scripts/sync_action_pins.py.

The script exists because `.github/workflows/{ci,security}.yml` are rendered
output while Dependabot edits them as if they were source. Without it a
Dependabot PR can never go green. These tests pin the two properties that
make it trustworthy: it is a no-op on an already-consistent tree, and it
makes a simulated Dependabot bump consistent again.

They operate on a copy of the repo in tmp_path, so they never mutate the
working tree.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "scripts" / "sync_action_pins.py"

#: Enough of the repo for the script to run: the registries it rewrites, the
#: workflows it reads, the templates it mirrors, and the goldens it renders.
COPY = [
    "scripts", "plugins/rigging/rigging", "plugins/hull/hull",
    "plugins/rigging/tests/golden", "plugins/hull/tests/golden",
    "plugins/keel/templates", ".github/workflows",
    ".rigging.json", ".hull.json",
]

PIN_RE = re.compile(r"(?P<repo>[\w.\-]+/[\w.\-]+)@(?P<sha>[0-9a-f]{40})")


@pytest.fixture
def sandbox(tmp_path):
    for rel in COPY:
        src, dst = REPO / rel, tmp_path / rel
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    return tmp_path


def run_script(cwd):
    return subprocess.run(
        [sys.executable, str(cwd / "scripts" / "sync_action_pins.py")],
        cwd=cwd, capture_output=True, text=True, timeout=120,
    )


WORKFLOWS = [".github/workflows/ci.yml", ".github/workflows/security.yml",
             ".github/workflows/changelog.yml"]


def bump(root, action, sha, tag):
    """Bump `action` across EVERY workflow that mentions it.

    Dependabot updates all occurrences; bumping only some is a different
    scenario (a partial bump), which the script rejects outright -- so a
    helper that edited one file would be testing the conflict path by
    accident.
    """
    touched = 0
    for rel in WORKFLOWS:
        p = root / rel
        text = p.read_text(encoding="utf-8")
        new = re.sub(rf'({re.escape(action)}@)[0-9a-f]{{40}}("?\s*#\s*)v[\d.]+',
                     rf'\g<1>{sha}\g<2>{tag}', text)
        if new != text:
            p.write_text(new, encoding="utf-8")
            touched += 1
    assert touched, f"{action} not found in any workflow -- helper is stale"
    return touched


def snapshot(root):
    return {
        rel: (root / rel).read_text(encoding="utf-8")
        for rel in [
            "plugins/rigging/rigging/plan.py",
            "plugins/rigging/rigging/stacks.py",
            "plugins/hull/hull/plan.py",
            "plugins/hull/hull/scanners.py",
            ".github/workflows/ci.yml",
            ".github/workflows/security.yml",
        ]
    }


def test_script_is_a_no_op_on_a_consistent_tree(sandbox):
    # If this ever changes something on a clean checkout, the committed
    # artifacts have drifted from what the registries render -- which the
    # dogfood tests would also catch, but this says so directly.
    before = snapshot(sandbox)
    proc = run_script(sandbox)
    assert proc.returncode == 0, proc.stderr
    assert snapshot(sandbox) == before


def test_a_dependabot_style_bump_is_propagated_into_the_registries(sandbox):
    """The whole point: Dependabot edits only the rendered workflow, and the
    script has to carry that into the registry that renders it."""
    new_sha = "c" * 40
    bump(sandbox, "actions/checkout", new_sha, "v99")

    proc = run_script(sandbox)
    assert proc.returncode == 0, proc.stderr

    for rel in ["plugins/rigging/rigging/plan.py", "plugins/hull/hull/plan.py"]:
        text = (sandbox / rel).read_text()
        assert new_sha in text, f"{rel} did not pick up the new sha"
        assert '"v99"' in text, f"{rel} did not pick up the new version tag"


def test_registries_stay_importable_after_a_bump(sandbox):
    """Regression: the pin regex used to swallow the closing quote of
    `uses="owner/repo@<sha>"`, leaving an unterminated string -- a
    SyntaxError, so the plugin stopped importing at all."""
    bump(sandbox, "actions/checkout", "c" * 40, "v99")
    assert run_script(sandbox).returncode == 0

    for rel in ["plugins/rigging/rigging/plan.py", "plugins/hull/hull/scanners.py"]:
        proc = subprocess.run(
            [sys.executable, "-c", f"import ast; ast.parse(open({str(sandbox / rel)!r}).read())"],
            capture_output=True, text=True, timeout=30)
        assert proc.returncode == 0, f"{rel} is not parseable: {proc.stderr}"


def test_one_actions_tag_does_not_overwrite_anothers(sandbox):
    """Regression: rewriting `*_version` constants file-wide once per action
    set every constant in the file to whichever action was handled last.
    stacks.py pins setup-python and setup-node together, so bumping only one
    must leave the other's tag alone."""
    bump(sandbox, "actions/setup-python", "e" * 40, "v98")
    assert run_script(sandbox).returncode == 0

    stacks = (sandbox / "plugins/rigging/rigging/stacks.py").read_text()
    assert 'setup_uses_version="v98"' in stacks, "setup-python tag not applied"
    node_line = [l for l in stacks.split("\n") if "setup-node@" in l][0]
    idx = stacks.split("\n").index(node_line)
    following = "\n".join(stacks.split("\n")[idx:idx + 4])
    assert '"v98"' not in following, "setup-node's tag was overwritten by setup-python's"


def test_conflicting_pins_are_an_error_not_a_guess(sandbox):
    # A partial bump means the workflows disagree about one action. Picking a
    # winner silently would leave the other copy stale.
    # Deliberately partial: only one of the workflows that pin checkout.
    p = sandbox / ".github/workflows/security.yml"
    p.write_text(re.sub(r'(actions/checkout@)[0-9a-f]{40}',
                        r'\g<1>' + "f" * 40, p.read_text()), encoding="utf-8")
    proc = run_script(sandbox)
    assert proc.returncode != 0
    assert "conflicting pins" in (proc.stdout + proc.stderr)
