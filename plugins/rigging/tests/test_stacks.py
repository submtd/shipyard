import re
import pytest

from rigging import stacks
from rigging.stacks import REGISTRY, STACK_IDS, Step, StackSpec


def test_rigging_version():
    import rigging
    assert rigging.__version__ == "0.6.0"


def test_registry_keys():
    assert tuple(REGISTRY) == ("python", "node")


def test_stack_ids_derived_from_registry():
    assert STACK_IDS == tuple(REGISTRY)


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_id_matches_registry_key(key):
    assert REGISTRY[key].id == key


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_detect_files_non_empty(key):
    assert isinstance(REGISTRY[key].detect_files, tuple)
    assert len(REGISTRY[key].detect_files) > 0


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_default_versions_non_empty(key):
    assert isinstance(REGISTRY[key].default_versions, tuple)
    assert len(REGISTRY[key].default_versions) > 0


@pytest.mark.parametrize("key", ["python"])
def test_spec_steps_non_empty(key):
    """Only python's steps live on the StackSpec itself; node's now come
    from the selected package manager (see test_node_spec_no_longer_carries_its_own_steps)."""
    assert isinstance(REGISTRY[key].steps, tuple)
    assert len(REGISTRY[key].steps) > 0


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_steps_are_run_only_no_uses(key):
    for step in REGISTRY[key].steps:
        assert isinstance(step, Step)
        assert step.run is not None
        assert step.uses is None


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_steps_run_has_no_expression_interpolation(key):
    for step in REGISTRY[key].steps:
        assert "${{" not in step.run


PYTHON_INSTALL_RUN = (
    "python -m pip install --upgrade pip\n"
    "pip install 'pytest>=8,<9'\n"
    "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"
)


def test_python_spec_contents():
    spec = REGISTRY["python"]
    assert spec.detect_files == ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    assert spec.setup_uses.split("@")[0] == "actions/setup-python"
    assert spec.matrix_var == "python"
    assert spec.setup_with_key == "python-version"
    assert spec.default_versions == ("3.12",)
    # pytest moved off steps and onto default_test (see
    # test_python_steps_no_longer_carry_the_test_step / test_python_default_test_is_pytest).
    assert spec.steps == (Step(run=PYTHON_INSTALL_RUN),)
    assert spec.default_test == ("python", "-m", "pytest")


def test_python_install_step_matches_github_starter_workflow_shape():
    """The python install step mirrors GitHub's official python starter
    workflow: upgrade pip, install pytest (version-bounded, so a pytest major
    release cannot break a repo whose own code never changed), and conditionally install the
    project's own requirements.txt if present -- so CI is red only when the
    project's own tests are red, not merely because its dependencies were
    never installed."""
    spec = REGISTRY["python"]
    install_step = spec.steps[0]
    assert "\n" in install_step.run
    lines = install_step.run.split("\n")
    assert lines[0] == "python -m pip install --upgrade pip"
    assert lines[1] == "pip install 'pytest>=8,<9'"
    assert lines[2] == "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"


def test_node_spec_contents():
    spec = REGISTRY["node"]
    assert spec.detect_files == ("package.json",)
    assert spec.setup_uses.split("@")[0] == "actions/setup-node"
    assert spec.matrix_var == "node"
    assert spec.setup_with_key == "node-version"
    assert spec.default_versions == ("20",)
    # spec.steps == () now: node's steps come from the selected package
    # manager (see test_node_spec_no_longer_carries_its_own_steps below).


def test_step_is_frozen_dataclass():
    step = Step(run="echo hi")
    with pytest.raises(Exception):
        step.run = "changed"


def test_stackspec_is_frozen_dataclass():
    spec = REGISTRY["python"]
    with pytest.raises(Exception):
        spec.id = "changed"


def test_python_default_test_is_pytest():
    assert stacks.REGISTRY["python"].default_test == ("python", "-m", "pytest")


def test_node_has_no_stack_default_test():
    # node's default test comes from its package manager, not the stack.
    assert stacks.REGISTRY["node"].default_test == ()


def test_python_steps_no_longer_carry_the_test_step():
    # pytest moved to default_test; steps is install-only now. Check for the
    # test INVOCATION ("python -m pytest"), not the bare word "pytest" -- the
    # install step legitimately contains "pip install 'pytest>=8,<9'".
    runs = [s.run for s in stacks.REGISTRY["python"].steps if s.run]
    assert not any("python -m pytest" in r for r in runs)


# --- action refs must be SHA pins ----------------------------------------

_SHA_PIN = re.compile(r"[^@\s]+@[0-9a-f]{40}")


def test_every_registry_action_ref_is_a_sha_pin():
    """A moving tag (`@v4`) is repointable by the action's owner, so it is
    not a pin no matter what the docs call it. Every ref rigging emits must
    name an immutable commit."""
    from rigging.plan import CHECKOUT_STEP

    refs = [CHECKOUT_STEP.uses] + [spec.setup_uses for spec in REGISTRY.values()]
    for ref in refs:
        assert _SHA_PIN.fullmatch(ref), f"{ref} is not pinned to a commit SHA"


def test_every_pinned_ref_carries_a_version_comment():
    # The SHA is unreadable alone; the trailing comment is what keeps it
    # reviewable and what Dependabot bumps alongside the pin.
    from rigging.plan import CHECKOUT_STEP

    assert CHECKOUT_STEP.uses_version
    for spec in REGISTRY.values():
        assert spec.setup_uses_version


# --- what the node steps actually require (issue #24) ---------------------
#
# NODE_PACKAGE_MANAGER and FOREIGN_NODE_LOCKFILES (and the refusal-guard
# tests that pinned their contents) are gone as of the package-manager
# registry below: the lockfile-to-manager table now says WHICH manager to
# drive instead of only which ones to refuse. detect.py still reads the old
# names until a later task rewrites it.


def test_npm_manager_is_registered():
    from rigging.stacks import DEFAULT_NODE_PACKAGE_MANAGER, NODE_PACKAGE_MANAGERS

    assert DEFAULT_NODE_PACKAGE_MANAGER == "npm"
    npm = NODE_PACKAGE_MANAGERS["npm"]
    assert npm.lockfiles == ("package-lock.json",)
    assert npm.install == ("npm", "ci")
    assert npm.test == ("npm", "test")
    assert npm.setup_steps == ()


def test_manager_ids_match_their_keys():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for key, manager in NODE_PACKAGE_MANAGERS.items():
        assert manager.id == key


def test_node_spec_no_longer_carries_its_own_steps():
    """The node stack's steps now come from the selected manager. A leftover
    `steps` tuple would silently win or silently be ignored -- either way it
    would be a second, drifting source of truth."""
    assert REGISTRY["node"].steps == ()


def test_python_spec_still_carries_its_own_steps():
    """Only node is manager-driven. Python's steps are multi-line shell and
    stay exactly where they were."""
    assert REGISTRY["python"].steps


# --- pnpm, yarn (both majors), and bun -------------------------------------

#: Alias for the SHA-pin regex above, under the name the tests below use.
_SHA_PINNED_REF_RE = _SHA_PIN


def test_every_manager_setup_step_is_sha_pinned():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager in NODE_PACKAGE_MANAGERS.values():
        for step in manager.setup_steps:
            assert _SHA_PINNED_REF_RE.fullmatch(step.uses), step.uses
            assert step.uses_version


def test_no_manager_command_embeds_an_expression():
    """Registry commands become `run:` lines, as do setup_steps and
    post_setup_steps -- yarn-berry's `corepack enable` is the first entry to
    carry one. An expression anywhere in these would be interpolated by
    Actions before any shell saw it, so every install/test argv element and
    every step's run body and uses ref must be checked."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager in NODE_PACKAGE_MANAGERS.values():
        for part in manager.install + manager.test:
            assert "${{" not in part
        for step in manager.setup_steps + manager.post_setup_steps:
            if step.run is not None:
                assert "${{" not in step.run
            if step.uses is not None:
                assert "${{" not in step.uses


def test_bun_runs_the_repos_test_script_not_buns_runner():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    assert NODE_PACKAGE_MANAGERS["bun"].test == ("bun", "run", "test")


# --- invariants inherited from the deleted FOREIGN_NODE_LOCKFILES tests ----
#
# Task 2 removed three guards along with the table they described. The
# properties they protected are still real; these are their replacements
# against the registry that took its place.


def test_install_and_test_invoke_the_same_binary():
    """Replaces the old drift guard that checked the npm constant against the
    node steps' first word. Catches the copy-paste error this table invites:
    a pnpm entry whose test line still says npm."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager_id, manager in NODE_PACKAGE_MANAGERS.items():
        assert manager.install[0] == manager.test[0], manager_id


def test_no_manager_claims_package_lock_except_npm():
    """`npm ci` REQUIRES package-lock.json. Another manager claiming it would
    select the wrong toolchain for exactly the repos rigging always handled
    correctly."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager_id, manager in NODE_PACKAGE_MANAGERS.items():
        if manager_id != "npm":
            assert "package-lock.json" not in manager.lockfiles


def test_no_lockfile_collides_with_a_stack_detect_file():
    """A lockfile that was also a detect file would make stack detection and
    manager selection fight over the same marker."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    detect_files = set(REGISTRY["node"].detect_files)
    for manager in NODE_PACKAGE_MANAGERS.values():
        assert not set(manager.lockfiles) & detect_files


def test_only_yarn_shares_a_lockfile_between_managers():
    """yarn1 and yarn-berry deliberately share yarn.lock -- that sharing is
    what detection has to disambiguate by major version. Any OTHER pair
    sharing a lockfile would make selection genuinely undecidable."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    owners = {}
    for manager_id, manager in NODE_PACKAGE_MANAGERS.items():
        for lockfile in manager.lockfiles:
            owners.setdefault(lockfile, set()).add(manager_id)
    for lockfile, ids in owners.items():
        if len(ids) > 1:
            assert ids == {"yarn1", "yarn-berry"}, (lockfile, ids)


def test_yarn_berry_enables_corepack_after_node_setup():
    """`--immutable` is a Yarn 2+ flag and the runners ship Yarn 1.22.x, so
    without corepack the install line fails every run."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    berry = NODE_PACKAGE_MANAGERS["yarn-berry"]
    assert berry.post_setup_steps == (Step(run="corepack enable"),)


def test_only_yarn_berry_needs_a_post_setup_step():
    """npm and yarn classic ship with the runner; pnpm and bun install their
    own binary in a pre-setup action. Berry is the only one that needs node
    to exist first."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    needing = {i for i, m in NODE_PACKAGE_MANAGERS.items() if m.post_setup_steps}
    assert needing == {"yarn-berry"}
