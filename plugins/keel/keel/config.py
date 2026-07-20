"""Load and validate .keel.json. Stdlib only; no subprocess."""
import json
from dataclasses import dataclass
from pathlib import Path

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


def load_config(repo_root):
    path = Path(repo_root) / CONFIG_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{CONFIG_NAME} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_NAME} must contain a JSON object.")

    branches = raw.get("branches") or {}
    prefixes = raw.get("prefixes") or {}
    strategy = raw.get("mergeStrategy") or {}

    topology = _one_of(raw.get("topology", "gitflow"), TOPOLOGIES, "topology")
    production = branches.get("production", "main")
    integration = production if topology == "trunk" else branches.get("integration", "develop")

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
        require_changelog=bool(raw.get("requireChangelog", True)),
    )
