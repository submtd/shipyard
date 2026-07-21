"""The stack registry: known language/toolchain stacks and their
.gitignore sections.

Pure data module. Stdlib only; no subprocess, no os, no networking -- a
later task enforces this invariant over the whole engine via an AST test.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StackSpec:
    """Everything needed to detect a stack and scaffold its .gitignore
    section."""

    id: str
    detect_files: tuple[str, ...]
    gitignore: tuple[str, ...]


BASE = StackSpec(
    id="base",
    detect_files=(),
    gitignore=(".DS_Store", "Thumbs.db"),
)


REGISTRY: dict[str, StackSpec] = {
    "python": StackSpec(
        id="python",
        detect_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        gitignore=(
            "__pycache__/",
            "*.py[cod]",
            "*.egg-info/",
            ".pytest_cache/",
            ".mypy_cache/",
            ".ruff_cache/",
            ".venv/",
            "build/",
            "dist/",
        ),
    ),
    "node": StackSpec(
        id="node",
        detect_files=("package.json",),
        gitignore=(
            "node_modules/",
            "npm-debug.log*",
            "dist/",
            "coverage/",
            ".env",
        ),
    ),
}

STACK_IDS: tuple[str, ...] = tuple(REGISTRY)
