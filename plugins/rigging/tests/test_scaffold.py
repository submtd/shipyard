import itertools
import json

import pytest

from rigging import scaffold
from rigging.config import CONFIG_NAME, StackConfig, load_config
from rigging.scaffold import CI_FILES, classify_files, propose_config
from rigging.stacks import NODE_PACKAGE_MANAGERS, REGISTRY, STACK_IDS

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
    "name": (ABSENT, "ci"),
    "stacks": (("python",), ("node",), ("python", "node")),  # required: no ABSENT
    "versions": (ABSENT, {"python": ["3.12"]}, {"node": ["20"]}),
    "pushBranches": (ABSENT, ["main"]),
    "unsupported": (ABSENT, {"python": "no test runner detected"}),
    "packageManagers": (
        ABSENT,
        {"node": "pnpm"},          # valid iff node is in stacks
        {"python": "npm"},         # python has no manager -> ValueError (break #3)
        {"node": ["pnpm"]},        # unhashable manager id -> must be ValueError (break #4)
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


def _all_non_empty_subsets(ids):
    for r in range(1, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_non_empty_subsets(STACK_IDS))


def test_single_stack_proposes_dict_with_defaults():
    cfg = propose_config({"stacks": ("python",)})
    assert cfg["name"] == "ci"
    assert cfg["stacks"] == {"python": {}}


def test_explicit_versions_flow_through(tmp_path):
    cfg = propose_config({
        "stacks": ("python",),
        "versions": {"python": ["3.10", "3.11"]},
    })
    assert cfg["stacks"]["python"] == {"versions": ["3.10", "3.11"]}
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks == {"python": StackConfig(versions=("3.10", "3.11"))}


def test_explicit_versions_only_applied_to_named_stack(tmp_path):
    cfg = propose_config({
        "stacks": ("python", "node"),
        "versions": {"python": ["3.10"]},
    })
    assert cfg["stacks"]["python"] == {"versions": ["3.10"]}
    assert cfg["stacks"]["node"] == {}
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks["python"].versions == ("3.10",)
    assert loaded.stacks["node"].versions == REGISTRY["node"].default_versions


def test_custom_name_flows_through(tmp_path):
    cfg = propose_config({"stacks": ("python",), "name": "my-CI_1"})
    assert cfg["name"] == "my-CI_1"
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.name == "my-CI_1"


@pytest.mark.parametrize(
    "bad_version",
    ["3.10 beta", "3.9\n", "a}}b"],
    ids=["space", "newline", "braces"],
)
def test_bad_version_string_raises_value_error_naming_field(bad_version):
    with pytest.raises(ValueError, match="versions"):
        propose_config({
            "stacks": ("python",),
            "versions": {"python": [bad_version]},
        })


def test_non_string_version_entry_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="versions"):
        propose_config({
            "stacks": ("python",),
            "versions": {"python": [3, 10]},
        })


def test_valid_explicit_version_still_round_trips(tmp_path):
    cfg = propose_config({
        "stacks": ("python",),
        "versions": {"python": ["3.10"]},
    })
    assert cfg["stacks"]["python"] == {"versions": ["3.10"]}
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks["python"].versions == ("3.10",)


def test_versions_not_a_dict_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="versions"):
        propose_config({"stacks": ("python",), "versions": ["3.10"]})


def test_ci_files_rejects_path_traversal_name():
    with pytest.raises(ValueError, match="name"):
        CI_FILES("../evil")


def test_ci_files_returns_two_expected_paths_for_valid_name():
    assert CI_FILES("ci") == [".rigging.json", ".github/workflows/ci.yml"]


def test_unknown_stack_id_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": ("ruby",)})


def test_empty_stacks_list_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": ()})


def test_missing_stacks_key_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({})


@pytest.mark.parametrize("bad_name", ["../evil", "a/b", "a.b", "", 5])
def test_bad_name_raises_value_error_naming_field(bad_name):
    with pytest.raises(ValueError, match="name"):
        propose_config({"stacks": ("python",), "name": bad_name})


def test_ci_files_returns_config_and_workflow_paths():
    assert CI_FILES("ci") == [".rigging.json", ".github/workflows/ci.yml"]


def test_ci_files_uses_provided_name_in_workflow_path():
    assert CI_FILES("my-CI_1") == [".rigging.json", ".github/workflows/my-CI_1.yml"]


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / ".rigging.json").write_text("{}")
    result = classify_files(tmp_path, CI_FILES("ci"))
    assert result == {
        ".rigging.json": "present",
        ".github/workflows/ci.yml": "absent",
    }


def test_classify_files_handles_nested_workflow_path(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("x")
    result = classify_files(tmp_path, CI_FILES("ci"))
    assert result == {
        ".rigging.json": "absent",
        ".github/workflows/ci.yml": "present",
    }


# --- pushBranches -------------------------------------------------------

BASE_SIGNALS = {"stacks": ["python"]}


def test_propose_config_omits_push_branches_when_not_signalled():
    """Absent means "use the default". Writing the default out explicitly
    would freeze today's choice into every scaffolded repo, so a later change
    of default would reach none of them."""
    assert "pushBranches" not in propose_config(BASE_SIGNALS)


def test_propose_config_carries_push_branches_through(tmp_path):
    cfg = propose_config(dict(BASE_SIGNALS, pushBranches=["master"]))
    assert cfg["pushBranches"] == ["master"]
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).push_branches == ("master",)


@pytest.mark.parametrize("bad", [[], "main", ["a b"], [1], ["-x"], ["a${{x}}"]])
def test_propose_config_rejects_unrenderable_push_branches(bad):
    """Rejected here as well as in load_config: propose_config's contract is
    that valid signals in produce a config load_config accepts, so a value
    it would reject must not be proposable."""
    with pytest.raises(ValueError):
        propose_config(dict(BASE_SIGNALS, pushBranches=bad))


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


# --- the refusal is load-bearing, not advisory (issue #24) -----------------
#
# The init skill is prose, and prose can be skimmed or overridden. Routing the
# detected reasons back through propose_config makes the refusal happen at the
# one place that decides what goes on disk.

PNPM_REASON = "found pnpm-lock.yaml at the repo root ... npm ci cannot work here."


def test_unsupported_stack_raises_naming_stack_and_reason():
    with pytest.raises(ValueError) as excinfo:
        propose_config({"stacks": ["node"], "unsupported": {"node": PNPM_REASON}})
    message = str(excinfo.value)
    assert "node" in message
    assert PNPM_REASON in message


def test_unsupported_entry_for_a_stack_not_being_proposed_is_ignored():
    """Polyglot repo, python only: node is unsupported but not asked for, so
    the python scaffold proceeds untouched."""
    cfg = propose_config({"stacks": ["python"], "unsupported": {"node": PNPM_REASON}})
    assert cfg == {"name": "ci", "stacks": {"python": {}}}


def test_absent_unsupported_signal_is_byte_identical_to_before():
    assert propose_config({"stacks": ["python", "node"]}) == propose_config(
        {"stacks": ["python", "node"], "unsupported": {}}
    )


def test_empty_unsupported_signal_changes_nothing():
    cfg = propose_config({"stacks": ["node"], "unsupported": {}})
    assert cfg == {"name": "ci", "stacks": {"node": {}}}


@pytest.mark.parametrize("bad", ["node", ["node"], 5])
def test_unsupported_signal_must_be_a_dict(bad):
    with pytest.raises(ValueError, match="unsupported"):
        propose_config({"stacks": ["python"], "unsupported": bad})


@pytest.mark.parametrize("bad", [{"node": ""}, {"node": 5}, {5: "why"}])
def test_unsupported_entries_must_map_id_to_non_empty_reason(bad):
    with pytest.raises(ValueError, match="unsupported"):
        propose_config({"stacks": ["python"], "unsupported": bad})


def test_unsupported_is_an_allowed_signal_key():
    from rigging.scaffold import SIGNAL_KEYS
    assert "unsupported" in SIGNAL_KEYS


def test_end_to_end_pnpm_repo_is_refused(tmp_path):
    """The wiring the skill performs: detect, then propose with the reasons."""
    from rigging.detect import detect_stacks, unsupported_reasons

    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    stacks_found = detect_stacks(tmp_path)
    reasons = unsupported_reasons(tmp_path)
    with pytest.raises(ValueError) as excinfo:
        propose_config({"stacks": list(stacks_found), "unsupported": reasons})
    assert "pnpm" in str(excinfo.value)


def test_end_to_end_polyglot_pnpm_repo_scaffolds_python_only(tmp_path):
    from rigging.detect import unsupported_reasons

    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    reasons = unsupported_reasons(tmp_path)
    cfg = propose_config({"stacks": ["python"], "unsupported": reasons})
    assert cfg["stacks"] == {"python": {}}


def test_package_managers_signal_reaches_the_config(tmp_path):
    from rigging.config import load_config

    cfg = propose_config({"stacks": ["node"],
                          "packageManagers": {"node": "pnpm"}})
    assert cfg["stacks"]["node"]["packageManager"] == "pnpm"
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).stacks["node"].package_manager == "pnpm"


def test_absent_package_managers_signal_omits_the_key():
    assert propose_config({"stacks": ["node"]})["stacks"]["node"] == {}


def test_unknown_manager_in_the_signal_is_rejected():
    with pytest.raises(ValueError, match="packageManagers"):
        propose_config({"stacks": ["node"], "packageManagers": {"node": "npm7"}})


def test_manager_for_a_stack_not_being_proposed_is_rejected():
    """A signal naming a stack that is not in `stacks` is a caller mistake,
    and dropping it silently would leave nothing on disk to notice by."""
    with pytest.raises(ValueError, match="packageManagers"):
        propose_config({"stacks": ["python"], "packageManagers": {"node": "pnpm"}})


def test_manager_for_a_stack_with_no_manager_concept_is_rejected():
    """`config._valid_package_manager` refuses `packageManager` for any
    stack but node. propose_config must refuse it too, before it ever
    reaches disk -- otherwise it emits a `.rigging.json` that
    `load_config` rejects, and the init skill has already written the file
    to disk by the time that surfaces."""
    with pytest.raises(ValueError, match="packageManagers"):
        propose_config({
            "stacks": ["python", "node"],
            "packageManagers": {"python": "npm", "node": "pnpm"},
        })


def test_package_managers_signal_round_trips_through_load_config(tmp_path):
    """The one non-negotiable guarantee (see the subset round-trip test
    above) exercised WITH the packageManagers signal set -- the existing
    round-trip test never set this signal, which is why a stack with no
    manager concept could reach load_config unrejected."""
    cfg = propose_config({
        "stacks": ["python", "node"],
        "packageManagers": {"node": "yarn1"},
    })
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)  # must not raise
    assert loaded.stacks["node"].package_manager == "yarn1"
    assert loaded.stacks["python"].package_manager is None
