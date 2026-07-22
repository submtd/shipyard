import itertools
import json

import pytest

from bosun import scaffold
from bosun.config import CONFIG_NAME, load_config
from bosun.ecosystems import ECOSYSTEM_IDS, INTERVALS
from bosun.scaffold import (DEPENDABOT_FILES, classify_files,
                            keel_integration_branch, propose_config)

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


SIGNAL_SPACE = {
    "ecosystems": ((), ("python",), ("python", "node")),   # githubActions is always added by propose_config
    "intervals": (
        ABSENT,
        {"python": INTERVALS[0]},          # valid ecosystem + valid interval (registry-sourced)
        {"githubActions": INTERVALS[-1]},  # the always-on ecosystem, a different valid interval
        {"bogus": INTERVALS[0]},           # unknown ecosystem id -> ValueError
        {"python": "often"},               # unknown interval -> ValueError
    ),
    "targetBranch": (ABSENT, "develop"),
}

# Ecosystem ids that detect_ecosystems can ever surface (always-off only --
# githubActions is never detected, it's the always-on one propose_config
# adds itself).
DETECTABLE_IDS = tuple(i for i in ECOSYSTEM_IDS if i != "githubActions")


def _all_subsets_incl_empty(ids):
    for r in range(0, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_subsets_incl_empty(DETECTABLE_IDS))


def test_signal_space_covers_every_signal_key():
    # Loud-omission guard: add a key to SIGNAL_KEYS without declaring its
    # samples here and this fails, rather than the round-trip silently
    # skipping the new key.
    assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS


def test_propose_config_round_trips_over_signal_space(tmp_path):
    for index, signals in enumerate(_candidate_signals(SIGNAL_SPACE)):
        _assert_round_trips(tmp_path, signals, index)


def test_no_detected_ecosystems_still_proposes_github_actions():
    cfg = propose_config({"ecosystems": []})
    assert cfg == {"ecosystems": {"githubActions": {}}}


def test_detected_python_includes_both_github_actions_and_python():
    cfg = propose_config({"ecosystems": ["python"]})
    assert cfg == {"ecosystems": {"githubActions": {}, "python": {}}}


def test_explicit_interval_flows_through(tmp_path):
    cfg = propose_config({
        "ecosystems": ["python"],
        "intervals": {"python": "monthly"},
    })
    assert cfg["ecosystems"]["python"] == {"interval": "monthly"}
    assert cfg["ecosystems"]["githubActions"] == {}
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.ecosystems["python"].interval == "monthly"
    assert loaded.ecosystems["githubActions"].interval == "weekly"


def test_explicit_interval_on_always_on_ecosystem_flows_through(tmp_path):
    cfg = propose_config({
        "ecosystems": [],
        "intervals": {"githubActions": "daily"},
    })
    assert cfg == {"ecosystems": {"githubActions": {"interval": "daily"}}}
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.ecosystems["githubActions"].interval == "daily"


@pytest.mark.parametrize("interval", INTERVALS)
def test_every_valid_interval_accepted(interval):
    cfg = propose_config({
        "ecosystems": ["python"],
        "intervals": {"python": interval},
    })
    assert cfg["ecosystems"]["python"] == {"interval": interval}


def test_unknown_ecosystem_id_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="ecosystems"):
        propose_config({"ecosystems": ["ruby"]})


def test_bad_interval_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="interval"):
        propose_config({
            "ecosystems": ["python"],
            "intervals": {"python": "hourly"},
        })


def test_invalid_interval_on_non_emitted_ecosystem_still_raises():
    # 'python' is neither always-on nor detected, so it's never emitted --
    # but the bad interval must still be caught, per the module docstring
    # and SKILL.md's "every signal is validated" guarantee.
    with pytest.raises(ValueError, match="interval"):
        propose_config({"ecosystems": [], "intervals": {"python": "hourly"}})


def test_typo_d_intervals_key_raises_unknown_ecosystem_error():
    # 'pyton' is not a real ecosystem id -- a typo like this must be
    # caught loudly, not silently dropped with python falling back to its
    # default interval.
    with pytest.raises(ValueError, match="intervals"):
        propose_config({"ecosystems": ["python"], "intervals": {"pyton": "daily"}})


def test_unknown_ecosystem_key_in_intervals_raises():
    with pytest.raises(ValueError, match="intervals"):
        propose_config({"ecosystems": [], "intervals": {"ruby": "weekly"}})


def test_valid_interval_on_emitted_ecosystem_still_works():
    cfg = propose_config({
        "ecosystems": ["python"],
        "intervals": {"python": "daily"},
    })
    assert cfg == {
        "ecosystems": {
            "githubActions": {},
            "python": {"interval": "daily"},
        }
    }


def test_missing_ecosystems_key_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="ecosystems"):
        propose_config({})


def test_ecosystems_not_a_list_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="ecosystems"):
        propose_config({"ecosystems": "python"})


def test_intervals_not_a_dict_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="intervals"):
        propose_config({"ecosystems": ["python"], "intervals": ["monthly"]})


def test_dependabot_files_returns_expected_paths():
    assert DEPENDABOT_FILES() == [".bosun.json", ".github/dependabot.yml"]


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / ".bosun.json").write_text("{}")
    result = classify_files(tmp_path, DEPENDABOT_FILES())
    assert result == {
        ".bosun.json": "present",
        ".github/dependabot.yml": "absent",
    }


def test_classify_files_handles_nested_dependabot_path(tmp_path):
    github_dir = tmp_path / ".github"
    github_dir.mkdir()
    (github_dir / "dependabot.yml").write_text("version: 2\n")
    result = classify_files(tmp_path, DEPENDABOT_FILES())
    assert result == {
        ".bosun.json": "absent",
        ".github/dependabot.yml": "present",
    }


def test_classify_files_both_absent(tmp_path):
    result = classify_files(tmp_path, DEPENDABOT_FILES())
    assert result == {
        ".bosun.json": "absent",
        ".github/dependabot.yml": "absent",
    }


# --- propose_config key order --------------------------------------------
#
# build_plan and render are both order-defended (their key-order tests fail
# under a set-iterating mutation). propose_config was not, and it writes the
# *other* committed artifact: .bosun.json. Its stability came only from
# iterating REGISTRY, which nothing pinned -- every assertion compared
# dicts with ==, which ignores key order, so a set-iterating refactor kept
# the whole suite green while making the written file vary per run.


def test_proposed_ecosystem_order_is_registry_order_not_input_order():
    cfg = propose_config({"ecosystems": ["python", "node"]})
    assert list(cfg["ecosystems"]) == ["githubActions", "python", "node"]


def test_proposed_order_is_independent_of_input_order():
    forward = propose_config({"ecosystems": ["python", "node"]})
    reversed_ = propose_config({"ecosystems": ["node", "python"]})
    assert list(forward["ecosystems"]) == list(reversed_["ecosystems"])


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
        propose_config(dict({'ecosystems': ['python']}, notASignal="x"))
    assert "notASignal" in str(excinfo.value)


def test_a_near_miss_of_a_real_signal_is_rejected():
    """The dangerous case is a typo of a key that exists: it looks configured
    and silently isn't."""
    with pytest.raises(ValueError):
        propose_config(dict({'ecosystems': ['python']}, stack=["python"]))


# --- targetBranch and keel_integration_branch -------------------------------


def test_target_branch_signal_is_emitted_and_round_trips(tmp_path):
    cfg = propose_config({"ecosystems": ["node"], "targetBranch": "develop"})
    assert cfg["targetBranch"] == "develop"
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).target_branch == "develop"


def test_absent_target_branch_signal_omits_the_key():
    # Omitted rather than written out as the current default, so a repo
    # scaffolded today does not have one topology's answer frozen into it.
    assert "targetBranch" not in propose_config({"ecosystems": []})


@pytest.mark.parametrize("bad", ["", "-develop", "a b", "x\ny", 5, ["develop"]])
def test_malformed_target_branch_signal_raises_before_anything_is_returned(bad):
    with pytest.raises(ValueError) as e:
        propose_config({"ecosystems": [], "targetBranch": bad})
    assert "targetBranch" in str(e.value)


def test_unknown_signal_key_still_rejected():
    with pytest.raises(ValueError):
        propose_config({"ecosystems": [], "target_branch": "develop"})


def test_keel_integration_branch_absent_file_is_none(tmp_path):
    assert keel_integration_branch(tmp_path) is None


def test_keel_integration_branch_reads_gitflow_integration(tmp_path):
    (tmp_path / ".keel.json").write_text(json.dumps({
        "topology": "gitflow",
        "branches": {"production": "main", "integration": "develop"},
    }))
    assert keel_integration_branch(tmp_path) == "develop"


def test_keel_integration_branch_defaults_to_develop_under_gitflow(tmp_path):
    # keel's own default when branches.integration is absent, and keel's own
    # default topology when the key is absent -- both mirrored here.
    (tmp_path / ".keel.json").write_text(json.dumps({"branches": {}}))
    assert keel_integration_branch(tmp_path) == "develop"


def test_keel_integration_branch_is_none_under_trunk(tmp_path):
    # Correct, not a gap: under trunk the integration branch IS the
    # repository default branch, so the right output has no target-branch.
    (tmp_path / ".keel.json").write_text(json.dumps({
        "topology": "trunk", "branches": {"production": "main"},
    }))
    assert keel_integration_branch(tmp_path) is None


@pytest.mark.parametrize("body", [
    "{not json",
    json.dumps(["not", "an", "object"]),
    json.dumps({"branches": {"integration": 5}}),
    json.dumps({"branches": {"integration": "bad branch"}}),
    json.dumps({"branches": "not-an-object"}),
])
def test_keel_integration_branch_degrades_quietly_on_unusable_keel_json(tmp_path, body):
    # A convenience, never a validator: keel's own loader is the authority
    # on whether .keel.json is sound. Returning None here means "no answer
    # from keel", and the caller falls back to asking the user.
    (tmp_path / ".keel.json").write_text(body)
    assert keel_integration_branch(tmp_path) is None


def test_keel_integration_branch_result_is_accepted_as_a_signal(tmp_path):
    # The whole point of the helper: whatever it returns must be directly
    # usable as propose_config's targetBranch signal.
    (tmp_path / ".keel.json").write_text(json.dumps({
        "topology": "gitflow", "branches": {"integration": "develop"},
    }))
    branch = keel_integration_branch(tmp_path)
    cfg = propose_config({"ecosystems": [], "targetBranch": branch})
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).target_branch == "develop"
