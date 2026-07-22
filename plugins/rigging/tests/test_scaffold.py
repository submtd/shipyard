import itertools
import json

import pytest

from rigging.config import StackConfig, load_config
from rigging.scaffold import CI_FILES, classify_files, propose_config
from rigging.stacks import REGISTRY, STACK_IDS


def _all_non_empty_subsets(ids):
    for r in range(1, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_non_empty_subsets(STACK_IDS))


def test_single_stack_proposes_dict_with_defaults():
    cfg = propose_config({"stacks": ("python",)})
    assert cfg["name"] == "ci"
    assert cfg["stacks"] == {"python": {}}


@pytest.mark.parametrize("subset", ALL_SUBSETS, ids=lambda s: "-".join(s))
def test_every_non_empty_subset_round_trips_through_load_config(tmp_path, subset):
    # The one non-negotiable guarantee: init can never write a .rigging.json
    # that rigging itself would reject.
    cfg = propose_config({"stacks": subset})
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)  # must not raise
    assert loaded is not None
    assert loaded.name == "ci"
    assert set(loaded.stacks.keys()) == set(subset)
    for stack_id in subset:
        assert loaded.stacks[stack_id].versions == REGISTRY[stack_id].default_versions


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
