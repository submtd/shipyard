import pytest

from rigging import stacks
from rigging.stacks import REGISTRY, STACK_IDS, Step, StackSpec


def test_rigging_version():
    import rigging
    assert rigging.__version__ == "0.1.0"


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


def test_python_spec_contents():
    spec = REGISTRY["python"]
    assert spec.detect_files == ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    assert spec.setup_uses == "actions/setup-python@v5"
    assert spec.matrix_var == "python"
    assert spec.setup_with_key == "python-version"
    assert spec.default_versions == ("3.12",)
    assert spec.steps == (Step(run="pip install pytest"), Step(run="python -m pytest"))


def test_node_spec_contents():
    spec = REGISTRY["node"]
    assert spec.detect_files == ("package.json",)
    assert spec.setup_uses == "actions/setup-node@v5"
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
