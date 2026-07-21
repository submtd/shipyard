import pytest

from ballast import stacks
from ballast.stacks import REGISTRY, STACK_IDS, StackSpec


def test_ballast_version():
    import ballast
    assert ballast.__version__ == "0.1.0"


def test_registry_keys():
    assert tuple(REGISTRY) == ("python",)


def test_stack_ids_derived_from_registry():
    assert STACK_IDS == tuple(REGISTRY)
    assert STACK_IDS == ("python",)


def test_python_spec_contents():
    spec = REGISTRY["python"]
    assert spec.id == "python"
    assert spec.detect_files == ("pyproject.toml", "setup.py", "setup.cfg", "requirements.txt")
    assert spec.default_test_paths == ("tests",)
    assert spec.default_import_mode == "importlib"


def test_spec_id_matches_registry_key():
    for key, spec in REGISTRY.items():
        assert spec.id == key


def test_stackspec_is_frozen_dataclass():
    spec = REGISTRY["python"]
    with pytest.raises(Exception):
        spec.id = "changed"
