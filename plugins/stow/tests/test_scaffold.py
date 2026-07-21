import itertools
import json

import pytest

from stow.config import load_config
from stow.scaffold import MANAGED_FILES, classify_files, desired_sections, propose_config
from stow.stacks import BASE, REGISTRY, STACK_IDS


def _all_subsets(ids):
    for r in range(0, len(ids) + 1):
        for combo in itertools.combinations(ids, r):
            yield combo


ALL_SUBSETS = list(_all_subsets(STACK_IDS))


def test_managed_files():
    assert MANAGED_FILES == [".gitignore"]


def test_single_stack_proposes_expected_dict():
    cfg = propose_config({"stacks": ["python"]})
    assert cfg == {"stacks": {"python": {}}}


def test_empty_stacks_list_proposes_base_only_dict():
    cfg = propose_config({"stacks": []})
    assert cfg == {"stacks": {}}


@pytest.mark.parametrize("subset", ALL_SUBSETS, ids=lambda s: "-".join(s) or "empty")
def test_every_subset_round_trips_through_load_config(tmp_path, subset):
    # The one non-negotiable guarantee: scaffold can never write a
    # .stow.json that stow itself would reject -- including the
    # base-only (empty stacks) case.
    cfg = propose_config({"stacks": subset})
    (tmp_path / ".stow.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)  # must not raise
    assert loaded is not None
    assert set(loaded.stacks.keys()) == set(subset)
    for stack_id in subset:
        assert loaded.stacks[stack_id] == {}


def test_unknown_stack_id_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": ["ruby"]})


def test_base_as_stack_id_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": ["base"]})


def test_missing_stacks_key_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({})


def test_stacks_not_a_list_raises_value_error_naming_field():
    with pytest.raises(ValueError, match="stacks"):
        propose_config({"stacks": "python"})


def test_desired_sections_base_only_for_empty_config(tmp_path):
    (tmp_path / ".stow.json").write_text(json.dumps({"stacks": {}}))
    config = load_config(tmp_path)
    assert desired_sections(config) == [BASE]


def test_desired_sections_returns_base_first_then_registry_order(tmp_path):
    (tmp_path / ".stow.json").write_text(
        json.dumps({"stacks": {"node": {}, "python": {}}})
    )
    config = load_config(tmp_path)
    assert desired_sections(config) == [BASE, REGISTRY["node"], REGISTRY["python"]]


def test_desired_sections_follows_config_key_order():
    class FakeConfig:
        stacks = {"python": {}, "node": {}}

    assert desired_sections(FakeConfig()) == [BASE, REGISTRY["python"], REGISTRY["node"]]


def test_classify_files_absent(tmp_path):
    result = classify_files(tmp_path, MANAGED_FILES)
    assert result == {".gitignore": "absent"}


def test_classify_files_present(tmp_path):
    (tmp_path / ".gitignore").write_text("")
    result = classify_files(tmp_path, MANAGED_FILES)
    assert result == {".gitignore": "present"}


def test_classify_files_handles_arbitrary_candidates(tmp_path):
    (tmp_path / ".stow.json").write_text("{}")
    result = classify_files(tmp_path, [".stow.json", ".gitignore"])
    assert result == {".stow.json": "present", ".gitignore": "absent"}
