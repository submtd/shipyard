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
    ["#unit"],
    [";unit"],
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
    [";src"],
    ["#src"],
])
def test_invalid_python_path_entries_raise(tmp_path, python_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"stacks": {"python": {"pythonPath": python_path}}}))


def test_leading_hash_test_path_raises(tmp_path):
    # iniconfig treats any line whose first non-space char is "#" as a
    # COMMENT when parsing pytest.ini -- a testPaths entry of "#unit" would
    # render into pytest.ini and then be silently dropped, leaving
    # testpaths empty and pytest scanning the whole tree instead.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"testPaths": ["#unit"]}}}))
    assert "#unit" in str(e.value)


def test_leading_semicolon_python_path_raises(tmp_path):
    # Same failure class as the leading "#" case: iniconfig also treats a
    # leading ";" as a comment marker.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"pythonPath": [";src"]}}}))
    assert ";src" in str(e.value)


def test_hash_not_in_leading_position_is_still_accepted(tmp_path):
    # iniconfig only treats the value as a comment when "#"/";" is the
    # FIRST character of the (stripped) line -- a hash elsewhere in the
    # token is not special to it, so this must remain a valid path.
    cfg = load_config(write(tmp_path, {"stacks": {"python": {"testPaths": ["a#b"]}}}))
    assert cfg.stacks["python"].test_paths == ("a#b",)


def test_plain_tests_path_still_accepted(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {"testPaths": ["tests"]}}}))
    assert cfg.stacks["python"].test_paths == ("tests",)


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


# --- shlex-significant characters ------------------------------------------
#
# pytest shlex-splits addopts, testpaths and pythonpath. An unbalanced quote
# is therefore fatal to the whole run -- not a bad value, an unhandled
# ValueError out of pytest's own config layer, before collection. PATH_RE and
# FLAG_RE were plain \S+, which excluded whitespace but not quotes, so
# ballast could render a pytest.ini that made pytest crash: the precise
# failure ballast exists to prevent.


@pytest.mark.parametrize("bad", ["-k'foo", '-k"foo', "--cov='x", 'a"b'])
def test_quote_in_add_opts_raises(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"addOpts": [bad]}}}))
    assert bad in str(e.value)


@pytest.mark.parametrize("bad", ["te'sts", 'te"sts', "'tests"])
def test_quote_in_test_path_raises(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"testPaths": [bad]}}}))
    assert bad in str(e.value)


def test_quote_in_python_path_raises(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"pythonPath": ["sr'c"]}}}))
    assert "sr'c" in str(e.value)


@pytest.mark.parametrize("bad", ["a\\b", "a`b", "tests$x"])
def test_other_shlex_significant_characters_raise(tmp_path, bad):
    # Backslash, backtick and '$' are all shell-significant to shlex in
    # non-posix mode or to a shell that later re-expands the value. None of
    # them belong in a path pytest is going to tokenize.
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {"testPaths": [bad]}}}))
    # repr, not the raw value: the message interpolates with !r, which
    # doubles the backslash in the "a\b" case.
    assert repr(bad) in str(e.value)


def test_ordinary_flags_and_paths_still_accepted(tmp_path):
    # Don't over-tighten: the common addOpts forms must keep working.
    cfg = load_config(write(tmp_path, {"stacks": {"python": {
        "addOpts": ["-q", "--strict-markers", "--cov=src", "-p", "no:cacheprovider"],
        "testPaths": ["tests", "pkg/tests", "a#b", "a-b_c.d"],
    }}}))
    assert cfg.stacks["python"].add_opts == (
        "-q", "--strict-markers", "--cov=src", "-p", "no:cacheprovider")
    assert cfg.stacks["python"].test_paths == ("tests", "pkg/tests", "a#b", "a-b_c.d")


# --- unknown keys ----------------------------------------------------------
#
# Silently ignoring an unknown key is the worst outcome for a config whose
# whole job is "make pytest collect the right tests": the user believes they
# configured something, ballast discards it, and the symptom (pytest scanning
# the whole tree) shows up far from the cause. The rendered pytest.ini uses
# lowercase names -- testpaths, pythonpath, addopts -- so mirroring those in
# .ballast.json instead of the camelCase keys is the natural mistake.


@pytest.mark.parametrize("typo", ["testPath", "testpaths", "pythonpath", "addopts",
                                  "importmode"])
def test_unknown_per_stack_key_raises_naming_it(tmp_path, typo):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {typo: ["tests"]}}}))
    assert typo in str(e.value)


def test_unknown_top_level_key_raises_naming_it(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"python": {}}, "importMode": "prepend"}))
    assert "importMode" in str(e.value)


def test_all_known_per_stack_keys_together_are_accepted(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {
        "testPaths": ["tests"], "pythonPath": ["src"],
        "importMode": "prepend", "addOpts": ["-q"],
    }}}))
    assert cfg.stacks["python"].import_mode == "prepend"


# --- CI-hostile addOpts ----------------------------------------------------

@pytest.mark.parametrize(
    "flag",
    ["--pdb", "--trace", "--pdbcls", "--lf", "--last-failed",
     "--ff", "--failed-first", "--sw", "--stepwise", "--stepwise-skip"],
)
def test_add_opts_rejects_ci_hostile_flags(tmp_path, flag):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": [flag]}}})
    with pytest.raises(ConfigError) as excinfo:
        load_config(root)
    assert flag in str(excinfo.value)


def test_add_opts_rejects_ci_hostile_flag_with_a_value(tmp_path):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": ["--pdbcls=IPython.terminal.debugger:TerminalPdb"]}}})
    with pytest.raises(ConfigError) as excinfo:
        load_config(root)
    assert "--pdbcls" in str(excinfo.value)


@pytest.mark.parametrize("flag", ["-s", "--capture=no", "-x", "--exitfirst", "-q", "--strict-markers"])
def test_add_opts_still_accepts_defensible_flags(tmp_path, flag):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": [flag]}}})
    config = load_config(root)
    assert flag in config.stacks["python"].add_opts
