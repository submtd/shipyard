from __future__ import annotations

import pytest

from stow.blocks import CLOSER_RE, OPENER_RE, find_blocks, render_block
from stow.stacks import BASE, REGISTRY, STACK_IDS, StackSpec


def test_stow_version():
    import stow

    assert stow.__version__ == "0.4.0"


def test_registry_keys():
    assert tuple(REGISTRY) == ("python", "node")


def test_stack_ids_derived_from_registry():
    assert STACK_IDS == tuple(REGISTRY)


def test_base_spec():
    assert BASE.id == "base"
    assert BASE.detect_files == ()
    assert BASE.gitignore == (".DS_Store", "Thumbs.db")


def test_base_not_in_registry():
    assert "base" not in REGISTRY
    assert BASE not in REGISTRY.values()


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_id_matches_registry_key(key):
    assert REGISTRY[key].id == key


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_detect_files_is_tuple(key):
    assert isinstance(REGISTRY[key].detect_files, tuple)
    assert len(REGISTRY[key].detect_files) > 0


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_gitignore_is_non_empty_tuple(key):
    assert isinstance(REGISTRY[key].gitignore, tuple)
    assert len(REGISTRY[key].gitignore) > 0


def test_python_spec_contents():
    spec = REGISTRY["python"]
    assert spec.detect_files == (
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
    )
    assert spec.gitignore == (
        "__pycache__/",
        "*.py[cod]",
        "*.egg-info/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".venv/",
        "build/",
        "dist/",
    )


def test_node_spec_contents():
    spec = REGISTRY["node"]
    assert spec.detect_files == ("package.json",)
    assert spec.gitignore == (
        "node_modules/",
        "npm-debug.log*",
        "dist/",
        "coverage/",
        ".env",
    )


def test_stackspec_is_frozen_dataclass():
    spec = REGISTRY["python"]
    with pytest.raises(Exception):
        spec.id = "changed"


def test_base_is_frozen_dataclass():
    with pytest.raises(Exception):
        BASE.id = "changed"


ALL_SPECS = (BASE,) + tuple(REGISTRY.values())


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.id)
def test_gitignore_lines_have_no_newlines(spec: StackSpec):
    """Parser integrity: a gitignore body line must never itself span
    multiple lines, or it could smuggle a spoofed marker line into a
    managed block and confuse the block parser.
    """
    for line in spec.gitignore:
        assert "\n" not in line


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.id)
def test_gitignore_lines_do_not_collide_with_stow_marker(spec: StackSpec):
    """Parser integrity: a gitignore body line must never match stow's own
    block marker patterns, or emitting it would corrupt the managed block
    it lives in. Uses blocks.py's actual parser regexes (OPENER_RE /
    CLOSER_RE) -- the same `.match()` semantics the real parser uses in
    `find_blocks` -- as the single source of truth, rather than a
    hand-maintained copy that could silently drift from the real parser.
    """
    for line in spec.gitignore:
        assert not OPENER_RE.match(line)
        assert not CLOSER_RE.match(line)


@pytest.mark.parametrize("spec", ALL_SPECS, ids=lambda s: s.id)
def test_render_block_round_trips_through_find_blocks(spec: StackSpec):
    """Parser integrity, the other direction: every registry spec must
    render to exactly one well-formed, parseable block, with no malformed
    markers -- catching a bad spec.id or a body line that breaks the
    parser despite passing the line-level checks above."""
    well_formed, malformed = find_blocks(render_block(spec))
    assert well_formed == [(spec.id, 0, len(spec.gitignore) + 2)]
    assert malformed == []
