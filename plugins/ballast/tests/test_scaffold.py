import itertools
import json

import pytest

from ballast.config import load_config
from ballast.scaffold import CONFIG_FILES, classify_files, propose_config
from ballast.stacks import REGISTRY, STACK_IDS


def _all_non_empty_subsets(ids):
    for r in range(1, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_non_empty_subsets(STACK_IDS))


def test_config_files_value():
    assert CONFIG_FILES == [".ballast.json", "pytest.ini"]


def test_single_stack_proposes_dict_with_defaults():
    cfg = propose_config({"stacks": ["python"]})
    assert cfg == {"stacks": {"python": {}}}


@pytest.mark.parametrize("subset", ALL_SUBSETS, ids=lambda s: "-".join(s))
def test_every_non_empty_subset_round_trips_through_load_config(tmp_path, subset):
    # The one non-negotiable guarantee: init can never write a .ballast.json
    # that ballast itself would reject.
    cfg = propose_config({"stacks": list(subset)})
    (tmp_path / ".ballast.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)  # must not raise
    assert loaded is not None
    assert set(loaded.stacks.keys()) == set(subset)
    for stack_id in subset:
        spec = REGISTRY[stack_id]
        pytest_config = loaded.stacks[stack_id]
        assert pytest_config.test_paths == spec.default_test_paths
        assert pytest_config.import_mode == spec.default_import_mode
        assert pytest_config.python_path == ()
        assert pytest_config.add_opts == ()


def test_explicit_fields_flow_through(tmp_path):
    cfg = propose_config({
        "stacks": ["python"],
        "configs": {
            "python": {
                "testPaths": ["tests", "plugins/keel/tests"],
                "pythonPath": ["plugins/keel"],
                "importMode": "prepend",
                "addOpts": ["-q", "--strict-markers"],
            }
        },
    })
    assert cfg["stacks"]["python"] == {
        "testPaths": ["tests", "plugins/keel/tests"],
        "pythonPath": ["plugins/keel"],
        "importMode": "prepend",
        "addOpts": ["-q", "--strict-markers"],
    }
    (tmp_path / ".ballast.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    py = loaded.stacks["python"]
    assert py.test_paths == ("tests", "plugins/keel/tests")
    assert py.python_path == ("plugins/keel",)
    assert py.import_mode == "prepend"
    assert py.add_opts == ("-q", "--strict-markers")


def test_configs_only_applied_to_named_stack():
    cfg = propose_config({
        "stacks": ["python"],
        "configs": {"python": {"importMode": "append"}},
    })
    assert cfg["stacks"]["python"] == {"importMode": "append"}


def test_missing_configs_key_defaults_to_empty_per_stack():
    cfg = propose_config({"stacks": ["python"]})
    assert cfg["stacks"]["python"] == {}


def test_missing_stacks_key_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({})


def test_empty_stacks_list_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": []})


def test_stacks_not_a_list_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": "python"})


def test_unknown_stack_id_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": ["ruby"]})


def test_configs_not_a_dict_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="configs"):
        propose_config({"stacks": ["python"], "configs": ["not", "a", "dict"]})


def test_stack_config_not_a_dict_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="configs"):
        propose_config({"stacks": ["python"], "configs": {"python": "oops"}})


def test_bad_import_mode_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="importMode"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"importMode": "eval"}},
        })


@pytest.mark.parametrize(
    "bad_path",
    ["my tests", "/abs", "../evil"],
    ids=["space", "leading-slash", "dotdot"],
)
def test_bad_test_path_raises_value_error_naming_field(bad_path):
    with pytest.raises(ValueError, match="testPaths"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"testPaths": [bad_path]}},
        })


@pytest.mark.parametrize(
    "bad_path",
    ["my path", "/abs", "../evil"],
    ids=["space", "leading-slash", "dotdot"],
)
def test_bad_python_path_raises_value_error_naming_field(bad_path):
    with pytest.raises(ValueError, match="pythonPath"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"pythonPath": [bad_path]}},
        })


def test_bad_add_opts_token_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="addOpts"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"addOpts": ["a b"]}},
        })


def test_empty_test_paths_list_raises_value_error_naming_field():
    # Mirrors config.load_config's own non-empty rule for testPaths -- an
    # empty list here would otherwise silently break the round-trip
    # guarantee once written and reloaded.
    with pytest.raises(ValueError, match="testPaths"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"testPaths": []}},
        })


def test_empty_python_path_list_is_allowed_and_round_trips(tmp_path):
    cfg = propose_config({
        "stacks": ["python"],
        "configs": {"python": {"pythonPath": []}},
    })
    assert cfg["stacks"]["python"] == {"pythonPath": []}
    (tmp_path / ".ballast.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks["python"].python_path == ()


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / ".ballast.json").write_text("{}")
    result = classify_files(tmp_path, CONFIG_FILES)
    assert result == {
        ".ballast.json": "present",
        "pytest.ini": "absent",
    }


def test_classify_files_both_present(tmp_path):
    (tmp_path / ".ballast.json").write_text("{}")
    (tmp_path / "pytest.ini").write_text("[pytest]\n")
    result = classify_files(tmp_path, CONFIG_FILES)
    assert result == {
        ".ballast.json": "present",
        "pytest.ini": "present",
    }


def test_classify_files_both_absent(tmp_path):
    result = classify_files(tmp_path, CONFIG_FILES)
    assert result == {
        ".ballast.json": "absent",
        "pytest.ini": "absent",
    }
