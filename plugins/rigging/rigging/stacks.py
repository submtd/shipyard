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


@dataclass(frozen=True)
class PackageManager:
    """How to drive one JavaScript package manager in CI.

    Install and test are argv TUPLES rather than shell strings, and that is
    deliberate: increment 2 lets a repo supply its own test command, and an
    argv array is the shape that makes shell metacharacters inert. Keeping
    the registry's own defaults in the same shape means user-supplied and
    built-in commands travel one rendering path, so neither can acquire
    quoting behaviour the other lacks.
    """

    id: str
    #: Root-level lockfiles that prove this manager is in charge. Several
    #: for bun, which has shipped two names.
    lockfiles: tuple[str, ...]
    install: tuple[str, ...]
    test: tuple[str, ...]
    #: Extra steps this manager needs before `setup-node` runs -- installing
    #: the manager itself. Empty for npm and yarn, which ship with node.
    setup_steps: tuple[Step, ...] = ()


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
        steps=(),
    ),
}

STACK_IDS: tuple[str, ...] = tuple(REGISTRY)


#: The manager assumed when a repo has a package.json and no other signal.
#: That is simply what an npm repo looks like: npm ships with node, so the
#: absence of any other manager's marker is itself the signal.
DEFAULT_NODE_PACKAGE_MANAGER: str = "npm"

#: How to drive each JavaScript package manager. This replaces the old
#: FOREIGN_NODE_LOCKFILES table, which existed only to say "we cannot drive
#: this" -- the same lockfiles now say WHICH manager to drive.
#:
#: It lives here, beside the node StackSpec, for the reason that table did:
#: these commands are a property of the node job, and whoever changes how
#: that job works has to walk past them.
NODE_PACKAGE_MANAGERS: dict[str, PackageManager] = {
    "npm": PackageManager(
        id="npm",
        lockfiles=("package-lock.json",),
        install=("npm", "ci"),
        test=("npm", "test"),
    ),
    "pnpm": PackageManager(
        id="pnpm",
        lockfiles=("pnpm-lock.yaml",),
        install=("pnpm", "install", "--frozen-lockfile"),
        test=("pnpm", "test"),
        # pnpm does not ship with node, so the runner has to install it.
        setup_steps=(Step(
            uses="pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271",
            uses_version="v6.0.9",
        ),),
    ),
    # Yarn 1 and Yarn 2+ are two toolchains sharing one lockfile name, and
    # their install flags are mutually incompatible: --frozen-lockfile is an
    # error on berry, --immutable is an error on classic. They are separate
    # registry entries because they are separate tools, not one tool with a
    # version field -- a single entry would need a conditional in the
    # renderer, which is exactly the drift this registry exists to prevent.
    "yarn1": PackageManager(
        id="yarn1",
        lockfiles=("yarn.lock",),
        install=("yarn", "install", "--frozen-lockfile"),
        test=("yarn", "test"),
    ),
    "yarn-berry": PackageManager(
        id="yarn-berry",
        lockfiles=("yarn.lock",),
        install=("yarn", "install", "--immutable"),
        test=("yarn", "test"),
    ),
    "bun": PackageManager(
        id="bun",
        # bun has shipped two lockfile names: the original binary `bun.lockb`
        # and the newer text `bun.lock`. A repo may carry either depending on
        # when, and with which bun, it was last installed.
        lockfiles=("bun.lockb", "bun.lock"),
        install=("bun", "install", "--frozen-lockfile"),
        # `bun run test` rather than `bun test`: the latter runs bun's own
        # test runner, while every other entry here runs the repo's `test`
        # script. A repo using vitest under bun would otherwise silently run
        # a different suite than it does locally.
        test=("bun", "run", "test"),
        setup_steps=(Step(
            uses="oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6",
            uses_version="v2.2.0",
        ),),
    ),
}
