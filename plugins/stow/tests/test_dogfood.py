"""Drift guard: shipyard's own .gitignore must be exactly stow's rendered
output for shipyard's own .stow.json -- a byte-for-byte no-op -- and the
repo-custom `.superpowers/` line must remain a free line, outside every
managed block.

Regenerate with:
    python3 -c "import sys; sys.path.insert(0,'plugins/stow'); \
from stow.config import load_config; from stow.scaffold import desired_sections; \
from stow.blocks import apply_blocks; from pathlib import Path; \
p=Path('.gitignore'); p.write_text(apply_blocks(p.read_text(), desired_sections(load_config(Path('.')))))"
"""
from __future__ import annotations

from pathlib import Path

from stow.blocks import apply_blocks, find_blocks
from stow.config import load_config
from stow.scaffold import desired_sections

REPO = Path(__file__).resolve().parents[3]


def test_gitignore_matches_rendered_output_byte_for_byte():
    # The central-update integrity + round-trip guard: applying stow to
    # shipyard's own .stow.json against the committed .gitignore must be a
    # no-op. If this ever fails, the committed .gitignore has drifted from
    # what stow itself would produce.
    text = (REPO / ".gitignore").read_text()
    assert apply_blocks(text, desired_sections(load_config(REPO))) == text


def test_superpowers_line_is_present_and_free():
    # `.superpowers/` is shipyard's one repo-custom line -- it predates
    # stow and must survive the migration as a free line, untouched by any
    # managed block.
    text = (REPO / ".gitignore").read_text()
    lines = text.split("\n")
    assert ".superpowers/" in lines

    idx = lines.index(".superpowers/")
    well_formed, malformed = find_blocks(text)
    assert not malformed
    assert not any(start <= idx <= end for _id, start, end in well_formed)
