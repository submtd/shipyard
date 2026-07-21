"""The stack registry: known language/toolchain stacks and how to CI them.

Pure data module. Stdlib only; no subprocess, no os, no networking -- a
later task enforces this invariant over the whole engine via an AST test.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Step:
    """One workflow step. Either `uses` (an action) or `run` (a shell line)."""

    name: Optional[str] = None
    uses: Optional[str] = None
    with_: Optional[dict] = None
    run: Optional[str] = None


@dataclass(frozen=True)
class StackSpec:
    """Everything needed to detect a stack and scaffold its CI job."""

    id: str
    detect_files: tuple[str, ...]
    setup_uses: str
    matrix_var: str
    setup_with_key: str
    default_versions: tuple[str, ...]
    steps: tuple[Step, ...]


REGISTRY: dict[str, StackSpec] = {
    "python": StackSpec(
        id="python",
        detect_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        setup_uses="actions/setup-python@v5",
        matrix_var="python",
        setup_with_key="python-version",
        default_versions=("3.12",),
        steps=(
            Step(run="pip install pytest"),
            Step(run="python -m pytest"),
        ),
    ),
    "node": StackSpec(
        id="node",
        detect_files=("package.json",),
        setup_uses="actions/setup-node@v5",
        matrix_var="node",
        setup_with_key="node-version",
        default_versions=("20",),
        steps=(
            Step(run="npm ci"),
            Step(run="npm test"),
        ),
    ),
}

STACK_IDS: tuple[str, ...] = tuple(REGISTRY)
