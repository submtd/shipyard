"""Ecosystem detection from repo-root marker files.

Pure module. Stdlib only; no subprocess, no os, no networking -- pathlib
existence checks only. A later task enforces this invariant over the whole
engine via an AST test.
"""
from __future__ import annotations

from pathlib import Path

from bosun import ecosystems


def detect_ecosystems(root) -> tuple[str, ...]:
    """Return the ids (registry order) of always-off ecosystems whose
    markers exist at root. Always-on ecosystems (github-actions) are never
    surfaced here -- that policy lives in scaffold/detect callers, not
    detection itself."""
    root = Path(root)
    detected = []
    for ecosystem_id, spec in ecosystems.REGISTRY.items():
        if spec.always_on:
            continue
        # is_file, not exists: a *directory* with a marker's name holds no
        # configuration, and detecting off one scaffolds the wrong stack.
        if any((root / filename).is_file() for filename in spec.detect_files):
            detected.append(ecosystem_id)
    return tuple(detected)
