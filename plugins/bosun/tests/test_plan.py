"""Config -> DependabotPlan tests.

Mirrors rigging/tests/test_plan.py and hull/tests/test_plan.py's shape.
"""
from __future__ import annotations

import pytest

from bosun.config import Config, EcosystemConfig
from bosun.plan import DependabotPlan, Update, build_plan


def test_reversed_config_order_yields_registry_order_updates():
    cfg = Config(
        ecosystems={
            "node": EcosystemConfig(interval="weekly"),
            "python": EcosystemConfig(interval="weekly"),
            "githubActions": EcosystemConfig(interval="weekly"),
        }
    )
    plan = build_plan(cfg)

    assert plan.updates == (
        Update(package_ecosystem="github-actions", directory="/", interval="weekly"),
        Update(package_ecosystem="pip", directory="/", interval="weekly"),
        Update(package_ecosystem="npm", directory="/", interval="weekly"),
    )


def test_update_interval_comes_from_config():
    cfg = Config(
        ecosystems={
            "python": EcosystemConfig(interval="monthly"),
        }
    )
    plan = build_plan(cfg)

    assert plan.updates == (
        Update(package_ecosystem="pip", directory="/", interval="monthly"),
    )


def test_update_directory_is_always_root():
    cfg = Config(
        ecosystems={
            "githubActions": EcosystemConfig(interval="daily"),
            "node": EcosystemConfig(interval="weekly"),
        }
    )
    plan = build_plan(cfg)

    assert all(update.directory == "/" for update in plan.updates)


def test_dependabotplan_version_is_2():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    plan = build_plan(cfg)
    assert plan.version == 2


def test_updates_is_a_tuple():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    plan = build_plan(cfg)
    assert isinstance(plan.updates, tuple)


def test_build_plan_is_deterministic():
    cfg = Config(
        ecosystems={
            "node": EcosystemConfig(interval="weekly"),
            "python": EcosystemConfig(interval="daily"),
            "githubActions": EcosystemConfig(interval="monthly"),
        }
    )
    assert build_plan(cfg) == build_plan(cfg)


def test_dependabotplan_is_frozen_dataclass():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    plan = build_plan(cfg)
    with pytest.raises(Exception):
        plan.version = 3


def test_update_is_frozen_dataclass():
    cfg = Config(ecosystems={"githubActions": EcosystemConfig(interval="weekly")})
    update = build_plan(cfg).updates[0]
    with pytest.raises(Exception):
        update.interval = "daily"
