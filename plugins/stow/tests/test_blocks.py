from __future__ import annotations

import pytest

from stow.blocks import (
    CLOSER_RE,
    MARKER_RE,
    OPENER_RE,
    StowError,
    apply_blocks,
    find_blocks,
    render_block,
)
from stow.stacks import BASE, REGISTRY, StackSpec

# Duplicated deliberately (not imported from stow.blocks) so a change to the
# advisory text is caught by these tests rather than silently agreeing with
# itself.
ADVISORY_LINE = (
    "# managed by stow — edits inside this block are overwritten; "
    "put custom entries outside it"
)

PYTHON = REGISTRY["python"]
NODE = REGISTRY["node"]


def _block_lines(spec: StackSpec) -> list:
    """Build the expected lines for spec's block using *live* stacks.py
    data -- used by tests that are not themselves about pinning exact
    gitignore contents."""
    return [
        f"# >>> stow:{spec.id} >>>",
        ADVISORY_LINE,
        *spec.gitignore,
        f"# <<< stow:{spec.id} <<<",
    ]


def _block_text(spec: StackSpec) -> str:
    return "\n".join(_block_lines(spec))


# ---------------------------------------------------------------------------
# render_block
# ---------------------------------------------------------------------------


def test_render_block_is_deterministic():
    assert render_block(BASE) == render_block(BASE)
    assert render_block(PYTHON) == render_block(PYTHON)


def test_render_block_has_no_trailing_newline():
    assert not render_block(BASE).endswith("\n")
    assert not render_block(PYTHON).endswith("\n")


def test_render_block_has_no_blank_line_inside():
    assert "" not in render_block(BASE).split("\n")
    assert "" not in render_block(PYTHON).split("\n")


def test_render_block_starts_with_opener_and_ends_with_closer():
    lines = render_block(PYTHON).split("\n")
    assert lines[0] == "# >>> stow:python >>>"
    assert lines[-1] == "# <<< stow:python <<<"


def test_render_block_contains_advisory_and_body():
    lines = render_block(PYTHON).split("\n")
    assert lines[1] == ADVISORY_LINE
    assert lines[2:-1] == list(PYTHON.gitignore)


def test_render_block_matches_live_helper():
    assert render_block(BASE) == _block_text(BASE)
    assert render_block(PYTHON) == _block_text(PYTHON)


# ---------------------------------------------------------------------------
# create == apply_blocks("", desired) -- known expected string
# ---------------------------------------------------------------------------


def test_create_from_scratch_matches_known_expected_string():
    expected_lines = [
        "# >>> stow:base >>>",
        ADVISORY_LINE,
        ".DS_Store",
        "Thumbs.db",
        "# <<< stow:base <<<",
        "",
        "# >>> stow:python >>>",
        ADVISORY_LINE,
        "__pycache__/",
        "*.py[cod]",
        "*.egg-info/",
        ".pytest_cache/",
        ".mypy_cache/",
        ".ruff_cache/",
        ".venv/",
        "build/",
        "dist/",
        "# <<< stow:python <<<",
    ]
    expected = "\n".join(expected_lines) + "\n"
    assert apply_blocks("", [BASE, PYTHON]) == expected


def test_create_is_the_general_algorithm_not_a_special_case():
    desired = [BASE, PYTHON, NODE]
    assert apply_blocks("", desired) == apply_blocks("", desired)


def test_apply_blocks_empty_existing_empty_desired_is_empty_string():
    assert apply_blocks("", []) == ""


# ---------------------------------------------------------------------------
# append when absent / replace in place when present
# ---------------------------------------------------------------------------


def test_append_when_section_absent():
    existing = "\n".join([".superpowers/", "# a plain comment"]) + "\n"
    result = apply_blocks(existing, [PYTHON])
    expected = (
        "\n".join([".superpowers/", "# a plain comment"])
        + "\n\n"
        + _block_text(PYTHON)
        + "\n"
    )
    assert result == expected


def test_replace_in_place_updates_stale_body_at_same_position():
    existing = (
        "\n".join(
            [
                "free before",
                "# >>> stow:python >>>",
                ADVISORY_LINE,
                "THIS_IS_A_STALE_BODY_LINE",
                "# <<< stow:python <<<",
                "free after",
            ]
        )
        + "\n"
    )
    result = apply_blocks(existing, [PYTHON])
    expected = (
        "\n".join(["free before", _block_text(PYTHON), "free after"]) + "\n"
    )
    assert result == expected
    assert "THIS_IS_A_STALE_BODY_LINE" not in result


def test_replace_in_place_with_multiple_blocks_each_stays_at_own_position():
    existing = (
        "\n".join(
            [
                "# >>> stow:base >>>",
                ADVISORY_LINE,
                "STALE_BASE",
                "# <<< stow:base <<<",
                "",
                "# >>> stow:python >>>",
                ADVISORY_LINE,
                "STALE_PYTHON",
                "# <<< stow:python <<<",
            ]
        )
        + "\n"
    )
    result = apply_blocks(existing, [BASE, PYTHON])
    expected = "\n".join([_block_text(BASE), "", _block_text(PYTHON)]) + "\n"
    assert result == expected


# ---------------------------------------------------------------------------
# free lines preserved verbatim
# ---------------------------------------------------------------------------


def test_free_lines_preserved_verbatim_before_between_after():
    existing = (
        "\n".join(
            [
                ".superpowers/",
                "# >>> stow:base >>>",
                ADVISORY_LINE,
                ".DS_Store",
                "Thumbs.db",
                "# <<< stow:base <<<",
                "# a plain comment",
                "# >>> stow:python >>>",
                ADVISORY_LINE,
                "__pycache__/",
                "# <<< stow:python <<<",
                "trailing free line",
            ]
        )
        + "\n"
    )
    result = apply_blocks(existing, [BASE, PYTHON])
    lines = result.split("\n")

    assert ".superpowers/" in lines
    assert "# a plain comment" in lines
    assert "trailing free line" in lines

    idx_free1 = lines.index(".superpowers/")
    idx_base_open = lines.index("# >>> stow:base >>>")
    idx_comment = lines.index("# a plain comment")
    idx_python_open = lines.index("# >>> stow:python >>>")
    idx_trailing = lines.index("trailing free line")
    assert idx_free1 < idx_base_open < idx_comment < idx_python_open < idx_trailing


# ---------------------------------------------------------------------------
# blank lines outside any managed region are never touched
#
# apply_blocks' #1 guarantee is that lines outside any stow region are
# emitted byte-for-byte: never reordered, deduped, dropped, or rewritten.
# A blank-line run that sits entirely among free lines -- not adjacent to
# any region this call adds, replaces, or removes -- is exactly such a
# line, and must survive untouched, no matter how many consecutive blanks
# it is.
# ---------------------------------------------------------------------------


def test_blank_runs_outside_regions_are_preserved_verbatim():
    assert apply_blocks("a\n\n\n\nb\n", []) == "a\n\n\n\nb\n"


def test_noop_apply_is_byte_for_byte_identical_to_input():
    """A file already in canonical form -- including whatever internal
    blank-line formatting the user chose among the free lines -- must come
    back unchanged. This is the general form of the leading/trailing-blank
    no-op test above: multiple blank runs, in multiple positions, all at
    once."""
    canonical = (
        "\n".join(
            [
                "free1",
                "",
                "",
                _block_text(BASE),
                "",
                "free2",
                "",
                "",
                "",
                _block_text(PYTHON),
                "free3",
            ]
        )
        + "\n"
    )
    assert apply_blocks(canonical, [BASE, PYTHON]) == canonical


def test_idempotent_preserves_internal_blank_runs_among_free_lines():
    existing = "a\n\n\n\nb\n" + _block_text(PYTHON) + "\n"
    once = apply_blocks(existing, [PYTHON])
    twice = apply_blocks(once, [PYTHON])
    assert twice == once
    assert "a\n\n\n\nb\n" in once


# ---------------------------------------------------------------------------
# idempotency
# ---------------------------------------------------------------------------


STALE_MULTI_BLOCK_TEXT = (
    "\n".join(
        [
            "free1",
            "",
            "# >>> stow:node >>>",
            ADVISORY_LINE,
            "STALE_NODE",
            "# <<< stow:node <<<",
            "",
            "# >>> stow:python >>>",
            ADVISORY_LINE,
            "STALE_PYTHON",
            "# <<< stow:python <<<",
            "free2",
        ]
    )
    + "\n"
)

TEXT_WITH_UNKNOWN_BLOCK = (
    "\n".join(
        [
            "# >>> stow:rust >>>",
            "# rust-specific, not ours",
            "target/",
            "# <<< stow:rust <<<",
        ]
    )
    + "\n"
)


@pytest.mark.parametrize(
    "existing,desired",
    [
        ("", [BASE, PYTHON]),
        ("", [BASE, PYTHON, NODE]),
        ("free only, no blocks at all\n", [PYTHON]),
        (STALE_MULTI_BLOCK_TEXT, [BASE, PYTHON]),
        (STALE_MULTI_BLOCK_TEXT, [BASE, PYTHON, NODE]),
        (TEXT_WITH_UNKNOWN_BLOCK, [PYTHON]),
    ],
)
def test_idempotent_for_various_inputs(existing, desired):
    once = apply_blocks(existing, desired)
    twice = apply_blocks(once, desired)
    assert twice == once


def test_idempotent_after_removal():
    desired = [PYTHON]
    once = apply_blocks(STALE_MULTI_BLOCK_TEXT, desired)  # drops node
    twice = apply_blocks(once, desired)
    assert once == twice
    assert "stow:node" not in once


# ---------------------------------------------------------------------------
# declarative removal
# ---------------------------------------------------------------------------


def test_declarative_removal_drops_undesired_known_block():
    result = apply_blocks(STALE_MULTI_BLOCK_TEXT, [PYTHON])
    assert "stow:node" not in result
    assert "STALE_NODE" not in result
    assert "stow:python" in result
    assert "STALE_PYTHON" not in result  # replaced with canonical body


def test_removal_collapses_surrounding_blank_lines_exactly():
    result = apply_blocks(STALE_MULTI_BLOCK_TEXT, [PYTHON])
    expected = "\n".join(["free1", "", _block_text(PYTHON), "free2"]) + "\n"
    assert result == expected


def test_removal_of_all_desired_sections_leaves_only_free_lines():
    # free1 and free2 were never adjacent in the source (a blank line or a
    # block always separated them) -- removal collapses that gap to a
    # single blank line rather than eliminating it, consistent with
    # test_removal_collapses_surrounding_blank_lines_exactly above.
    result = apply_blocks(STALE_MULTI_BLOCK_TEXT, [])
    assert result == "\n".join(["free1", "", "free2"]) + "\n"


# ---------------------------------------------------------------------------
# boundary removal: a removed block at the very start or end of the file
# leaves no orphaned separator blank line behind.
#
# The interior-sandwich collapse above (decision #2) only fires when a
# removed region has a blank-adjacent neighbor on *both* sides -- it
# collapses that pair down to one. At a file edge there's only one side,
# so without dedicated handling the lone separator blank that used to
# stand between the removed region and its single neighbor is never
# dropped, and survives as an orphan.
# ---------------------------------------------------------------------------


def test_start_of_file_removal_drops_leading_orphan_blank():
    # node is the very first thing in the file; removing it must not leave
    # a leading blank line where it used to be.
    existing = _block_text(NODE) + "\n\n" + _block_text(BASE) + "\n"
    result = apply_blocks(existing, [BASE])
    assert result == _block_text(BASE) + "\n"


def test_end_of_file_removal_drops_trailing_orphan_blank():
    # node is the very last thing in the file; removing it must not leave
    # a trailing blank line behind.
    existing = "free1\n\n" + _block_text(NODE) + "\n"
    result = apply_blocks(existing, [])
    assert result == "free1\n"


def test_both_start_and_end_boundary_removal_in_one_call():
    # node at the head and base at the tail are both declaratively
    # removed in the same call; only the interior free line should
    # survive, with no orphaned blank at either edge.
    existing = _block_text(NODE) + "\n\nfree1\n\n" + _block_text(BASE) + "\n"
    result = apply_blocks(existing, [])
    assert result == "free1\n"


# ---------------------------------------------------------------------------
# boundary removal only collapses the ONE separator blank -- pins the
# actual contract (see apply_blocks' docstring): when two or more blank
# lines separated the removed boundary block from its neighbor, only the
# single separator blank is collapsed. Any additional blank lines are user
# content and are preserved, so the file can still start or end with a
# user-authored blank line after a boundary removal.
# ---------------------------------------------------------------------------


def test_start_of_file_removal_with_two_blanks_leaves_exactly_one():
    # node is at the head, separated from base by TWO blank lines. Only
    # one of those is the separator; the other is user content and must
    # survive -- the result is neither zero blanks (over-collapse) nor two
    # (no collapse at all).
    existing = _block_text(NODE) + "\n\n\n" + _block_text(BASE) + "\n"
    result = apply_blocks(existing, [BASE])
    expected = "\n" + _block_text(BASE) + "\n"
    assert result == expected
    assert apply_blocks(result, [BASE]) == result  # idempotent


def test_end_of_file_removal_with_two_blanks_leaves_exactly_one():
    # node is at the end, separated from free1 by TWO blank lines. Only
    # one collapses; the other is preserved as trailing user content.
    existing = "free1\n\n\n" + _block_text(NODE) + "\n"
    result = apply_blocks(existing, [])
    expected = "free1\n\n"
    assert result == expected
    assert apply_blocks(result, []) == result  # idempotent


# ---------------------------------------------------------------------------
# unknown-id regions
# ---------------------------------------------------------------------------


def test_unknown_id_region_left_untouched_when_not_desired():
    result = apply_blocks(TEXT_WITH_UNKNOWN_BLOCK, [])
    assert result == TEXT_WITH_UNKNOWN_BLOCK


def test_unknown_id_region_untouched_while_other_blocks_change():
    existing = (
        "\n".join(
            [
                "# >>> stow:rust >>>",
                "# rust stuff",
                "target/",
                "# <<< stow:rust <<<",
                "",
                "# >>> stow:node >>>",
                ADVISORY_LINE,
                "node_modules/",
                "# <<< stow:node <<<",
            ]
        )
        + "\n"
    )
    result = apply_blocks(existing, [PYTHON])
    assert "# >>> stow:rust >>>" in result
    assert "target/" in result
    assert "stow:node" not in result
    assert "stow:python" in result


# ---------------------------------------------------------------------------
# malformed input
# ---------------------------------------------------------------------------


def test_opener_without_closer_raises_stow_error_naming_line():
    existing = "\n".join(["free", "# >>> stow:python >>>", "body without closer"]) + "\n"
    with pytest.raises(StowError) as exc:
        apply_blocks(existing, [PYTHON])
    assert "line 2" in str(exc.value)


def test_opener_without_closer_at_eof_raises():
    existing = "# >>> stow:python >>>\n"
    with pytest.raises(StowError) as exc:
        apply_blocks(existing, [PYTHON])
    assert "line 1" in str(exc.value)


def test_closer_without_opener_raises_stow_error_naming_line():
    existing = "\n".join(["free", "# <<< stow:python <<<"]) + "\n"
    with pytest.raises(StowError) as exc:
        apply_blocks(existing, [PYTHON])
    assert "line 2" in str(exc.value)


def test_duplicate_openers_for_one_id_raises_stow_error():
    existing = (
        "\n".join(
            [
                "# >>> stow:python >>>",
                ADVISORY_LINE,
                "a",
                "# <<< stow:python <<<",
                "",
                "# >>> stow:python >>>",
                ADVISORY_LINE,
                "b",
                "# <<< stow:python <<<",
            ]
        )
        + "\n"
    )
    with pytest.raises(StowError) as exc:
        apply_blocks(existing, [PYTHON])
    assert "python" in str(exc.value)


def test_mismatched_open_close_ids_raises_stow_error():
    existing = (
        "\n".join(["# >>> stow:python >>>", ADVISORY_LINE, "body", "# <<< stow:node <<<"])
        + "\n"
    )
    with pytest.raises(StowError):
        apply_blocks(existing, [PYTHON])


def test_malformed_raises_even_if_offending_id_is_not_in_desired():
    """A malformed region should abort the whole splice, not just be
    ignored because it isn't otherwise relevant to this call."""
    existing = "\n".join(["# >>> stow:rust >>>", "unterminated"]) + "\n"
    with pytest.raises(StowError):
        apply_blocks(existing, [PYTHON])


# ---------------------------------------------------------------------------
# find_blocks (direct unit coverage)
# ---------------------------------------------------------------------------


def test_find_blocks_returns_a_tuple_of_two():
    result = find_blocks("")
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_find_blocks_well_formed_simple():
    text = "\n".join(["free", "# >>> stow:python >>>", "body", "# <<< stow:python <<<", "tail"])
    well_formed, malformed = find_blocks(text)
    assert well_formed == [("python", 1, 3)]
    assert not malformed


def test_find_blocks_multiple_well_formed_in_document_order():
    text = "\n".join(
        [
            "# >>> stow:base >>>",
            "b",
            "# <<< stow:base <<<",
            "# >>> stow:python >>>",
            "p",
            "# <<< stow:python <<<",
        ]
    )
    well_formed, malformed = find_blocks(text)
    assert well_formed == [("base", 0, 2), ("python", 3, 5)]
    assert not malformed


def test_find_blocks_opener_without_closer_flagged():
    text = "\n".join(["# >>> stow:python >>>", "body"])
    well_formed, malformed = find_blocks(text)
    assert well_formed == []
    assert malformed
    assert any("line 1" in m for m in malformed)


def test_find_blocks_closer_without_opener_flagged():
    text = "\n".join(["free", "# <<< stow:python <<<"])
    well_formed, malformed = find_blocks(text)
    assert malformed
    assert any("line 2" in m for m in malformed)


def test_find_blocks_duplicate_ids_flagged():
    text = "\n".join(
        [
            "# >>> stow:python >>>",
            "b1",
            "# <<< stow:python <<<",
            "# >>> stow:python >>>",
            "b2",
            "# <<< stow:python <<<",
        ]
    )
    well_formed, malformed = find_blocks(text)
    assert len(well_formed) == 2
    assert malformed


def test_find_blocks_no_markers_is_clean():
    well_formed, malformed = find_blocks("just\nsome\nfree\ntext\n")
    assert well_formed == []
    assert malformed == []


# ---------------------------------------------------------------------------
# marker regexes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "line",
    [
        "# >>> stow:python >>>",
        "# >>> stow:my-stack2 >>>",
        "# >>> stow:a >>>",
    ],
)
def test_opener_re_matches_valid_lines(line):
    assert OPENER_RE.match(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "  # >>> stow:python >>>",
        "# >>> stow:python >>> ",
        "# >>> stow:Python >>>",
        "# >>> stow:python <<<",
        "prefix # >>> stow:python >>>",
        "# >>> stow: >>>",
        "# >>> stow:py_thon >>>",
    ],
)
def test_opener_re_rejects_invalid_lines(line):
    assert OPENER_RE.match(line) is None


@pytest.mark.parametrize(
    "line",
    [
        "# <<< stow:python <<<",
        "# <<< stow:my-stack2 <<<",
    ],
)
def test_closer_re_matches_valid_lines(line):
    assert CLOSER_RE.match(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "  # <<< stow:python <<<",
        "# <<< stow:python <<< ",
        "# <<< stow:python >>>",
        "# <<< stow: <<<",
    ],
)
def test_closer_re_rejects_invalid_lines(line):
    assert CLOSER_RE.match(line) is None


@pytest.mark.parametrize(
    "line",
    [
        "# >>> stow:python >>>",
        "# <<< stow:python <<<",
    ],
)
def test_marker_re_matches_any_marker_line(line):
    assert MARKER_RE.match(line) is not None


@pytest.mark.parametrize(
    "line",
    [
        "# a plain comment",
        ".superpowers/",
        "",
        "stow:python",
    ],
)
def test_marker_re_rejects_non_marker_lines(line):
    assert MARKER_RE.match(line) is None


# ---------------------------------------------------------------------------
# marker regexes are newline-safe (exported for reuse by external callers,
# who may naively .match() a raw line that still carries its trailing "\n"
# -- e.g. read straight from a file via iteration rather than pre-split).
# Un-anchored `$` matches just before a trailing "\n", not just at the
# absolute end of the string, so a naive external caller could get a false
# match. `\Z` closes that gap.
# ---------------------------------------------------------------------------


def test_opener_re_does_not_match_line_with_trailing_newline():
    assert OPENER_RE.match("# >>> stow:rust >>>\n") is None


def test_closer_re_does_not_match_line_with_trailing_newline():
    assert CLOSER_RE.match("# <<< stow:rust <<<\n") is None


def test_marker_re_does_not_match_line_with_trailing_newline():
    assert MARKER_RE.match("# >>> stow:rust >>>\n") is None


# ---------------------------------------------------------------------------
# multi-stack composition: order, separators, trailing newline
# ---------------------------------------------------------------------------


def test_composition_order_base_then_registry_order():
    desired = [BASE, PYTHON, NODE]
    result = apply_blocks("", desired)
    positions = [result.index(f"# >>> stow:{s.id} >>>") for s in desired]
    assert positions == sorted(positions)


def test_composition_uses_exact_single_blank_line_separators():
    desired = [BASE, PYTHON, NODE]
    result = apply_blocks("", desired)
    expected = "\n\n".join(_block_text(s) for s in desired) + "\n"
    assert result == expected


def test_composition_has_no_triple_newlines_anywhere():
    result = apply_blocks("", [BASE, PYTHON, NODE])
    assert "\n\n\n" not in result


def test_single_trailing_newline():
    result = apply_blocks("", [BASE, PYTHON])
    assert result.endswith("\n")
    assert not result.endswith("\n\n")


def test_leading_and_trailing_blank_lines_in_existing_text_are_preserved():
    """Leading/trailing blank lines among free lines sit outside any
    managed region -- stow has no business touching them. This was
    previously named '..._are_collapsed' and asserted the opposite
    (stripped leading/trailing blanks); that encoded a bug: a global
    blank-run collapse pass ran unconditionally over the whole assembled
    output, not just at the seams a splice actually creates. Since the
    python block here is already canonical, this call is a pure no-op and
    must return the input byte-for-byte."""
    existing = "\n\n" + _block_text(PYTHON) + "\n\n\n"
    result = apply_blocks(existing, [PYTHON])
    assert result == existing


# ---------------------------------------------------------------------------
# \r\n normalization
# ---------------------------------------------------------------------------


def test_crlf_input_is_normalized_to_lf():
    existing = (
        "free\r\n"
        + "# >>> stow:python >>>\r\n"
        + ADVISORY_LINE
        + "\r\nSTALE\r\n# <<< stow:python <<<\r\n"
    )
    result = apply_blocks(existing, [PYTHON])
    assert "\r" not in result
    assert result == "\n".join(["free", _block_text(PYTHON)]) + "\n"


def test_bare_cr_input_is_also_normalized():
    existing = "free\r# >>> stow:python >>>\r" + ADVISORY_LINE + "\rSTALE\r# <<< stow:python <<<\r"
    result = apply_blocks(existing, [PYTHON])
    assert "\r" not in result


# ---------------------------------------------------------------------------
# StowError basics
# ---------------------------------------------------------------------------


def test_stow_error_is_an_exception():
    assert issubclass(StowError, Exception)
