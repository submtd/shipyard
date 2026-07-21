"""The stack registry: known language/toolchain stacks and their pytest defaults.

Pure data module. Stdlib only; no subprocess, no os, no networking -- a
later task enforces this invariant over the whole engine via an AST test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StackSpec:
    """Everything needed to detect a stack and render its pytest.ini defaults."""

    id: str
    detect_files: tuple[str, ...]
    default_test_paths: tuple[str, ...]
    default_import_mode: str


REGISTRY: dict[str, StackSpec] = {
    "python": StackSpec(
        id="python",
        detect_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        default_test_paths=("tests",),
        default_import_mode="importlib",
    ),
}

STACK_IDS: tuple[str, ...] = tuple(REGISTRY)
