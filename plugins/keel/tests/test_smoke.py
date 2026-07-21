"""Smoke tests: package version, plugin metadata, marketplace registration,
skill frontmatter, hook wiring, and module importability.

keel is the oldest and most-installed plugin in the suite and had the
thinnest smoke test of the six -- three lines asserting only __version__.
It was the only plugin whose plugin.json and marketplace registration went
unverified, and the only one shipping eleven SKILL.md files, none of which
were checked. This brings it up to the standard its juniors already meet,
plus the two things only keel has: hooks.json, and more than one skill.
"""
from __future__ import annotations

import importlib
import importlib.util
import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]

VERSION = "0.5.0"

#: Every skill keel ships. Listed explicitly rather than globbed so that
#: deleting a skill fails here instead of silently shrinking what's
#: checked. hooks/orient.py advertises the same list to the model at
#: session start, and a test below pins the two together.
SKILLS = (
    "doctor", "finish-work", "init", "land", "protect", "release",
    "respond-to-review", "review", "ship", "start-work", "sync",
)


def test_package_imports():
    import keel

    assert keel.__version__ == VERSION


def test_plugin_json_parses_and_names_keel():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "keel"
    assert plugin["version"] == VERSION


def test_marketplace_lists_keel():
    marketplace = json.loads(
        (REPO / ".claude-plugin" / "marketplace.json").read_text()
    )
    names = [p["name"] for p in marketplace["plugins"]]
    assert "keel" in names


def _parse_frontmatter(text: str) -> dict:
    assert text.startswith("---\n"), "SKILL.md must open with a frontmatter block"
    _, _, rest = text.partition("---\n")
    body, sep, _ = rest.partition("\n---\n")
    assert sep, "SKILL.md frontmatter block must be closed with '---'"
    fields = {}
    for line in body.splitlines():
        if not line.strip():
            continue
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def test_every_skill_directory_exists():
    found = sorted(p.name for p in (PLUGIN_ROOT / "skills").iterdir() if p.is_dir())
    assert found == sorted(SKILLS)


def test_every_skill_frontmatter_is_exactly_name_and_description():
    for skill in SKILLS:
        text = (PLUGIN_ROOT / "skills" / skill / "SKILL.md").read_text()
        fields = _parse_frontmatter(text)
        assert set(fields) == {"name", "description"}, skill
        assert fields["name"] == skill


def test_every_skill_description_is_non_empty():
    # The description is what the harness matches on to decide whether a
    # skill applies, so an empty one makes the skill unreachable.
    for skill in SKILLS:
        text = (PLUGIN_ROOT / "skills" / skill / "SKILL.md").read_text()
        assert _parse_frontmatter(text)["description"], skill


def test_orientation_advertises_exactly_the_shipped_skills():
    # orient.py names the skills to the model at session start. If that list
    # drifts from what's on disk it advertises skills that don't exist.
    spec = importlib.util.spec_from_file_location(
        "keel_orient_smoke", PLUGIN_ROOT / "hooks" / "orient.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # orient.py advertises them namespaced, as the user types them.
    assert sorted(module.SKILLS) == sorted(f"keel:{name}" for name in SKILLS)


def test_hooks_json_wires_both_hooks_from_the_plugin_root():
    doc = json.loads((PLUGIN_ROOT / "hooks" / "hooks.json").read_text())
    hooks = doc["hooks"]
    assert {"PreToolUse", "SessionStart"} <= set(hooks)
    # The guard only ever sees Bash tool calls; orientation fires at startup.
    assert hooks["PreToolUse"][0]["matcher"] == "Bash"
    assert hooks["SessionStart"][0]["matcher"] == "startup"
    blob = json.dumps(doc)
    assert "${CLAUDE_PLUGIN_ROOT}" in blob, (
        "hook commands must be rooted at ${CLAUDE_PLUGIN_ROOT} -- a path "
        "relative to the user's cwd resolves differently per session"
    )


def test_every_keel_module_imports_cleanly():
    for name in ("actions", "config", "facts", "ghio", "gitio", "render",
                 "rules", "scaffold"):
        importlib.import_module(f"keel.{name}")


def test_no_plugin_tests_dir_is_a_package():
    """Guard: a `tests/__init__.py` in any plugin turns its tests dir into a
    package, which under pytest's --import-mode=importlib silently shadows
    any sibling test file sharing a basename with a same-named file in
    another plugin's (non-package) tests dir.
    """
    offenders = sorted(REPO.glob("plugins/*/tests/__init__.py"))
    assert offenders == []
