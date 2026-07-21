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
#: Anchored with `\Z`, not `$` -- `$` matches just before a trailing "\n",
#: not only at the absolute end of the string, so `OPENER_RE.match(s)`
#: would otherwise still succeed for a newline-suffixed `s` (e.g. a raw
#: line read from a file without stripping it first). These regexes are
#: exported for reuse by external callers, so that footgun matters.
OPENER_RE = re.compile(rf"^# >>> stow:(?P<id>{_ID_PATTERN}) >>>\Z")

#: Full-line, anchored: matches only a line that is *exactly* a stow closer.
CLOSER_RE = re.compile(rf"^# <<< stow:(?P<id>{_ID_PATTERN}) <<<\Z")

#: Matches any stow marker line (opener or closer), regardless of id. Used
#: to test "is this line a stow marker at all" -- e.g. so a gitignore body
#: line can be checked for accidentally colliding with the marker syntax.
MARKER_RE = re.compile(rf"^# (?:>>>|<<<) stow:{_ID_PATTERN} (?:>>>|<<<)\Z")


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
    - Lines outside any region -- including blank lines, blank runs, and
      any leading/trailing blank lines -- are emitted verbatim, in
      original order and position. Blank-line normalization happens ONLY
      at the two seams this call can itself introduce: see the next two
      bullets. Everywhere else, nothing about blank-line formatting is
      touched; a no-op call (existing text already matches the desired
      sections) returns the input byte-for-byte.
    - When a known region is dropped (declaratively removed), if that
      leaves a blank line immediately before the removed region directly
      adjacent to a blank line immediately after it, that newly-adjacent
      pair collapses to a single blank line. This is local to the removed
      region's position -- blank runs anywhere else in the file are left
      alone. At a file boundary there's only one side to collapse: a
      removed region with nothing preceding it (nothing before it, or
      only other removed regions at the top) drops a single leading
      blank from the gap that follows it; a removed region with nothing
      following it to end of file (nothing after it, or only blank
      lines) drops a single trailing blank from the gap that precedes
      it. Either way, removing a block never leaves a stray orphan blank
      at the start or end of the file.
    - A desired section with no existing region is appended at the end, in
      canonical order, each separated from what precedes it by at least
      one blank line -- never doubled. If the free content immediately
      preceding the append point already ends in its own multi-blank
      tail, that tail is preserved as-is (untouched, per the
      preserved-verbatim guarantee above) rather than collapsed to
      exactly one.

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

    # Split into logical lines with no phantom trailing element. A
    # trailing "\n" in normalized text (the common case) makes
    # str.split("\n") produce a final "" that isn't a real line -- it's
    # just how the split represents "the text ended right after a
    # newline". Popping it here (rather than stripping trailing blanks
    # later) is what lets a *genuine* trailing blank line survive while
    # the single-trailing-newline guarantee is still enforced by the
    # unconditional "+ \n" below.
    if normalized:
        lines = normalized.split("\n")
        if normalized.endswith("\n"):
            lines.pop()
    else:
        lines = []

    desired_by_id = {spec.id: spec for spec in desired_sections}
    known_ids = frozenset(STACK_IDS) | {BASE.id}

    out: list = []
    pos = 0
    # Set when a just-processed removal sat at the head of the file (no
    # emitted output yet, no gap before it) and was itself followed by a
    # blank line: the orphan blank lives in the *next* gap, not this
    # region's own (empty) gap, so dropping it has to be deferred one
    # iteration.
    drop_next_leading_blank = False
    total = len(well_formed)
    for idx, (block_id, start, end) in enumerate(well_formed):
        gap = lines[pos:start]
        if drop_next_leading_blank and gap and gap[0] == "":
            gap = gap[1:]
        drop_next_leading_blank = False

        if block_id in desired_by_id:
            out.extend(gap)
            out.extend(render_block(desired_by_id[block_id]).split("\n"))
        elif block_id in known_ids:
            # known but not desired: declaratively removed. If that
            # leaves a blank line immediately before the removed region
            # directly touching a blank line immediately after it,
            # collapse that newly-adjacent pair to one blank -- local to
            # this removal, nothing else in `gap` is touched (the
            # interior case).
            #
            # Boundary cases: nothing precedes this region at all (empty
            # `gap`, nothing emitted into `out` yet) -- defer dropping
            # its blank-after to the next gap, since that's where the
            # orphan blank actually lives. Nothing follows this region to
            # EOF (it's the last well-formed block and everything after
            # it, if anything, is blank) -- drop a trailing blank
            # straight out of this region's own `gap`.
            at_head = not out and not gap
            after_is_blank = end + 1 < len(lines) and lines[end + 1] == ""
            no_following_content = idx == total - 1 and all(
                line == "" for line in lines[end + 1 :]
            )

            if gap and gap[-1] == "" and after_is_blank:
                gap = gap[:-1]
            if no_following_content and gap and gap[-1] == "":
                gap = gap[:-1]
            if at_head and after_is_blank:
                drop_next_leading_blank = True

            out.extend(gap)
        else:
            out.extend(gap)
            out.extend(lines[start : end + 1])  # unknown id: forward-compat, untouched
        pos = end + 1

    tail = lines[pos:]
    if drop_next_leading_blank and tail and tail[0] == "":
        tail = tail[1:]
    out.extend(tail)

    present_ids = {block_id for block_id, _start, _end in well_formed}
    for spec in desired_sections:
        if spec.id not in present_ids:
            if out and out[-1] != "":
                out.append("")
            out.extend(render_block(spec).split("\n"))

    if not out:
        return ""
    return "\n".join(out) + "\n"
