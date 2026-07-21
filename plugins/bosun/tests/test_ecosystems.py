"""Registry tests for bosun's ecosystem specs.

Mirrors rigging/tests/test_stacks.py and hull/tests/test_scanners.py's
shape: registry keys, derived id tuple, per-spec field checks, and the
frozen-dataclass invariant.
"""
from __future__ import annotations

import pytest

from bosun import ecosystems
from bosun.ecosystems import ECOSYSTEM_IDS, INTERVALS, REGISTRY, EcosystemSpec


def test_registry_keys():
    assert tuple(REGISTRY) == ("githubActions", "python", "node")


def test_ecosystem_ids_derived_from_registry():
    assert ECOSYSTEM_IDS == tuple(REGISTRY)


def test_ecosystem_ids_value():
    assert ECOSYSTEM_IDS == ("githubActions", "python", "node")


@pytest.mark.parametrize("key", ["githubActions", "python", "node"])
def test_spec_id_matches_registry_key(key):
    assert REGISTRY[key].id == key


def test_github_actions_spec_contents():
    spec = REGISTRY["githubActions"]
    assert spec.package_ecosystem == "github-actions"
    assert spec.detect_files == ()
    assert spec.always_on is True


def test_python_spec_contents():
    spec = REGISTRY["python"]
    assert spec.package_ecosystem == "pip"
    assert spec.detect_files == (
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "requirements.txt",
    )
    assert spec.always_on is False


def test_node_spec_contents():
    spec = REGISTRY["node"]
    assert spec.package_ecosystem == "npm"
    assert spec.detect_files == ("package.json",)
    assert spec.always_on is False


def test_python_and_node_detect_files_match_riggings_stack_markers():
    """bosun's python/node detect markers are the same files rigging uses
    to detect those stacks -- the two plugins must agree on what "this
    repo has Python/Node" means."""
    from rigging.stacks import REGISTRY as STACK_REGISTRY

    assert REGISTRY["python"].detect_files == STACK_REGISTRY["python"].detect_files
    assert REGISTRY["node"].detect_files == STACK_REGISTRY["node"].detect_files


def test_intervals_value():
    """Every `schedule.interval` GitHub accepts without extra keys. The
    enum stopped at monthly, so a valid `"quarterly"` in .bosun.json was
    rejected by bosun's own config loader -- a false error about a file
    GitHub would have accepted. `cron` is deliberately absent: it is the one
    value that requires a companion `schedule.cronjob` key, so admitting it
    to this enum alone would render a dependabot.yml GitHub rejects."""
    assert INTERVALS == (
        "daily", "weekly", "monthly", "quarterly", "semiannually", "yearly")
    assert "cron" not in INTERVALS


def test_ecosystemspec_is_frozen_dataclass():
    spec = REGISTRY["python"]
    with pytest.raises(Exception):
        spec.id = "changed"
