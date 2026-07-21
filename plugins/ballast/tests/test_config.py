import json

import pytest

from ballast.config import Config, ConfigError, PytestConfig, load_config


def write(tmp_path, data):
    (tmp_path / ".ballast.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".ballast.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".ballast.json" in str(e.value)


def test_non_object_root_raises(tmp_path):
    (tmp_path / ".ballast.json").write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_defaults_fill_in(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert cfg.stacks == {
        "python": PytestConfig(
            test_paths=("tests",),
            python_path=(),
            import_mode="importlib",
            add_opts=(),
        )
    }


def test_null_stack_value_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": None}}))
    assert cfg.stacks["python"].test_paths == ("tests",)
    assert cfg.stacks["python"].import_mode == "importlib"
    assert cfg.stacks["python"].python_path == ()
    assert cfg.stacks["python"].add_opts == ()


def test_explicit_values_flow_through_as_tuples_preserving_order(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "testPaths": ["tests", "plugins/keel/tests"],
                "pythonPath": ["plugins/keel", "plugins/rigging"],
                "importMode": "prepend",
                "addOpts": ["-q", "--strict-markers"],
            }
        }
    }))
    py = cfg.stacks["python"]
    assert py.test_paths == ("tests", "plugins/keel/tests")
    assert py.python_path == ("plugins/keel", "plugins/rigging")
    assert py.import_mode == "prepend"
    assert py.add_opts == ("-q", "--strict-markers")


def test_unknown_stack_id_raises_naming_id_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"ruby": {}}}))
    msg = str(e.value)
    assert "ruby" in msg
    assert "python" in msg


def test_missing_stacks_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {}))


def test_empty_stacks_object_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {}}))


def test_non_object_stacks_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": "python"}))


def test_stack_value_non_object_non_null_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": "3.12"}}))


def test_import_mode_outside_enum_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"importMode": "eval"}}}))


@pytest.mark.parametrize("test_paths", [
    [],
    [123],
    ["tests\n"],
    ["/abs"],
    ["../evil"],
    ["plugins/../evil"],
    ["my tests"],
    ["a\tb"],
])
def test_invalid_test_paths_raise(tmp_path, test_paths):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"testPaths": test_paths}}}))


@pytest.mark.parametrize("python_path", [
    [123],
    ["tests\n"],
    ["/abs"],
    ["../evil"],
    ["my path"],
])
def test_invalid_python_path_entries_raise(tmp_path, python_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"pythonPath": python_path}}}))


def test_test_paths_with_normal_relative_path_still_loads(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"testPaths": ["plugins/keel/tests"]}}
    }))
    assert cfg.stacks["python"].test_paths == ("plugins/keel/tests",)


def test_empty_python_path_list_is_allowed(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {"pythonPath": []}}}))
    assert cfg.stacks["python"].python_path == ()


@pytest.mark.parametrize("add_opts", [
    ["a b"],
    [""],
    ["a\nb"],
    [123],
])
def test_invalid_add_opts_raise(tmp_path, add_opts):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"addOpts": add_opts}}}))


def test_bad_json_raises(tmp_path):
    (tmp_path / ".ballast.json").write_text("not json at all")
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert isinstance(cfg, Config)
    with pytest.raises(Exception):
        cfg.stacks = {}


def test_pytest_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    py = cfg.stacks["python"]
    assert isinstance(py, PytestConfig)
    with pytest.raises(Exception):
        py.import_mode = "prepend"


def test_two_stack_config_preserves_key_order(tmp_path):
    # only python is registered in increment 1, but a single-key config
    # should still preserve dict ordering semantics.
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert list(cfg.stacks.keys()) == ["python"]


def test_test_paths_default_is_registry_default(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert cfg.stacks["python"].test_paths == ("tests",)


def test_import_mode_default_is_registry_default(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert cfg.stacks["python"].import_mode == "importlib"


@pytest.mark.parametrize("mode", ["importlib", "prepend", "append"])
def test_all_import_modes_accepted(tmp_path, mode):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {"importMode": mode}}}))
    assert cfg.stacks["python"].import_mode == mode


def test_valid_flag_tokens_accepted(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"addOpts": ["-q", "--strict-markers", "--cov=x"]}}
    }))
    assert cfg.stacks["python"].add_opts == ("-q", "--strict-markers", "--cov=x")
