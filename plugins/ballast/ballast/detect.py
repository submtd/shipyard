"""Stack detection from repo-root marker files.

Pure module. Stdlib only; no subprocess, no os, no networking -- pathlib
existence checks only. A later task enforces this invariant over the whole
engine via an AST test.
"""
from __future__ import annotations

from pathlib import Path

from ballast import stacks


def detect_stacks(root) -> tuple[str, ...]:
    """Return the ids of stacks (registry order) whose markers exist at root."""
    root = Path(root)
    detected = []
    for stack_id, spec in stacks.REGISTRY.items():
        if any((root / filename).exists() for filename in spec.detect_files):
            detected.append(stack_id)
    return tuple(detected)
