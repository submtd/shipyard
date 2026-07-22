"""Smoke tests: package version, plugin metadata, marketplace registration,
skill frontmatter, module importability, and an end-to-end render.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PLUGIN_ROOT = Path(__file__).resolve().parents[1]


def test_package_imports():
    import ballast

    assert ballast.__version__ == "0.6.0"


def test_plugin_json_parses_and_names_ballast():
    plugin = json.loads((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert plugin["name"] == "ballast"
    assert plugin["version"] == "0.6.0"


def test_marketplace_lists_ballast():
    marketplace = json.loads(
        (REPO / ".claude-plugin" / "marketplace.json").read_text()
    )
    names = [p["name"] for p in marketplace["plugins"]]
    assert "ballast" in names


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


def test_every_ballast_module_imports_cleanly():
    import importlib

    for name in ("stacks", "config", "detect", "render", "scaffold"):
        importlib.import_module(f"ballast.{name}")


def test_end_to_end_render_from_fixture_config(tmp_path):
    from ballast.config import load_config
    from ballast.render import render

    (tmp_path / ".ballast.json").write_text(
        json.dumps({"stacks": {"python": {}}})
    )
    text = render(load_config(tmp_path))
    assert text
    assert text.startswith("[pytest]")


def test_no_plugin_tests_dir_is_a_package():
    """Guard: a `tests/__init__.py` in any plugin turns its tests dir into a
    package, which under pytest's --import-mode=importlib silently shadows
    any sibling test file sharing a basename with a same-named file in
    another plugin's (non-package) tests dir. Every plugin's tests dir must
    stay a plain, unpackaged directory. Rigging's test_smoke.py already runs
    this repo-wide guard; it's duplicated here for stow/rigging-parity so
    ballast's own suite also fails loudly if its tests dir regresses into a
    package.
    """
    offenders = sorted(REPO.glob("plugins/*/tests/__init__.py"))
    assert offenders == []
