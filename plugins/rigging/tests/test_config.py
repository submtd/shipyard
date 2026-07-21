import json

import pytest

from rigging.config import Config, ConfigError, load_config


def write(tmp_path, data):
    (tmp_path / ".rigging.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".rigging.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".rigging.json" in str(e.value)


def test_non_object_root_raises(tmp_path):
    (tmp_path / ".rigging.json").write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_defaults_fill_in(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert cfg.name == "ci"
    assert cfg.stacks == {"python": ("3.12",)}


def test_null_stack_value_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": None}}))
    assert cfg.stacks == {"node": ("20",)}


def test_explicit_versions_preserved_as_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"versions": ["3.10", "3.11"]}}
    }))
    assert cfg.stacks == {"python": ("3.10", "3.11")}


def test_unknown_stack_id_raises_naming_id_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"ruby": {}}}))
    msg = str(e.value)
    assert "ruby" in msg
    assert "python" in msg
    assert "node" in msg


def test_missing_stacks_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {}))


def test_empty_stacks_object_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {}}))


def test_non_object_stacks_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": "python"}))


@pytest.mark.parametrize("versions", [
    [],
    [123],
    ["3.9 "],
    ["a}}b"],
])
def test_invalid_versions_raise(tmp_path, versions):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"versions": versions}}}))


@pytest.mark.parametrize("name", ["../evil", "a/b", "a.b", "", 5])
def test_invalid_name_raises(tmp_path, name):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"name": name, "stacks": {"python": {}}}))
    assert "name" in str(e.value)


def test_valid_name_accepted(tmp_path):
    cfg = load_config(write(tmp_path, {"name": "my-CI_1", "stacks": {"python": {}}}))
    assert cfg.name == "my-CI_1"


def test_two_stack_config_preserves_key_order(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}, "python": {}}}))
    assert list(cfg.stacks.keys()) == ["node", "python"]


def test_two_stack_config_reversed_order_preserved(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}, "node": {}}}))
    assert list(cfg.stacks.keys()) == ["python", "node"]


def test_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert isinstance(cfg, Config)
    with pytest.raises(Exception):
        cfg.name = "changed"


def test_stack_value_non_object_non_null_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": "3.12"}}))


def test_versions_non_list_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"versions": "3.12"}}}))
