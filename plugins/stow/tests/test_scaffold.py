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
    # Keys are written in NON-registry order (node before python) so that
    # asserting registry order below actually proves composition ignores
    # .stow.json key order -- a config-key-order implementation would
    # produce [BASE, node, python] here, not [BASE, python, node].
    (tmp_path / ".stow.json").write_text(
        json.dumps({"stacks": {"node": {}, "python": {}}})
    )
    config = load_config(tmp_path)
    assert desired_sections(config) == [BASE, REGISTRY["python"], REGISTRY["node"]]


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


def test_desired_sections_on_a_missing_config_says_so():
    """`load_config` returns None when .stow.json is absent, and the skill's
    own one-liner pipes it straight in. That used to surface as a bare
    `AttributeError: 'NoneType' object has no attribute 'stacks'` from two
    frames deep -- true, but it names neither the file nor the fix."""
    with pytest.raises(ValueError) as excinfo:
        desired_sections(None)
    assert ".stow.json" in str(excinfo.value)
