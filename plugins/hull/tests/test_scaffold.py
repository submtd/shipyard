"""Tests for hull's scaffold helpers.

Mirrors rigging/tests/test_scaffold.py's shape: propose_config round-trips
through config.load_config, bad fields raise ValueError naming the field,
SECURITY_FILES rejects path-escaping names, classify_files reports
present/absent for both flat and nested candidate paths.
"""
from __future__ import annotations

import json

import pytest

from hull.config import load_config
from hull.scanners import REGISTRY, SCANNER_IDS
from hull.scaffold import (
    SECURITY_FILES,
    check_preconditions,
    classify_files,
    propose_config,
)


def test_propose_config_defaults():
    cfg = propose_config({})
    assert cfg == {"name": "security", "scanner": "gitleaks"}


def test_propose_config_defaults_round_trip_through_load_config(tmp_path):
    cfg = propose_config({})
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert loaded.name == "security"
    assert loaded.scanner == "gitleaks"


def test_propose_config_explicit_signals_round_trip_through_load_config(tmp_path):
    cfg = propose_config({"name": "my-Scan_1", "scanner": "gitleaks"})
    assert cfg == {"name": "my-Scan_1", "scanner": "gitleaks"}
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    loaded = load_config(tmp_path)
    assert loaded is not None
    assert loaded.name == "my-Scan_1"
    assert loaded.scanner == "gitleaks"


@pytest.mark.parametrize("bad_name", ["a/b", "../evil", "${{ github.token }}", "a.b", "", 5])
def test_propose_config_bad_name_raises_value_error_naming_field(bad_name):
    with pytest.raises(ValueError, match="name"):
        propose_config({"name": bad_name})


@pytest.mark.parametrize("bad_scanner", ["semgrep", "", 5])
def test_propose_config_unknown_scanner_raises_value_error_naming_field(bad_scanner):
    with pytest.raises(ValueError, match="scanner"):
        propose_config({"scanner": bad_scanner})


def test_propose_config_scanner_ids_are_all_valid():
    for scanner_id in SCANNER_IDS:
        cfg = propose_config({"scanner": scanner_id})
        assert cfg["scanner"] == scanner_id


def test_security_files_returns_expected_paths_for_valid_name():
    assert SECURITY_FILES("security") == [
        ".hull.json",
        ".github/workflows/security.yml",
    ]


def test_security_files_uses_provided_name_in_workflow_path():
    assert SECURITY_FILES("my-Scan_1") == [
        ".hull.json",
        ".github/workflows/my-Scan_1.yml",
    ]


@pytest.mark.parametrize("bad_name", ["../evil", "a/b", "${{ x }}", "a.b", ""])
def test_security_files_rejects_path_escaping_name(bad_name):
    with pytest.raises(ValueError, match="name"):
        SECURITY_FILES(bad_name)


def test_classify_files_absent_and_present(tmp_path):
    (tmp_path / ".hull.json").write_text("{}")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "present",
        ".github/workflows/security.yml": "absent",
    }


def test_classify_files_handles_nested_workflow_path(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "security.yml").write_text("x")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "absent",
        ".github/workflows/security.yml": "present",
    }


def test_classify_files_both_absent(tmp_path):
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "absent",
        ".github/workflows/security.yml": "absent",
    }


def test_classify_files_both_present(tmp_path):
    (tmp_path / ".hull.json").write_text("{}")
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "security.yml").write_text("x")
    result = classify_files(tmp_path, SECURITY_FILES("security"))
    assert result == {
        ".hull.json": "present",
        ".github/workflows/security.yml": "present",
    }


# --- pushBranches: mirrors rigging/tests/test_scaffold.py ---------------


def test_propose_config_omits_push_branches_when_not_signalled():
    """Absent means "use the default". Writing the default out explicitly
    would freeze today's choice into every scaffolded repo."""
    assert "pushBranches" not in propose_config({})


def test_propose_config_carries_push_branches_through(tmp_path):
    cfg = propose_config({"pushBranches": ["master"]})
    assert cfg["pushBranches"] == ["master"]
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).push_branches == ("master",)


@pytest.mark.parametrize("bad", [[], "main", ["a b"], [1], ["-x"], ["a${{x}}"]])
def test_propose_config_rejects_unrenderable_push_branches(bad):
    with pytest.raises(ValueError):
        propose_config({"pushBranches": bad})


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
        propose_config(dict({}, notASignal="x"))
    assert "notASignal" in str(excinfo.value)


def test_a_near_miss_of_a_real_signal_is_rejected():
    """The dangerous case is a typo of a key that exists: it looks configured
    and silently isn't."""
    with pytest.raises(ValueError):
        propose_config(dict({}, stack=["python"]))


# --- licenseSecret signal --------------------------------------------------


def test_propose_config_omits_license_secret_when_not_signalled():
    assert "licenseSecret" not in propose_config({})


def test_propose_config_carries_license_secret_through(tmp_path):
    cfg = propose_config({"licenseSecret": "GITLEAKS_LICENSE"})
    assert cfg["licenseSecret"] == "GITLEAKS_LICENSE"
    (tmp_path / ".hull.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).license_secret == "GITLEAKS_LICENSE"


@pytest.mark.parametrize("bad", [
    "${{ secrets.X }}", "X }} ${{ y", "MY-LICENSE", "MY.LICENSE",
    "1LICENSE", "", 5, ["GITLEAKS_LICENSE"],
])
def test_propose_config_rejects_unrenderable_license_secret(bad):
    with pytest.raises(ValueError, match="licenseSecret"):
        propose_config({"licenseSecret": bad})


# --- check_preconditions ---------------------------------------------------
#
# Issue #24: hull:init used to write a workflow that CANNOT pass in an
# org-owned repo, with no warning. The guard is pure -- the skill runs
# `gh repo view --json owner -q .owner.type` and passes the answer in -- so
# these tests exercise the whole decision without any I/O at all.


def test_no_blockers_for_a_user_owned_repo():
    result = check_preconditions({"ownerType": "User"})
    assert result.blockers == ()


def test_no_blockers_when_owner_type_is_unknown():
    """A failed lookup (no remote yet, gh unauthenticated, offline) must not
    make hull unusable on a brand-new repo -- which is where it is most
    useful. The advisory channel still carries the caveat."""
    assert check_preconditions({}).blockers == ()
    assert check_preconditions({"ownerType": None}).blockers == ()


def test_organization_without_a_license_secret_is_blocked():
    result = check_preconditions({"ownerType": "Organization"})
    assert len(result.blockers) == 1


def test_blocker_states_cause_exit_code_and_remedy():
    """The message has to survive being pasted into an issue by someone who
    has never read hull's source: cause, the fact that the action exits 1,
    and both remedies."""
    (blocker,) = check_preconditions({"ownerType": "Organization"}).blockers
    assert "Organization" in blocker
    assert "license" in blocker
    assert "exits 1" in blocker
    assert "licenseSecret" in blocker
    assert "GITLEAKS_LICENSE" in blocker
    assert "secret" in blocker
    assert "trufflehog" in blocker


def test_organization_with_a_license_secret_is_clear():
    result = check_preconditions({
        "ownerType": "Organization",
        "licenseSecret": "GITLEAKS_LICENSE",
    })
    assert result.blockers == ()


def test_organization_with_a_licenseless_scanner_is_clear():
    """The blocker is keyed off the SCANNER's license gate, not off the
    owner type alone. Previously staged with a patched registry because no
    licenseless scanner existed; it now exercises the real one."""
    assert check_preconditions({
        "ownerType": "Organization", "scanner": "trufflehog",
    }).blockers == ()


# --- the advisory channel --------------------------------------------------
#
# Deliberately a SEPARATE return channel from blockers: an advisory is
# reported alongside a successful init, a blocker instead of one. Collapsing
# them into one list of strings would leave the skill guessing which is which.


def test_fork_pr_secret_advisory_is_returned_for_a_license_gated_scanner():
    (advisory,) = check_preconditions({"ownerType": "User"}).advisories
    assert "fork" in advisory.lower()
    assert "secret" in advisory
    assert "GITLEAKS_LICENSE" in advisory


def test_fork_pr_advisory_is_still_returned_once_a_license_is_configured():
    """This is the point of it: a configured license fixes the org blocker
    and does nothing for fork PRs, because GitHub withholds secrets there by
    design."""
    result = check_preconditions({
        "ownerType": "Organization",
        "licenseSecret": "GITLEAKS_LICENSE",
    })
    assert result.blockers == ()
    assert len(result.advisories) == 1


def test_advisory_is_not_a_blocker():
    """The distinction is load-bearing: an advisory must never appear in the
    channel the skill refuses to scaffold on."""
    result = check_preconditions({"ownerType": "User"})
    assert result.advisories
    assert result.blockers == ()


def test_fork_pr_advisory_absent_for_a_scanner_with_no_license_gate():
    """The fork-PR advisory is about secrets being withheld from fork runs.
    trufflehog reads no secret, so the caveat does not apply to it."""
    advisories = check_preconditions({
        "ownerType": "User", "scanner": "trufflehog",
    }).advisories
    assert not any("fork" in a.lower() for a in advisories)


def test_preconditions_unpacks_as_blockers_then_advisories():
    blockers, advisories = check_preconditions({"ownerType": "Organization"})
    assert blockers and advisories


# --- check_preconditions rejects unknown signals ---------------------------


def test_check_preconditions_rejects_an_unknown_signal_key():
    with pytest.raises(ValueError) as excinfo:
        check_preconditions({"ownerType": "User", "notASignal": "x"})
    assert "notASignal" in str(excinfo.value)


def test_check_preconditions_rejects_a_near_miss_of_owner_type():
    """The dangerous typo: `owner_type` looks configured, silently isn't, and
    the org guard never runs."""
    with pytest.raises(ValueError):
        check_preconditions({"owner_type": "Organization"})


@pytest.mark.parametrize("near_miss", [
    "organization",     # the likeliest slip: a model lower-casing gh's output
    "ORGANIZATION",
    "Organisation",     # British spelling
    "org",
    "Org",
    "Bot",              # a real GitHub owner type, but not one hull models
    "",
])
def test_check_preconditions_rejects_a_near_miss_of_the_owner_type_VALUE(near_miss):
    """The value deserves the same treatment as the key above, because it has
    the identical consequence. The blocker fires on an exact match against
    "Organization", so any of these would pass an isinstance check, return
    zero blockers, and hand an org-owned repo the very workflow this guard
    exists to refuse -- with nothing on disk afterwards to notice it by."""
    with pytest.raises(ValueError, match="ownerType"):
        check_preconditions({"ownerType": near_miss})


@pytest.mark.parametrize("bad", [5, ["Organization"], {"type": "Organization"}])
def test_check_preconditions_rejects_a_non_string_owner_type(bad):
    """Unhashable values (list, dict) included: the domain check must raise
    ValueError naming the field, not a TypeError out of a set lookup."""
    with pytest.raises(ValueError, match="ownerType"):
        check_preconditions({"ownerType": bad})


def test_owner_type_error_points_at_the_command_that_produces_it():
    """The caller is a skill reading prose, so the message has to say where a
    correct value comes from, not merely that this one was wrong."""
    with pytest.raises(ValueError) as excinfo:
        check_preconditions({"ownerType": "organization"})
    message = str(excinfo.value)
    assert "gh repo view" in message
    assert "Organization" in message


def test_the_org_blocker_and_the_domain_check_share_one_constant():
    """If these ever drift, a value that validates could still fail to trip
    the blocker -- which is precisely the bug being closed here."""
    from hull.scaffold import OWNER_TYPE_ORGANIZATION, OWNER_TYPES

    assert OWNER_TYPE_ORGANIZATION in OWNER_TYPES
    assert check_preconditions({"ownerType": OWNER_TYPE_ORGANIZATION}).blockers


def test_check_preconditions_rejects_a_hostile_license_secret():
    with pytest.raises(ValueError, match="licenseSecret"):
        check_preconditions({"ownerType": "Organization",
                             "licenseSecret": "${{ github.token }}"})


def test_check_preconditions_rejects_an_unknown_scanner():
    with pytest.raises(ValueError, match="scanner"):
        check_preconditions({"ownerType": "User", "scanner": "semgrep"})


def test_propose_config_still_rejects_owner_type():
    """`ownerType` is an observation about the remote, not a setting -- it has
    no home in .hull.json, so propose_config must refuse it rather than drop
    it silently."""
    with pytest.raises(ValueError, match="ownerType"):
        propose_config({"ownerType": "Organization"})


def test_blocker_names_the_licenseless_scanner_concretely():
    """Before #27 the message ended "or choose a scanner with no license
    gate", which named nothing real -- the registry had one entry. The
    remedy is only actionable if it names the scanner to re-run with."""
    (blocker,) = check_preconditions({"ownerType": "Organization"}).blockers
    assert "trufflehog" in blocker


def test_every_remedy_the_blocker_offers_actually_exists():
    """Guards the message against drifting back into naming a scanner that
    was removed from the registry."""
    (blocker,) = check_preconditions({"ownerType": "Organization"}).blockers
    named = [s for s in SCANNER_IDS if s in blocker]
    assert "trufflehog" in named
    for scanner_id in named:
        assert scanner_id in REGISTRY


def test_trufflehog_carries_a_base_equals_head_advisory():
    """Rare, not systematic -- so it belongs in the channel reported
    ALONGSIDE a successful init, never instead of one."""
    result = check_preconditions({"ownerType": "User", "scanner": "trufflehog"})
    assert result.blockers == ()
    (advisory,) = result.advisories
    assert "BASE" in advisory and "HEAD" in advisory
    assert "exits 1" in advisory


def test_base_equals_head_advisory_is_absent_for_gitleaks():
    """It is a property of trufflehog's action, not of scanning generally."""
    advisories = check_preconditions({"ownerType": "User"}).advisories
    assert not any("BASE" in a for a in advisories)


def test_trufflehog_is_never_blocked_in_an_org_repo():
    """The advisory must not have quietly become a blocker -- that would
    reintroduce exactly the dead end #27 exists to remove."""
    assert check_preconditions({
        "ownerType": "Organization", "scanner": "trufflehog",
    }).blockers == ()
