"""Repo-level guards that no single plugin owns.

Each plugin's own smoke test asserts that *it* appears in marketplace.json.
Nothing asserted the inverse -- a marketplace entry pointing at a directory
that doesn't exist, or a plugin directory nobody registered, both shipped
green. These are the checks that only make sense from the repo root.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MARKETPLACE = json.loads((REPO / ".claude-plugin" / "marketplace.json").read_text())
PLUGIN_DIRS = sorted(p.name for p in (REPO / "plugins").iterdir() if p.is_dir())


def test_every_marketplace_entry_points_at_a_real_directory():
    for entry in MARKETPLACE["plugins"]:
        source = (REPO / entry["source"]).resolve()
        assert source.is_dir(), f"{entry['name']}: {entry['source']} does not exist"
        assert (source / ".claude-plugin" / "plugin.json").is_file(), (
            f"{entry['name']}: no plugin.json at {entry['source']}"
        )


def test_every_plugin_directory_is_registered():
    registered = {entry["name"] for entry in MARKETPLACE["plugins"]}
    assert set(PLUGIN_DIRS) == registered


def test_marketplace_name_matches_the_plugin_json_it_points_at():
    for entry in MARKETPLACE["plugins"]:
        plugin = json.loads(
            (REPO / entry["source"] / ".claude-plugin" / "plugin.json").read_text()
        )
        assert plugin["name"] == entry["name"]


def test_plugin_json_version_matches_the_package_version():
    """plugin.json and <pkg>/__init__.py both carry a version. They are
    edited in different places and nothing forced them to agree.
    """
    import re

    for name in PLUGIN_DIRS:
        plugin = json.loads(
            (REPO / "plugins" / name / ".claude-plugin" / "plugin.json").read_text()
        )
        init = (REPO / "plugins" / name / name / "__init__.py").read_text()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init)
        assert match, f"{name}: no __version__ in {name}/__init__.py"
        assert match.group(1) == plugin["version"], (
            f"{name}: plugin.json says {plugin['version']}, "
            f"__init__.py says {match.group(1)}"
        )


def test_every_plugin_ships_at_least_one_skill():
    for name in PLUGIN_DIRS:
        skills = sorted((REPO / "plugins" / name / "skills").glob("*/SKILL.md"))
        assert skills, f"{name}: no SKILL.md found"
