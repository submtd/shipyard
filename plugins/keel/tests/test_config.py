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


@pytest.mark.parametrize("field,value", [
    ("production", 5),
    ("production", ""),
    ("integration", 5),
    ("integration", None),
])
def test_non_string_or_empty_branch_name_raises(tmp_path, field, value):
    # Predecessor's exact silent-failure mode: {"branches":{"production":5}}
    # used to yield production=5, so _protected() became {5, "develop"} and
    # NO branch name could ever match it -- the protected-branch rule
    # silently disabled itself.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"branches": {field: value}}))
    assert field in str(e.value)


@pytest.mark.parametrize("field,value", [
    ("feature", 5),
    ("release", ""),
    ("hotfix", None),
])
def test_non_string_or_empty_prefix_raises(tmp_path, field, value):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"prefixes": {field: value}}))
    assert field in str(e.value)


def test_trunk_collapses_integration_even_with_explicit_value(tmp_path):
    """Trunk topology must collapse integration to production, ignoring explicit branches.integration."""
    cfg = load_config(write(tmp_path, {
        "topology": "trunk",
        "branches": {"integration": "dev", "production": "main"}
    }))
    assert cfg.integration == "main"
    assert cfg.production == "main"


# --- unknown keys ----------------------------------------------------------


def test_unknown_top_level_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"topology": "trunk", "reviewPolicyy": "none"}))
    assert "reviewPolicyy" in str(e.value)


def test_unknown_nested_branches_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"branches": {"prodction": "main"}}))
    assert "prodction" in str(e.value)


def test_unknown_nested_prefixes_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"prefixes": {"bugfix": "bugfix/"}}))
    assert "bugfix" in str(e.value)


def test_unknown_nested_merge_strategy_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"mergeStrategy": {"toMain": "squash"}}))
    assert "toMain" in str(e.value)


def test_every_documented_key_together_still_loads(tmp_path):
    cfg = load_config(write(tmp_path, {
        "topology": "gitflow",
        "branches": {"production": "main", "integration": "develop"},
        "prefixes": {"feature": "feature/", "release": "release/", "hotfix": "hotfix/"},
        "mergeStrategy": {"toIntegration": "squash", "toProduction": "merge"},
        "contributions": "both",
        "reviewPolicy": "review",
        "requireChangelog": True,
    }))
    assert cfg.topology == "gitflow"
    assert cfg.merge_to_production == "merge"
