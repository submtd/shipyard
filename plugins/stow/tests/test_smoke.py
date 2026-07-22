"""Smoke tests: package version, plugin metadata, marketplace registration,
skill frontmatter, module importability, and an end-to-end render.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import stow

    assert stow.__version__ == "0.6.0"


def test_plugin_json_parses_and_names_stow():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "stow"
    assert plugin["version"] == "0.6.0"


def test_marketplace_lists_stow():
    marketplace = json.loads(
        (REPO / ".claude-plugin" / "marketplace.json").read_text()
    )
    names = [p["name"] for p in marketplace["plugins"]]
    assert "stow" in names


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


def test_init_skill_frontmatter_is_exactly_name_and_description():
    text = (PLUGIN_ROOT / "skills" / "init" / "SKILL.md").read_text()
    fields = _parse_frontmatter(text)
    assert set(fields) == {"name", "description"}
    assert fields["name"] == "init"


def test_every_stow_module_imports_cleanly():
    import importlib

    for name in ("stacks", "blocks", "config", "detect", "scaffold"):
        importlib.import_module(f"stow.{name}")


def test_end_to_end_render_from_fixture_config(tmp_path):
    from stow.blocks import apply_blocks
    from stow.config import load_config
    from stow.scaffold import desired_sections

    (tmp_path / ".stow.json").write_text(json.dumps({"stacks": {"python": {}}}))
    text = apply_blocks("", desired_sections(load_config(tmp_path)))
    assert text
    assert "# >>> stow:" in text
