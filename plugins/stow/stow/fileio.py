"""stow's only I/O module -- the engine stays pure, this owns the disk.

Splitting this out of the skill's inline one-liner is deliberate. stow's
whole promise is that it edits a file the user already owns without losing
what they wrote, and a bare `Path.write_text(...)` breaks that promise two
ways: it encodes with the locale's preferred codec (ADVISORY contains an em
dash, so an ASCII locale raises) and it truncates the target *before*
encoding, so the raise lands on an already-empty file. Non-atomic writes
have the same failure shape for a SIGINT or a full disk.

Both are fixed here, once, where a test can reach them -- see
tests/test_fileio.py.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Suffix for the staging file written next to the target. Named rather
#: than inlined so the "no temp file left behind" test names the same thing
#: the code does.
TMP_SUFFIX = ".stow-tmp"


def read_managed_file(path):
    """Return the file's contents as UTF-8 text, or "" if it doesn't exist.

    Absent is not an error: the create-or-update path treats a repo with no
    .gitignore as an empty document. A file that exists but isn't valid
    UTF-8 still raises -- that's a repo we must not guess about.
    """
    path = Path(path)
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def write_managed_file(path, text):
    """Write `text` to `path` as UTF-8, atomically.

    Stages into a sibling temp file and swaps with os.replace, so the target
    is only ever the old contents or the new ones -- never a truncated
    prefix. A symlinked target is resolved first so the swap replaces what
    the link points at rather than the link itself (a .gitignore symlinked
    into a dotfiles repo must survive as a symlink).
    """
    path = Path(path)
    if path.is_symlink():
        path = path.resolve()

    tmp = path.with_name(path.name + TMP_SUFFIX)
    tmp.write_text(text, encoding="utf-8")
    try:
        os.replace(tmp, path)
    except OSError:
        # Leave the target untouched and don't strand the staging file.
        tmp.unlink(missing_ok=True)
        raise
