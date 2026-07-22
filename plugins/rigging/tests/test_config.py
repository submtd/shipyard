import json

import pytest

from rigging.config import Config, ConfigError, load_config
from rigging.stacks import REGISTRY


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
    assert cfg.stacks["python"].versions == ("3.12",)


def test_null_stack_value_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": None}}))
    assert cfg.stacks["node"].versions == ("20",)


def test_explicit_versions_preserved_as_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"versions": ["3.10", "3.11"]}}
    }))
    assert cfg.stacks["python"].versions == ("3.10", "3.11")


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


def test_name_with_trailing_newline_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"name": "ci\n", "stacks": {"python": {}}}))


def test_version_with_trailing_newline_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {
            "stacks": {"python": {"versions": ["3.9\n"]}}
        }))


def test_valid_name_and_version_still_load(tmp_path):
    cfg = load_config(write(tmp_path, {
        "name": "ci", "stacks": {"python": {"versions": ["3.9"]}}
    }))
    assert cfg.name == "ci"
    assert cfg.stacks["python"].versions == ("3.9",)


# --- unknown keys ----------------------------------------------------------
#
# Silently dropping an unrecognised key is how a one-character typo becomes
# an invisible behaviour change: "versinos" reverted the whole CI matrix to
# the registry default, and the user's rendered workflow tested a Python
# version they never asked for. `triggers` is worse -- the spec deliberately
# does not support it, so a user who adds it got silence rather than an
# answer.


def test_unknown_top_level_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {}}, "triggers": {"branches": ["main"]}}))
    assert "triggers" in str(e.value)


def test_unknown_per_stack_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"versinos": ["3.9"]}}}))
    assert "versinos" in str(e.value)


def test_known_keys_together_still_load(tmp_path):
    cfg = load_config(write(tmp_path, {"name": "ci", "stacks": {"python": {"versions": ["3.12"]}}}))
    assert cfg.name == "ci"
    assert cfg.stacks["python"].versions == ("3.12",)


# --- pushBranches -------------------------------------------------------


def test_push_branches_defaults_to_the_conventional_trunk(tmp_path):
    (tmp_path / ".rigging.json").write_text(json.dumps({"stacks": {"python": {}}}))
    assert load_config(tmp_path).push_branches == ("main",)


def test_push_branches_is_read_from_the_config(tmp_path):
    cfg = dict({"stacks": {"python": {}}}, pushBranches=["main", "release/1.x"])
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).push_branches == ("main", "release/1.x")


@pytest.mark.parametrize("bad", [[], "main", {}, [""], ["a b"], [1], ["-x"], ["a$b"]])
def test_push_branches_rejects_what_it_cannot_safely_render(tmp_path, bad):
    """The value is rendered straight into YAML, so anything needing quoting
    or escaping is refused rather than emitted and hoped for. An empty list
    is refused too: it renders `branches: []`, which silently disables push
    CI entirely -- exactly the failure the key exists to prevent."""
    cfg = dict({"stacks": {"python": {}}}, pushBranches=bad)
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_stacks_values_are_stack_configs(tmp_path):
    """The per-stack container the next three increments hang their keys
    off. Today it holds only versions."""
    from rigging.config import StackConfig

    cfg = load_config(write(tmp_path, {"stacks": {"python": {"versions": ["3.12"]}}}))
    assert cfg.stacks["python"] == StackConfig(versions=("3.12",))


def test_stack_config_is_frozen():
    """FrozenInstanceError specifically, not a bare Exception -- a bare
    `pytest.raises(Exception)` passes on a typo in the attribute name and so
    proves nothing about frozenness. Matches keel/tests/test_facts.py."""
    import dataclasses

    from rigging.config import StackConfig

    sc = StackConfig(versions=("3.12",))
    with pytest.raises(dataclasses.FrozenInstanceError):
        sc.versions = ("3.11",)


def test_registry_defaults_still_fill_in_absent_versions(tmp_path):
    """A stack with `{}` still takes its registry default -- the refactor
    must not have moved where defaults come from."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].versions == REGISTRY["node"].default_versions
