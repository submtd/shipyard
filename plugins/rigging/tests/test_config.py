import json

import pytest

from rigging.config import Config, ConfigError, ResolvedService, load_config
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


def test_package_manager_defaults_to_none(tmp_path):
    """None means "unset", which build_plan reads as npm. Not written out as
    a default so a config authored today does not freeze one answer in."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].package_manager is None


def test_package_manager_is_read(tmp_path):
    """An explicitly configured manager is carried through, and is
    distinguishable from the unset case above. Uses "npm" because it is the
    only registered manager at this point in the plan -- a later task adds
    pnpm/yarn/bun and covers them in the golden tests."""
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": "npm"}}}))
    assert cfg.stacks["node"].package_manager == "npm"


def test_explicit_null_package_manager_means_unset(tmp_path):
    """`dict.get` cannot distinguish an absent key from one set to null, and
    this codebase already treats an explicit null as "unset" elsewhere (see
    bosun's targetBranch). Pinned so the two spellings cannot drift apart."""
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": None}}}))
    assert cfg.stacks["node"].package_manager is None


@pytest.mark.parametrize("bad", ["npm7", "", "NPM", 5, ["npm"], {"a": 1}])
def test_unknown_package_manager_raises_naming_the_field(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"packageManager": bad}}}))
    assert "packageManager" in str(e.value)


def test_package_manager_rejected_for_a_stack_that_has_no_managers(tmp_path):
    """Python has no package-manager concept, so setting one is a user
    believing they configured something that is silently discarded -- the
    same failure the unknown-key check exists to prevent."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"python": {"packageManager": "npm"}}}))
    assert "packageManager" in str(e.value)


# --- testCommand ---------------------------------------------------------


def test_test_command_preserved_as_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"testCommand": ["turbo", "run", "test"]}}
    }))
    assert cfg.stacks["node"].test_command == ("turbo", "run", "test")


def test_test_command_absent_is_none(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].test_command is None


def test_test_command_applies_to_python_too(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"testCommand": ["pytest", "-q"]}}
    }))
    assert cfg.stacks["python"].test_command == ("pytest", "-q")


def test_test_command_empty_list_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": []}}}))
    assert "testCommand" in str(e.value)


def test_test_command_not_a_list_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": "npm test"}}}))
    assert "testCommand" in str(e.value)


def test_test_command_non_string_element_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": ["npm", 7]}}}))
    assert "testCommand" in str(e.value)


def test_test_command_empty_string_element_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": ["npm", ""]}}}))
    assert "testCommand" in str(e.value)


def test_test_command_with_actions_expression_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"testCommand": ["echo", "${{ secrets.TOKEN }}"]}}
        }))
    msg = str(e.value)
    assert "testCommand" in msg
    assert "${{" in msg


def test_test_command_with_newline_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"testCommand": ["npm", "test\nrm -rf /"]}}
        }))
    assert "testCommand" in str(e.value)


@pytest.mark.parametrize("bad_break", [
    "a\rb",         # bare carriage return -- a line break to a YAML parser
    "trailing\n",   # a trailing newline that len(splitlines()) > 1 would miss
    "a\u2028b",      # Unicode LINE SEPARATOR
    "a\u2029b",      # Unicode PARAGRAPH SEPARATOR
], ids=["cr", "trailing-lf", "u2028", "u2029"])
def test_test_command_any_line_break_rejected(tmp_path, bad_break):
    # Not just \n: any line break is refused, because a bare \r (or a Unicode
    # separator) is a line break to a YAML parser and would let the rendered
    # run: command differ from what was written.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"testCommand": ["npm", bad_break]}}
        }))
    assert "testCommand" in str(e.value)


def test_shell_metacharacters_are_allowed_and_kept_literal(tmp_path):
    # A ; or a quote is inert once shlex.quote runs at render; the config layer
    # accepts it. Only ${{ and line breaks are refused.
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"testCommand": ["sh", "-c", "echo hi; echo bye"]}}
    }))
    assert cfg.stacks["node"].test_command == ("sh", "-c", "echo hi; echo bye")


# --- services ----------------------------------------------------------


def test_services_resolve_to_tuple_of_resolved_services(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}}}
    }))
    assert cfg.stacks["node"].services == (
        ResolvedService(service_id="postgres", version="16",
                        url_env="TEST_DATABASE_URL"),
    )


def test_services_absent_is_empty_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].services == ()


def test_unknown_service_id_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "cassandra": {"version": "5", "urlEnv": "DB_URL"}}}}}))
    msg = str(e.value)
    assert "cassandra" in msg and "postgres" in msg  # names the bad id and the allowed set


def test_service_missing_version_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"urlEnv": "DB_URL"}}}}}))
    assert "version" in str(e.value)


def test_service_missing_url_env_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16"}}}}}))
    assert "urlEnv" in str(e.value)


@pytest.mark.parametrize("bad_env", ["1DB", "DB URL", "DB-URL", "${{x}}", ""])
def test_bad_url_env_rejected(tmp_path, bad_env):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": bad_env}}}}}))
    assert "urlEnv" in str(e.value)


@pytest.mark.parametrize("bad_version", ["16 rc", "1.0}}", "${{ x }}", "a b"])
def test_bad_service_version_rejected(tmp_path, bad_version):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": bad_version, "urlEnv": "DB_URL"}}}}}))
    assert "version" in str(e.value)


def test_unknown_key_inside_a_service_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "DB_URL", "port": 5432}}}}}))
    assert "port" in str(e.value)


def test_services_not_a_dict_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": ["postgres"]}}}))
    assert "services" in str(e.value)


def test_service_database_threaded_onto_resolved_service(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL",
                         "database": "onelife_test"}}}}
    }))
    assert cfg.stacks["node"].services == (
        ResolvedService(service_id="postgres", version="16",
                        url_env="TEST_DATABASE_URL", database="onelife_test"),
    )


def test_service_database_omitted_is_none(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "DB_URL"}}}}}))
    assert cfg.stacks["node"].services[0].database is None


def test_database_on_a_service_without_one_rejected(tmp_path):
    # redis has no database concept; naming a database for it is a config error,
    # not a silently-ignored setting.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "redis": {"version": "7", "urlEnv": "REDIS_URL",
                      "database": "onelife_test"}}}}}))
    msg = str(e.value)
    assert "database" in msg and "redis" in msg  # names the field and the service


@pytest.mark.parametrize("bad_database", ["one life", "db/name", "on${{x}}", "", "a.b"])
def test_bad_service_database_rejected(tmp_path, bad_database):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "DB_URL",
                         "database": bad_database}}}}}))
    assert "database" in str(e.value)
