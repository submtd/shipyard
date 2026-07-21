import itertools
import json

import pytest

from rigging.config import load_config
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
        assert loaded.stacks[stack_id] == REGISTRY[stack_id].default_versions


def test_explicit_versions_flow_through(tmp_path):
    cfg = propose_config({
        "stacks": ("python",),
        "versions": {"python": ["3.10", "3.11"]},
    })
    assert cfg["stacks"]["python"] == {"versions": ["3.10", "3.11"]}
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks == {"python": ("3.10", "3.11")}


def test_explicit_versions_only_applied_to_named_stack(tmp_path):
    cfg = propose_config({
        "stacks": ("python", "node"),
        "versions": {"python": ["3.10"]},
    })
    assert cfg["stacks"]["python"] == {"versions": ["3.10"]}
    assert cfg["stacks"]["node"] == {}
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded.stacks["python"] == ("3.10",)
    assert loaded.stacks["node"] == REGISTRY["node"].default_versions


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
    assert loaded.stacks["python"] == ("3.10",)


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
