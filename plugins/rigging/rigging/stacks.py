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
        setup_uses="actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
        setup_uses_version="v7",
        matrix_var="python",
        setup_with_key="python-version",
        default_versions=("3.12",),
        steps=(
            Step(run=(
                "python -m pip install --upgrade pip\n"
                "pip install 'pytest>=8,<9'\n"
                "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"
            )),
            Step(run="python -m pytest"),
        ),
    ),
    "node": StackSpec(
        id="node",
        detect_files=("package.json",),
        setup_uses="actions/setup-node@820762786026740c76f36085b0efc47a31fe5020",
        setup_uses_version="v7",
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


#: The one package manager the node stack's steps above can actually drive.
#: This is not a preference -- it is a *reading* of those steps: `npm ci`
#: installs from a `package-lock.json` and fails outright when there isn't
#: one, and `npm test` shells out to npm's own script runner. Neither line
#: works in a repo whose dependency graph is recorded by some other tool.
NODE_PACKAGE_MANAGER: str = "npm"

#: Root-level markers that prove a *different* JavaScript package manager is
#: in charge, mapped to the manager each one implies.
#:
#: This lives here, immediately below the node StackSpec, rather than in
#: detect.py, because it is not a fact about detection -- it is a property of
#: the steps directly above it. `npm ci`/`npm test` is what makes pnpm-lock.yaml
#: disqualifying; change the steps to `pnpm install`/`pnpm test` and this table
#: is wrong in the same edit. Keeping the constraint adjacent to the thing it
#: constrains is the only arrangement where the two cannot silently drift
#: apart: whoever teaches rigging to drive pnpm has to walk past this constant
#: to do it.
#:
#: `detect_files=("package.json",)` is why this is needed at all. *Every*
#: JavaScript repo has a package.json, so every pnpm/yarn/bun repo detects as
#: "node" -- and, without this table, would be handed an `npm ci` workflow
#: that dies on its first step in every single run.
FOREIGN_NODE_LOCKFILES: dict[str, str] = {
    "pnpm-lock.yaml": "pnpm",
    "yarn.lock": "yarn",
    # bun has shipped two lockfile names: the original binary `bun.lockb` and
    # the newer text `bun.lock`. Both are listed because a repo may carry
    # either one depending on when (and with which bun) it was last installed.
    "bun.lockb": "bun",
    "bun.lock": "bun",
}
