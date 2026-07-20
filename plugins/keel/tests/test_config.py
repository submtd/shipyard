import json
import pytest
from keel.config import load_config, Config, ConfigError


def write(tmp_path, data):
    (tmp_path / ".keel.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_defaults_fill_in(tmp_path):
    cfg = load_config(write(tmp_path, {}))
    assert cfg.topology == "gitflow"
    assert cfg.production == "main"
    assert cfg.integration == "develop"
    assert cfg.review_policy == "review"
    assert cfg.require_changelog is True


def test_trunk_collapses_integration_into_production(tmp_path):
    cfg = load_config(write(tmp_path, {"topology": "trunk"}))
    assert cfg.integration == cfg.production == "main"


def test_explicit_values_win(tmp_path):
    cfg = load_config(write(tmp_path, {
        "branches": {"production": "master", "integration": "dev"},
        "reviewPolicy": "approval",
        "requireChangelog": False,
    }))
    assert cfg.production == "master"
    assert cfg.integration == "dev"
    assert cfg.review_policy == "approval"
    assert cfg.require_changelog is False


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".keel.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".keel.json" in str(e.value)


def test_unknown_enum_value_raises(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"reviewPolicy": "vibes"}))
    assert "reviewPolicy" in str(e.value)


def test_unknown_topology_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"topology": "octopus"}))


@pytest.mark.parametrize("field", ["branches", "prefixes", "mergeStrategy"])
def test_non_object_nested_field_raises(tmp_path, field):
    """Non-dict values for nested object fields must raise ConfigError."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {field: "main"}))
    assert field in str(e.value)


def test_non_boolean_require_changelog_raises(tmp_path):
    """Non-boolean requireChangelog must raise ConfigError."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"requireChangelog": "false"}))
    assert "requireChangelog" in str(e.value)


def test_trunk_collapses_integration_even_with_explicit_value(tmp_path):
    """Trunk topology must collapse integration to production, ignoring explicit branches.integration."""
    cfg = load_config(write(tmp_path, {
        "topology": "trunk",
        "branches": {"integration": "dev", "production": "main"}
    }))
    assert cfg.integration == "main"
    assert cfg.production == "main"
