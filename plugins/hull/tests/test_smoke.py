"""Smoke tests: package version, plugin metadata, and marketplace
registration.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import hull

    assert hull.__version__ == "0.3.0"


def test_plugin_json_parses_and_names_hull():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "hull"
    assert plugin["version"] == "0.3.0"


def test_marketplace_lists_hull():
    marketplace = json.loads(
        (REPO / ".claude-plugin" / "marketplace.json").read_text()
    )
    names = [p["name"] for p in marketplace["plugins"]]
    assert "hull" in names
