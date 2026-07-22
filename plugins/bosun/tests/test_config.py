import json

import pytest

from bosun.config import Config, ConfigError, EcosystemConfig, load_config


def write(tmp_path, data):
    (tmp_path / ".bosun.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".bosun.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".bosun.json" in str(e.value)


def test_non_object_root_raises(tmp_path):
    (tmp_path / ".bosun.json").write_text(json.dumps(["not", "an", "object"]))
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_single_ecosystem_defaults_to_weekly(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"githubActions": {}}}))
    assert isinstance(cfg, Config)
    assert cfg.ecosystems == {"githubActions": EcosystemConfig(interval="weekly")}


def test_null_ecosystem_value_uses_defaults(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"githubActions": None}}))
    assert cfg.ecosystems == {"githubActions": EcosystemConfig(interval="weekly")}


def test_explicit_interval_preserved(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {"interval": "monthly"}}}))
    assert cfg.ecosystems == {"python": EcosystemConfig(interval="monthly")}


def test_unknown_ecosystem_id_raises_naming_id_and_allowed(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"ecosystems": {"ruby": {}}}))
    msg = str(e.value)
    assert "ruby" in msg
    assert "githubActions" in msg
    assert "python" in msg
    assert "node" in msg


def test_missing_ecosystems_key_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {}))


def test_empty_ecosystems_object_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"ecosystems": {}}))


def test_non_object_ecosystems_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"ecosystems": "python"}))


def test_ecosystem_value_non_object_non_null_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"ecosystems": {"python": 5}}))


@pytest.mark.parametrize("interval", ["daily", "weekly", "monthly"])
def test_valid_intervals_accepted(tmp_path, interval):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {"interval": interval}}}))
    assert cfg.ecosystems["python"].interval == interval


def test_invalid_interval_raises_naming_interval(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"ecosystems": {"python": {"interval": "hourly"}}}))
    msg = str(e.value)
    assert "interval" in msg


def test_two_ecosystem_config_preserves_key_order(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"node": {}, "python": {}}}))
    assert list(cfg.ecosystems.keys()) == ["node", "python"]


def test_two_ecosystem_config_reversed_order_preserved(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {}, "node": {}}}))
    assert list(cfg.ecosystems.keys()) == ["python", "node"]


def test_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {}}}))
    assert isinstance(cfg, Config)
    with pytest.raises(Exception):
        cfg.ecosystems = {}


def test_ecosystem_config_is_frozen_dataclass(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {}}}))
    with pytest.raises(Exception):
        cfg.ecosystems["python"].interval = "daily"


def test_interval_non_string_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"ecosystems": {"python": {"interval": 7}}}))


# --- unknown keys ----------------------------------------------------------
#
# The hand-edit path is where typos actually happen, and it was the lenient
# one: scaffold.propose_config already raises on a typo'd ecosystem id, but
# load_config accepted "intrval" and silently gave the user weekly when they
# asked for daily.


def test_unknown_top_level_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"ecosystems": {"python": {}}, "version": 3}))
    assert "version" in str(e.value)


def test_unknown_per_ecosystem_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"ecosystems": {"python": {"intrval": "daily"}}}))
    assert "intrval" in str(e.value)


def test_known_keys_still_load(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"python": {"interval": "daily"}}}))
    assert cfg.ecosystems["python"].interval == "daily"


# --- targetBranch -----------------------------------------------------------
#
# Absent means "let Dependabot use the repository default branch", which is
# the right answer under a trunk topology and the wrong one under gitflow --
# where the default branch is production. These cases pin down that the key
# is genuinely optional (so every config written before it existed still
# loads unchanged) and that what it accepts is narrow enough to render into
# YAML without quoting or escaping surprises.


def test_target_branch_absent_is_none(tmp_path):
    cfg = load_config(write(tmp_path, {"ecosystems": {"githubActions": {}}}))
    assert cfg.target_branch is None


def test_target_branch_explicit_null_is_none(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ecosystems": {"githubActions": {}},
        "targetBranch": None,
    }))
    assert cfg.target_branch is None


def test_target_branch_is_carried_through(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ecosystems": {"githubActions": {}},
        "targetBranch": "develop",
    }))
    assert cfg.target_branch == "develop"


def test_target_branch_accepts_slashes_and_dots(tmp_path):
    cfg = load_config(write(tmp_path, {
        "ecosystems": {"githubActions": {}},
        "targetBranch": "release/1.2.x",
    }))
    assert cfg.target_branch == "release/1.2.x"


@pytest.mark.parametrize("bad", [
    "",                          # empty
    "-develop",                  # leading dash reads as a flag
    "develop branch",            # whitespace
    "develop\ninjected: true",   # a newline is a new YAML key
    'develop"',                  # would need escaping in a quoted scalar
    "${{ github.ref }}",         # an expression, not a branch
    5,                           # not a string
    ["develop"],                 # not a string
])
def test_hostile_or_malformed_target_branch_raises(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "ecosystems": {"githubActions": {}},
            "targetBranch": bad,
        }))
    assert "targetBranch" in str(e.value)
