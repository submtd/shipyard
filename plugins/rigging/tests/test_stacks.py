import re
import pytest

from rigging import stacks
from rigging.stacks import REGISTRY, STACK_IDS, Step, StackSpec


def test_rigging_version():
    import rigging
    assert rigging.__version__ == "0.3.0"


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


@pytest.mark.parametrize("key", ["python", "node"])
def test_spec_steps_non_empty(key):
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
    assert spec.steps == (Step(run=PYTHON_INSTALL_RUN), Step(run="python -m pytest"))


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
    assert spec.steps == (Step(run="npm ci"), Step(run="npm test"))


def test_step_is_frozen_dataclass():
    step = Step(run="echo hi")
    with pytest.raises(Exception):
        step.run = "changed"


def test_stackspec_is_frozen_dataclass():
    spec = REGISTRY["python"]
    with pytest.raises(Exception):
        spec.id = "changed"


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
