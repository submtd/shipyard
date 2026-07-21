"""stow's one I/O module: the write that touches the user's .gitignore.

Everything else in stow is pure -- blocks.py is fuzz-clean and idempotent --
so the only way stow can destroy user data is here. These tests pin the two
properties that keep it from doing so:

1. UTF-8 always. ADVISORY (blocks.py) contains an em dash, and
   Path.write_text() with no encoding= truncates the file *before* it
   encodes. On an ASCII-preferred locale that leaves a 0-byte .gitignore
   and the user's hand-written ignore rules are gone.
2. Atomic. A crash, SIGINT, or full disk between truncate and write has
   the same effect, so the real file is only ever swapped in whole.

The locale test runs in a subprocess because the preferred encoding is
fixed at interpreter start. LC_ALL=C alone is not enough: PEP 538/540
coerce it back to UTF-8, so both escape hatches must be disabled too.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from stow.blocks import ADVISORY
from stow.fileio import read_managed_file, write_managed_file

PLUGIN_ROOT = Path(__file__).resolve().parents[1]

ASCII_LOCALE_ENV = {
    "LC_ALL": "C",
    "PYTHONCOERCECLOCALE": "0",
    "PYTHONUTF8": "0",
    "PATH": "/usr/bin:/bin",
}

#: Imported, not retyped: this is the exact string that makes the write
#: non-ASCII in production. If ADVISORY ever loses its em dash these tests
#: must stop claiming to guard the locale path, and importing it is what
#: makes that visible.
NON_ASCII = ADVISORY + "\n"


def test_survives_an_ascii_preferred_locale(tmp_path):
    # The regression this module exists for. Under an ASCII locale the old
    # bare Path.write_text() raised UnicodeEncodeError *after* truncating,
    # leaving 0 bytes. The user's lines must still be there afterwards.
    target = tmp_path / ".gitignore"
    target.write_text("MY_CUSTOM_LINE\nsecret.key\n", encoding="utf-8")

    script = (
        "import sys; sys.path.insert(0, {root!r});"
        "from stow.fileio import write_managed_file;"
        "write_managed_file({target!r}, {text!r})"
    ).format(
        root=str(PLUGIN_ROOT),
        target=str(target),
        text="MY_CUSTOM_LINE\nsecret.key\n" + NON_ASCII,
    )
    proc = subprocess.run(
        [sys.executable, "-c", script],
        env=ASCII_LOCALE_ENV,
        capture_output=True,
        text=True,
        timeout=30,
    )

    assert proc.returncode == 0, proc.stderr
    assert target.read_text(encoding="utf-8") == (
        "MY_CUSTOM_LINE\nsecret.key\n" + NON_ASCII
    )


def test_writes_utf8_bytes_not_locale_default(tmp_path):
    target = tmp_path / ".gitignore"
    write_managed_file(target, NON_ASCII)
    assert target.read_bytes() == NON_ASCII.encode("utf-8")


def test_reads_utf8_regardless_of_locale(tmp_path):
    target = tmp_path / ".gitignore"
    target.write_bytes(NON_ASCII.encode("utf-8"))
    assert read_managed_file(target) == NON_ASCII


def test_reading_an_absent_file_is_empty_not_an_error(tmp_path):
    # The skill's create-or-update path relies on this: no .gitignore yet
    # means "start from an empty document", not a crash.
    assert read_managed_file(tmp_path / ".gitignore") == ""


def test_a_failed_write_leaves_the_original_intact(tmp_path, monkeypatch):
    # Atomicity: if the swap fails, the user still has their file. Without
    # tmp+replace the original is already truncated by this point.
    target = tmp_path / ".gitignore"
    target.write_text("MY_CUSTOM_LINE\n", encoding="utf-8")

    import stow.fileio as fileio

    def boom(src, dst):
        raise OSError("disk full")

    monkeypatch.setattr(fileio.os, "replace", boom)

    with pytest.raises(OSError):
        write_managed_file(target, "replacement\n")

    assert target.read_text(encoding="utf-8") == "MY_CUSTOM_LINE\n"


def test_no_temp_file_is_left_behind_on_success(tmp_path):
    target = tmp_path / ".gitignore"
    write_managed_file(target, "a\n")
    assert [p.name for p in tmp_path.iterdir()] == [".gitignore"]


def test_writes_through_a_symlink_rather_than_replacing_it(tmp_path):
    # A .gitignore symlinked into a dotfiles repo must stay a symlink --
    # os.replace on the link path would silently break that setup.
    real = tmp_path / "real-gitignore"
    real.write_text("original\n", encoding="utf-8")
    link = tmp_path / ".gitignore"
    link.symlink_to(real)

    write_managed_file(link, "updated\n")

    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == "updated\n"
