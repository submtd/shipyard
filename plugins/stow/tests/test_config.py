import json

import pytest

from stow.config import Config, ConfigError, load_config


def write(tmp_path, data):
    (tmp_path / ".stow.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".stow.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".stow.json" in str(e.value)


def test_non_object_root_raises(tmp_path):
    (tmp_path / ".stow.json").write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_single_stack_loads(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert cfg.stacks == {"python": {}}


def test_null_stack_value_normalized_to_empty_dict(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": None}}))
    assert cfg.stacks == {"node": {}}


def test_empty_stacks_object_means_base_only(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {}}))
    assert cfg.stacks == {}


def test_missing_stacks_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {}))


def test_unknown_stack_id_raises_naming_id_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"ruby": {}}}))
    msg = str(e.value)
    assert "ruby" in msg
    assert "python" in msg
    assert "node" in msg


def test_base_as_stack_key_raises_naming_it_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"base": {}}}))
    msg = str(e.value)
    assert "base" in msg
    assert "python" in msg
    assert "node" in msg


def test_non_object_stacks_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": "python"}))


def test_stack_value_non_object_non_null_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": 5}}))


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
        cfg.stacks = {}
