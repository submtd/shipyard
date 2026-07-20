"""Load and validate .keel.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CONFIG_NAME = ".keel.json"

TOPOLOGIES = ("gitflow", "trunk")
CONTRIBUTIONS = ("fork", "branch", "both")
REVIEW_POLICIES = ("approval", "review", "none")
STRATEGIES = ("squash", "merge", "rebase")


class ConfigError(Exception):
    """Raised when .keel.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    topology: str
    production: str
    integration: str
    feature_prefix: str
    release_prefix: str
    hotfix_prefix: str
    contributions: str
    review_policy: str
    merge_to_integration: str
    merge_to_production: str
    require_changelog: bool

    @property
    def is_trunk(self):
        return self.topology == "trunk"


def _one_of(value, allowed, field):
    if value not in allowed:
        raise ConfigError(
            f"{CONFIG_NAME}: '{field}' must be one of {', '.join(allowed)} "
            f"(got {value!r})."
        )
    return value


def load_config(repo_root: Path) -> Optional[Config]:
    path = Path(repo_root) / CONFIG_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{CONFIG_NAME} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_NAME} must contain a JSON object.")

    # Validate nested object fields
    branches_raw = raw.get("branches")
    if branches_raw is not None and not isinstance(branches_raw, dict):
        raise ConfigError(f"{CONFIG_NAME}: 'branches' must be a JSON object (got {type(branches_raw).__name__}).")
    branches = branches_raw or {}

    prefixes_raw = raw.get("prefixes")
    if prefixes_raw is not None and not isinstance(prefixes_raw, dict):
        raise ConfigError(f"{CONFIG_NAME}: 'prefixes' must be a JSON object (got {type(prefixes_raw).__name__}).")
    prefixes = prefixes_raw or {}

    merge_strategy_raw = raw.get("mergeStrategy")
    if merge_strategy_raw is not None and not isinstance(merge_strategy_raw, dict):
        raise ConfigError(f"{CONFIG_NAME}: 'mergeStrategy' must be a JSON object (got {type(merge_strategy_raw).__name__}).")
    strategy = merge_strategy_raw or {}

    topology = _one_of(raw.get("topology", "gitflow"), TOPOLOGIES, "topology")
    production = branches.get("production", "main")
    integration = production if topology == "trunk" else branches.get("integration", "develop")

    # Validate requireChangelog if present
    require_changelog_value = raw.get("requireChangelog", True)
    if not isinstance(require_changelog_value, bool):
        raise ConfigError(
            f"{CONFIG_NAME}: 'requireChangelog' must be a boolean "
            f"(got {type(require_changelog_value).__name__})."
        )

    return Config(
        topology=topology,
        production=production,
        integration=integration,
        feature_prefix=prefixes.get("feature", "feature/"),
        release_prefix=prefixes.get("release", "release/"),
        hotfix_prefix=prefixes.get("hotfix", "hotfix/"),
        contributions=_one_of(raw.get("contributions", "both"), CONTRIBUTIONS, "contributions"),
        review_policy=_one_of(raw.get("reviewPolicy", "review"), REVIEW_POLICIES, "reviewPolicy"),
        merge_to_integration=_one_of(
            strategy.get("toIntegration", "squash"), STRATEGIES, "mergeStrategy.toIntegration"),
        merge_to_production=_one_of(
            strategy.get("toProduction", "merge"), STRATEGIES, "mergeStrategy.toProduction"),
        require_changelog=require_changelog_value,
    )
