import itertools
import json

import pytest

from bosun.config import load_config
from bosun.ecosystems import ECOSYSTEM_IDS, INTERVALS
from bosun.scaffold import DEPENDABOT_FILES, classify_files, propose_config

# Ecosystem ids that detect_ecosystems can ever surface (always-off only --
# githubActions is never detected, it's the always-on one propose_config
# adds itself).
DETECTABLE_IDS = tuple(i for i in ECOSYSTEM_IDS if i != "githubActions")


def _all_subsets_incl_empty(ids):
    for r in range(0, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_subsets_incl_empty(DETECTABLE_IDS))


def test_no_detected_ecosystems_still_proposes_github_actions():
    cfg = propose_config({"ecosystems": []})
    assert cfg == {"ecosystems": {"githubActions": {}}}


def test_no_detected_ecosystems_round_trips_through_load_config(tmp_path):
    cfg = propose_config({"ecosystems": []})
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert set(loaded.ecosystems.keys()) == {"githubActions"}


def test_detected_python_includes_both_github_actions_and_python():
    cfg = propose_config({"ecosystems": ["python"]})
    assert cfg == {"ecosystems": {"githubActions": {}, "python": {}}}


@pytest.mark.parametrize("subset", ALL_SUBSETS, ids=lambda s: "-".join(s) or "none")
def test_every_subset_round_trips_through_load_config(tmp_path, subset):
    # The one non-negotiable guarantee: init can never write a .bosun.json
    # that bosun itself would reject, and githubActions is always present
    # even when nothing was detected.
    cfg = propose_config({"ecosystems": list(subset)})
    (tmp_path / ".bosun.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert set(loaded.ecosystems.keys()) == {"githubActions", *subset}
    for ecosystem_id in loaded.ecosystems:
        assert loaded.ecosystems[ecosystem_id].interval == "weekly"


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
