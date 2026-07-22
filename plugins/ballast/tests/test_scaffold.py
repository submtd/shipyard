import itertools
import json

import pytest

from ballast import scaffold
from ballast.config import CONFIG_NAME, load_config
from ballast.scaffold import CONFIG_FILES, IMPORT_MODES, classify_files, propose_config
from ballast.stacks import REGISTRY, STACK_IDS

ABSENT = object()


def _candidate_signals(space):
    """Every combination of one sample per signal key. A key whose chosen
    sample is ABSENT is omitted from the produced dict entirely."""
    keys = sorted(space)
    for combo in itertools.product(*(space[k] for k in keys)):
        yield {k: v for k, v in zip(keys, combo) if v is not ABSENT}


def _assert_round_trips(tmp_path, signals, index):
    """The two-outcome contract for one signal combo."""
    try:
        cfg = propose_config(signals)
    except ValueError:
        return  # a deliberate rejection is an allowed outcome
    except Exception as exc:  # noqa: BLE001 - the point is to catch the wrong type
        pytest.fail(
            f"propose_config({signals!r}) raised {type(exc).__name__}, not "
            f"ValueError: {exc}"
        )
    sub = tmp_path / str(index)
    sub.mkdir()
    (sub / CONFIG_NAME).write_text(json.dumps(cfg))
    loaded = load_config(sub)  # must not raise
    assert loaded is not None, (
        f"load_config returned None for {signals!r} -> {cfg!r}"
    )


def _all_non_empty_subsets(ids):
    for r in range(1, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_non_empty_subsets(STACK_IDS))

SIGNAL_SPACE = {
    "stacks": (("python",),),   # required; python is the only registered stack
    "configs": (
        ABSENT,
        {"python": {"testPaths": ["tests"]}},
        {"python": {"pythonPath": []}},              # empty pythonPath is allowed
        {"python": {"importMode": IMPORT_MODES[0]}}, # a valid mode, sourced from the registry
        {"python": {"addOpts": ["-q"]}},
        {"python": {"testPaths": []}},               # empty testPaths -> ValueError
        {"python": {"importMode": "bogus"}},         # invalid mode -> ValueError
        {"python": ["not-a-dict"]},                  # override not a dict -> ValueError
    ),
}


def test_signal_space_covers_every_signal_key():
    # Loud-omission guard: add a key to SIGNAL_KEYS without declaring its
    # samples here and this fails, rather than the round-trip silently
    # skipping the new key.
    assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS


def test_propose_config_round_trips_over_signal_space(tmp_path):
    for index, signals in enumerate(_candidate_signals(SIGNAL_SPACE)):
        _assert_round_trips(tmp_path, signals, index)


def test_config_files_value():
    assert CONFIG_FILES == [".ballast.json", "pytest.ini"]


def test_single_stack_proposes_dict_with_defaults():
    cfg = propose_config({"stacks": ["python"]})
    assert cfg == {"stacks": {"python": {}}}


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


def test_leading_hash_test_path_raises_value_error():
    # propose_config reuses config._valid_path, so an iniconfig comment-char
    # path like "#unit" must already be rejected here too -- confirming the
    # two layers stay in lockstep.
    with pytest.raises(ValueError, match="testPaths"):
        propose_config({
            "stacks": ["python"],
            "configs": {"python": {"testPaths": ["#unit"]}},
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


# --- Unknown signals -------------------------------------------------------
#
# Found by an end-to-end run: a typo'd signal key was silently ignored, so
# the scaffold quietly took a default the user thought they had overridden.
# The config LOADERS were hardened against exactly this in 0.3.0 ("an
# unknown key is an error rather than something to ignore"), but the layer
# above them had the opposite behaviour -- and it is worse here, because
# there is no file left on disk to inspect afterwards.


def test_unknown_signal_key_is_rejected_naming_it():
    with pytest.raises(ValueError) as excinfo:
        propose_config(dict({'stacks': ['python']}, notASignal="x"))
    assert "notASignal" in str(excinfo.value)


def test_a_near_miss_of_a_real_signal_is_rejected():
    """The dangerous case is a typo of a key that exists: it looks configured
    and silently isn't."""
    with pytest.raises(ValueError):
        propose_config(dict({'stacks': ['python']}, stack=["python"]))
