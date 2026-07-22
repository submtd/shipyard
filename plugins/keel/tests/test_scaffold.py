import itertools
import json
from pathlib import Path

import pytest

from keel import scaffold
from keel.scaffold import propose_config, classify_files
from keel.config import CONFIG_NAME, load_config, ConfigError, CONTRIBUTIONS, REVIEW_POLICIES


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
    "has_develop": (True, False),                # required: no ABSENT (propose_config does signals["has_develop"])
    "production": (ABSENT, "main"),
    "integration": (ABSENT, "develop"),          # only consumed under gitflow (has_develop True)
    "contributions": (ABSENT,) + CONTRIBUTIONS,
    "review_policy": (ABSENT,) + REVIEW_POLICIES,
    "require_changelog": (ABSENT, True, False),
}


def test_signal_space_covers_every_signal_key():
    # Loud-omission guard: add a key to SIGNAL_KEYS without declaring its
    # samples here and this fails, rather than the round-trip silently
    # skipping the new key.
    assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS


def test_propose_config_round_trips_over_signal_space(tmp_path):
    for index, signals in enumerate(_candidate_signals(SIGNAL_SPACE)):
        _assert_round_trips(tmp_path, signals, index)


def test_no_develop_proposes_trunk():
    cfg = propose_config({"has_develop": False})
    assert cfg["topology"] == "trunk"
    assert cfg["branches"] == {"production": "main"}
    assert "integration" not in cfg["branches"]


def test_develop_proposes_gitflow_with_integration():
    cfg = propose_config({"has_develop": True})
    assert cfg["topology"] == "gitflow"
    assert cfg["branches"] == {"production": "main", "integration": "develop"}


def test_signals_flow_through():
    cfg = propose_config({
        "has_develop": False,
        "contributions": "fork",
        "review_policy": "approval",
        "require_changelog": False,
    })
    assert cfg["contributions"] == "fork"
    assert cfg["reviewPolicy"] == "approval"
    assert cfg["requireChangelog"] is False


def test_defaults_when_signals_absent():
    cfg = propose_config({"has_develop": False})
    assert cfg["contributions"] == "both"
    assert cfg["reviewPolicy"] == "review"
    assert cfg["requireChangelog"] is True


def test_production_signal_overrides_default():
    cfg = propose_config({"has_develop": False, "production": "master"})
    assert cfg["branches"] == {"production": "master"}


def test_production_signal_defaults_to_main():
    cfg = propose_config({"has_develop": False})
    assert cfg["branches"]["production"] == "main"


def test_integration_signal_overrides_default():
    cfg = propose_config({"has_develop": True, "integration": "trunk-dev"})
    assert cfg["branches"]["integration"] == "trunk-dev"


def test_integration_signal_defaults_to_develop():
    cfg = propose_config({"has_develop": True})
    assert cfg["branches"]["integration"] == "develop"


@pytest.mark.parametrize("bad_signals,bad_field", [
    ({"has_develop": False, "review_policy": "required"}, "review_policy"),
    ({"has_develop": False, "contributions": "nobody"}, "contributions"),
    ({"has_develop": False, "require_changelog": "false"}, "require_changelog"),
    ({"has_develop": False, "production": ""}, "production"),
    ({"has_develop": True, "integration": ""}, "integration"),
])
def test_invalid_signals_raise_value_error(bad_signals, bad_field):
    with pytest.raises(ValueError, match=bad_field):
        propose_config(bad_signals)


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / "LICENSE").write_text("MIT")
    result = classify_files(tmp_path, ["LICENSE", "CHANGELOG.md", ".keel.json"])
    assert result == {"LICENSE": "present", "CHANGELOG.md": "absent",
                      ".keel.json": "absent"}


def test_classify_files_handles_nested_paths(tmp_path):
    nested = tmp_path / ".github" / "ISSUE_TEMPLATE"
    nested.mkdir(parents=True)
    (nested / "bug_report.md").write_text("x")
    result = classify_files(tmp_path, [".github/ISSUE_TEMPLATE/bug_report.md",
                                       ".github/PULL_REQUEST_TEMPLATE.md"])
    assert result == {".github/ISSUE_TEMPLATE/bug_report.md": "present",
                      ".github/PULL_REQUEST_TEMPLATE.md": "absent"}


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
        propose_config(dict({'has_develop': True}, notASignal="x"))
    assert "notASignal" in str(excinfo.value)


def test_a_near_miss_of_a_real_signal_is_rejected():
    """The dangerous case is a typo of a key that exists: it looks configured
    and silently isn't."""
    with pytest.raises(ValueError):
        propose_config(dict({'has_develop': True}, stack=["python"]))
