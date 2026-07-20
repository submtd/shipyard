"""Tests for tri-state facts and enforcement of explicit comparison."""
import dataclasses

import pytest
from keel.facts import Facts, Tri


@pytest.mark.parametrize("value,expected", [
    (None, Tri.UNKNOWN), (True, Tri.TRUE), (False, Tri.FALSE),
])
def test_of_coerces_optional_bool(value, expected):
    assert Tri.of(value) is expected


@pytest.mark.parametrize("member", [Tri.TRUE, Tri.FALSE, Tri.UNKNOWN])
def test_tri_is_not_truthy_testable(member):
    # Three-valued logic must be compared explicitly; truthiness would
    # silently treat UNKNOWN as a decision.
    with pytest.raises(TypeError):
        bool(member)


def test_unknown_factory_is_all_unknown():
    f = Facts.unknown()
    assert f.branch is None
    assert f.capability is Tri.UNKNOWN
    assert f.pr_base is None
    assert f.pr_head is None
    assert f.pr_is_fork is Tri.UNKNOWN
    assert f.pr_review_state is None
    assert f.changelog_ok is Tri.UNKNOWN
    assert f.changelog_present is Tri.UNKNOWN


def test_facts_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        Facts.unknown().branch = "main"
