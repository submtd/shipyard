"""Smoke tests: package version, plugin metadata, and marketplace
registration.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import bosun

    assert isinstance(bosun.__version__, str)
    assert re.fullmatch(r"\d+\.\d+\.\d+", bosun.__version__), bosun.__version__


def test_plugin_json_parses_and_names_bosun():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "bosun"
    assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"]), plugin["version"]


def test_marketplace_lists_bosun():
    marketplace = json.loads(
        (REPO / ".claude-plugin" / "marketplace.json").read_text()
    )
    names = [p["name"] for p in marketplace["plugins"]]
    assert "bosun" in names
