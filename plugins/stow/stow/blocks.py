"""The managed-block splice engine.

Parses and rewrites stow:<id> managed blocks inside text (typically
.gitignore), leaving everything else -- free-form lines the user wrote
themselves, and any block stow doesn't recognize -- exactly where it found
it. `apply_blocks` is a pure string -> string transform: given the current
file text and the ordered list of stacks that should be present, it returns
the new file text.

Pure module. Stdlib `re` and string operations only; no subprocess, no os,
no networking.
"""
from __future__ import annotations

import re

from stow.stacks import BASE, STACK_IDS, StackSpec

#: The single fixed advisory line every managed block carries, right after
#: the opener. Deliberately identical across stacks -- it's the *block* that's
#: managed, not the advisory text, so there's nothing stack-specific to say.
ADVISORY = (
    "# managed by stow — edits inside this block are overwritten; "
    "put custom entries outside it"
)

_ID_PATTERN = r"[a-z0-9-]+"

#: Full-line, anchored: matches only a line that is *exactly* a stow opener.
OPENER_RE = re.compile(rf"^# >>> stow:(?P<id>{_ID_PATTERN}) >>>$")

#: Full-line, anchored: matches only a line that is *exactly* a stow closer.
CLOSER_RE = re.compile(rf"^# <<< stow:(?P<id>{_ID_PATTERN}) <<<$")

#: Matches any stow marker line (opener or closer), regardless of id. Used
#: to test "is this line a stow marker at all" -- e.g. so a gitignore body
#: line can be checked for accidentally colliding with the marker syntax.
MARKER_RE = re.compile(rf"^# (?:>>>|<<<) stow:{_ID_PATTERN} (?:>>>|<<<)$")


class StowError(Exception):
    """Raised when existing stow markers in a file can't be parsed safely
    (an unterminated block, a stray closer, or a duplicate block id)."""


def _opener_line(stack_id: str) -> str:
    return f"# >>> stow:{stack_id} >>>"


def _closer_line(stack_id: str) -> str:
    return f"# <<< stow:{stack_id} <<<"


def render_block(spec: StackSpec) -> str:
    """Render the canonical, deterministic text of one managed block for
    `spec`: opener, the fixed advisory line, the body lines, closer. No
    blank lines inside, and no trailing newline at the end -- callers
    (apply_blocks) control how blocks are joined with the rest of the
    file.
    """
    lines = [_opener_line(spec.id), ADVISORY, *spec.gitignore, _closer_line(spec.id)]
    return "\n".join(lines)


def find_blocks(text: str) -> tuple:
    """Scan `text` for stow managed-block markers.

    `text` is assumed to already use `\\n` line endings (apply_blocks
    normalizes before calling this; called directly, e.g. by a dogfood
    check, callers should normalize first too).

    Returns `(well_formed, malformed)`:
      - `well_formed`: list of `(id, start_line_idx, end_line_idx)`, 0-based
        line indices, inclusive of both the opener and the closer line, in
        document order.
      - `malformed`: list of human-readable problem descriptions, each
        naming a 1-based line number. Empty exactly when the file's stow
        markers all parse cleanly (no unterminated opener, no orphan
        closer, no mismatched pair, no duplicate block id).
    """
    lines = text.split("\n")
    well_formed: list = []
    malformed: list = []
    open_id = None
    open_idx = None

    for idx, line in enumerate(lines):
        opener = OPENER_RE.match(line)
        closer = CLOSER_RE.match(line)
        if opener:
            if open_id is not None:
                malformed.append(
                    f"line {open_idx + 1}: '{_opener_line(open_id)}' has no "
                    "matching closer"
                )
            open_id = opener.group("id")
            open_idx = idx
        elif closer:
            closer_id = closer.group("id")
            if open_id is None:
                malformed.append(
                    f"line {idx + 1}: '{_closer_line(closer_id)}' has no "
                    "matching opener"
                )
            elif closer_id != open_id:
                malformed.append(
                    f"line {open_idx + 1}: '{_opener_line(open_id)}' has no "
                    "matching closer"
                )
                malformed.append(
                    f"line {idx + 1}: '{_closer_line(closer_id)}' has no "
                    "matching opener"
                )
                open_id = None
                open_idx = None
            else:
                well_formed.append((open_id, open_idx, idx))
                open_id = None
                open_idx = None

    if open_id is not None:
        malformed.append(
            f"line {open_idx + 1}: '{_opener_line(open_id)}' has no matching closer"
        )

    seen_ids = set()
    for block_id, start, _end in well_formed:
        if block_id in seen_ids:
            malformed.append(
                f"line {start + 1}: duplicate 'stow:{block_id}' block "
                "(id already used earlier in this file)"
            )
        else:
            seen_ids.add(block_id)

    return well_formed, malformed


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _collapse_blank_runs(lines: list) -> list:
    """Strip leading/trailing blank lines and collapse any internal run of
    2+ consecutive blank lines down to exactly one.

    Applied once, at the end, over the whole assembled output -- not just
    to blank lines stow's own splicing introduced. A managed-blocks file
    (.gitignore) has no reason to carry meaningful multi-blank-line runs or
    leading/trailing blank lines, and normalizing them unconditionally is
    what keeps apply_blocks idempotent without having to track provenance
    of every blank line.
    """
    start = 0
    end = len(lines)
    while start < end and lines[start] == "":
        start += 1
    while end > start and lines[end - 1] == "":
        end -= 1

    collapsed: list = []
    prev_blank = False
    for line in lines[start:end]:
        is_blank = line == ""
        if is_blank and prev_blank:
            continue
        collapsed.append(line)
        prev_blank = is_blank
    return collapsed


def apply_blocks(existing_text: str, desired_sections: list) -> str:
    """Splice `desired_sections` (an ordered list of `StackSpec`, base
    first then registry order) into `existing_text`.

    - A desired section with an existing well-formed region is replaced in
      place (same position, current canonical body).
    - A known registry id (or "base") that is NOT desired is dropped
      entirely.
    - A region whose id stow doesn't recognize is left untouched
      (forward-compat with markers a newer stow -- or a hand-edit -- put
      there).
    - Lines outside any region are emitted verbatim, in original order.
    - A desired section with no existing region is appended at the end, in
      canonical order, each separated from what precedes it by exactly one
      blank line.

    Raises `StowError` if any existing stow marker doesn't parse cleanly
    (unterminated opener, orphan closer, mismatched pair, or duplicate
    block id) -- naming the offending 1-based line number(s).

    `apply_blocks("", desired)` is how a file is created from scratch, and
    `apply_blocks(apply_blocks(x, d), d) == apply_blocks(x, d)` for any x
    and d: applying twice is the same as applying once.
    """
    normalized = _normalize_newlines(existing_text)
    well_formed, malformed = find_blocks(normalized)
    if malformed:
        raise StowError("; ".join(malformed))

    lines = normalized.split("\n")
    desired_by_id = {spec.id: spec for spec in desired_sections}
    known_ids = frozenset(STACK_IDS) | {BASE.id}

    out: list = []
    pos = 0
    for block_id, start, end in well_formed:
        out.extend(lines[pos:start])
        if block_id in desired_by_id:
            out.extend(render_block(desired_by_id[block_id]).split("\n"))
        elif block_id in known_ids:
            pass  # known but not desired: declaratively removed
        else:
            out.extend(lines[start : end + 1])  # unknown id: forward-compat, untouched
        pos = end + 1
    out.extend(lines[pos:])

    present_ids = {block_id for block_id, _start, _end in well_formed}
    for spec in desired_sections:
        if spec.id not in present_ids:
            out.append("")
            out.extend(render_block(spec).split("\n"))

    out = _collapse_blank_runs(out)

    if not out:
        return ""
    return "\n".join(out) + "\n"
