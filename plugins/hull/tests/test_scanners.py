"""Registry tests for hull's secret-scanner specs.

Mirrors rigging/tests/test_stacks.py's shape: registry keys, derived id
tuple, per-spec field checks, and the injection-safety invariant (no run
step embeds `${{`, which would let an attacker-controlled value get
interpolated into a shell command rather than staying confined to `env`).
"""
from __future__ import annotations

import re

import pytest

from hull import scanners
from hull.scanners import REGISTRY, SCANNER_IDS, ScannerSpec, Step

# A pinned action ref: "<anything>@v<digits>" (e.g. "owner/repo@v2") or a
# 40-hex-char full commit SHA after the "@".
_PINNED_REF_RE = re.compile(r".+@v?\d+")
_SHA_RE = re.compile(r"[0-9a-f]{40}")


def test_registry_keys():
    assert tuple(REGISTRY) == ("gitleaks",)


def test_scanner_ids_derived_from_registry():
    assert SCANNER_IDS == tuple(REGISTRY)


def test_scanner_ids_value():
    assert SCANNER_IDS == ("gitleaks",)


@pytest.mark.parametrize("key", ["gitleaks"])
def test_spec_id_matches_registry_key(key):
    assert REGISTRY[key].id == key


def test_gitleaks_action_ref_is_pinned():
    ref = REGISTRY["gitleaks"].action_ref
    sha_suffix = ref.rsplit("@", 1)[-1]
    assert _PINNED_REF_RE.fullmatch(ref) or _SHA_RE.fullmatch(sha_suffix)


def test_gitleaks_action_ref_value():
    assert REGISTRY["gitleaks"].action_ref == "gitleaks/gitleaks-action@v2"


def test_gitleaks_checkout_fetch_depth():
    assert REGISTRY["gitleaks"].checkout_fetch_depth == "0"


def test_gitleaks_env_whitelists_github_token():
    assert REGISTRY["gitleaks"].env == {
        "GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"
    }


def test_registry_has_no_run_steps_with_expression_interpolation():
    """No Step embedded anywhere in the registry may put `${{` into a run
    body -- that's how an attacker-controlled value becomes shell
    injection. Any secret the scanner needs belongs in a step's `env`
    mapping (like gitleaks' GITHUB_TOKEN above), never interpolated
    directly into `run`. ScannerSpec carries no steps yet in this
    increment, so this guards ahead of a later one that adds them."""
    for spec in REGISTRY.values():
        for step in getattr(spec, "steps", ()):
            if step.run is not None:
                assert "${{" not in step.run


def test_scannerspec_is_frozen_dataclass():
    spec = REGISTRY["gitleaks"]
    with pytest.raises(Exception):
        spec.id = "changed"


def test_step_is_frozen_dataclass():
    step = Step(run="echo hi")
    with pytest.raises(Exception):
        step.run = "changed"


def test_step_has_name_uses_with_run_env_fields():
    step = Step(
        name="Scan",
        uses="gitleaks/gitleaks-action@v2",
        with_={"key": "value"},
        run=None,
        env={"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"},
    )
    assert step.name == "Scan"
    assert step.uses == "gitleaks/gitleaks-action@v2"
    assert step.with_ == {"key": "value"}
    assert step.run is None
    assert step.env == {"GITHUB_TOKEN": "${{ secrets.GITHUB_TOKEN }}"}


def test_step_fields_default_to_none():
    step = Step()
    assert step.name is None
    assert step.uses is None
    assert step.with_ is None
    assert step.run is None
    assert step.env is None
