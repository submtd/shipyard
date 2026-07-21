"""Repo-wide integrity guard for every plugins/*/skills/*/SKILL.md.

Hosted in keel because keel owns 11 of the suite's 16 skills and no plugin
validates skills it does not own; the suite's precedent is that repo-wide
guards live inside a plugin's tests directory (cf. the guard forbidding
plugins/*/tests/__init__.py). Filesystem reads only, no subprocess.

This is a ROT guard: everything it checks passes today. Its value is
coverage -- 11 of 16 SKILL.md files have no frontmatter validation at all,
and nothing checks that cross-plugin `plugin:skill` references resolve or
that the plugins/* directory set and marketplace.json agree.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


class FrontmatterError(Exception):
    """Raised when a SKILL.md frontmatter block is malformed."""


def parse_frontmatter(text):
    """Parse a SKILL.md leading `---` block into a dict of top-level keys.

    Pure: takes text, returns a dict, raises FrontmatterError. Kept
    separate from the filesystem so it can be tested against malformed
    input -- the repo is clean, so this is the only way to prove the
    guard can fail.
    """
    if not text.startswith("---\n"):
        raise FrontmatterError("frontmatter must open with '---' on line 1")
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError("frontmatter block is not closed")
    block = text[4:end]
    fields = {}
    for line in block.split("\n"):
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            raise FrontmatterError(f"frontmatter line is not a key: {line!r}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields


# Each negative test pins the SPECIFIC check that must fire. The inputs are
# chosen so exactly one check can catch them, and the `match=` assertion
# proves which one did. Without this, a test passes off the wrong branch and
# silently stops guarding what it names: text with no delimiter at all is
# caught by the unclosed-block check, not the opening-delimiter check, so
# neutering the opening check alone would leave every test green.
def test_parser_rejects_missing_opening_delimiter():
    # Closing delimiter present, opening absent -- only the open check can fire.
    with pytest.raises(FrontmatterError, match="open"):
        parse_frontmatter("name: init\ndescription: x\n---\n")


def test_parser_rejects_unclosed_block():
    with pytest.raises(FrontmatterError, match="not closed"):
        parse_frontmatter("---\nname: init\ndescription: x\n")


def test_parser_rejects_a_non_key_line():
    with pytest.raises(FrontmatterError, match="not a key"):
        parse_frontmatter("---\nname: init\ngarbage\n---\n")


def test_parser_extracts_exactly_the_top_level_keys():
    fields = parse_frontmatter("---\nname: init\ndescription: does a thing\n---\nbody\n")
    assert fields == {"name": "init", "description": "does a thing"}


def _plugin_names():
    return sorted(d.name for d in (REPO / "plugins").iterdir() if d.is_dir())


def _skill_files():
    return sorted(REPO.glob("plugins/*/skills/*/SKILL.md"))


SKILL_FILES = _skill_files()
REFERENCE_RE = re.compile(r"\b(" + "|".join(_plugin_names()) + r"):([a-z0-9][a-z0-9-]*)\b")


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_frontmatter_is_exactly_name_and_description(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert set(fields) == {"name", "description"}, (
        f"{skill_path} frontmatter keys must be exactly name+description"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_name_matches_its_directory(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert fields["name"] == skill_path.parts[-2]


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_description_is_non_empty(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert fields["description"].strip()


def test_every_cross_plugin_skill_reference_resolves():
    unresolved = []
    for skill_path in SKILL_FILES:
        for match in REFERENCE_RE.finditer(skill_path.read_text()):
            plugin, skill = match.group(1), match.group(2)
            if not (REPO / "plugins" / plugin / "skills" / skill / "SKILL.md").exists():
                unresolved.append(f"{skill_path}: {match.group(0)}")
    assert not unresolved, f"unresolved skill references: {unresolved}"


def test_plugins_dir_and_marketplace_agree():
    marketplace = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    listed = {p["name"] for p in marketplace["plugins"]}
    on_disk = set(_plugin_names())
    assert on_disk == listed, (
        f"plugin dirs not in marketplace: {on_disk - listed}; "
        f"marketplace entries with no dir: {listed - on_disk}"
    )


def test_guard_scans_a_nontrivial_corpus():
    assert len(SKILL_FILES) >= 16, f"expected >=16 SKILL.md files, found {len(SKILL_FILES)}"
    total_refs = sum(
        len(REFERENCE_RE.findall(p.read_text())) for p in SKILL_FILES
    )
    assert total_refs >= 1, "expected at least one cross-plugin skill reference"
