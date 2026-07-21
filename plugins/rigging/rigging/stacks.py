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
    #: Human-readable tag for a SHA-pinned `uses`, rendered as a trailing
    #: YAML comment (`# v4`). It must stay OUTSIDE the quoted scalar --
    #: inside, it becomes part of the ref and the action fails to resolve.
    #: A registry constant, never user input, so it cannot carry injection.
    uses_version: Optional[str] = None
    with_: Optional[dict] = None
    run: Optional[str] = None


@dataclass(frozen=True)
class StackSpec:
    """Everything needed to detect a stack and scaffold its CI job."""

    id: str
    detect_files: tuple[str, ...]
    setup_uses: str
    #: The tag the pinned setup_uses SHA corresponds to, rendered as a
    #: trailing comment so the pin stays readable and Dependabot can bump
    #: both together.
    setup_uses_version: str
    matrix_var: str
    setup_with_key: str
    default_versions: tuple[str, ...]
    steps: tuple[Step, ...]


REGISTRY: dict[str, StackSpec] = {
    "python": StackSpec(
        id="python",
        detect_files=("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"),
        setup_uses="actions/setup-python@a26af69be951a213d495a4c3e4e4022e16d87065",
        setup_uses_version="v5",
        matrix_var="python",
        setup_with_key="python-version",
        default_versions=("3.12",),
        steps=(
            Step(run=(
                "python -m pip install --upgrade pip\n"
                "pip install pytest\n"
                "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"
            )),
            Step(run="python -m pytest"),
        ),
    ),
    "node": StackSpec(
        id="node",
        detect_files=("package.json",),
        setup_uses="actions/setup-node@a0853c24544627f65ddf259abe73b1d18a591444",
        setup_uses_version="v5",
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
