"""Load and validate .bosun.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from bosun import ecosystems

CONFIG_NAME = ".bosun.json"

#: Accepted keys. An unknown key is an error rather than something to
#: ignore: silently dropping it means the user believes they configured
#: something they didn't, and the resulting behaviour change surfaces far
#: from its cause.
TOP_LEVEL_KEYS = frozenset({"ecosystems"})
ECOSYSTEM_KEYS = frozenset({"interval"})



class ConfigError(Exception):
    """Raised when .bosun.json exists but cannot be used."""


@dataclass(frozen=True)
class EcosystemConfig:
    interval: str


@dataclass(frozen=True)
class Config:
    ecosystems: dict[str, EcosystemConfig]


def _valid_interval(value, ecosystem_id) -> str:
    if not isinstance(value, str) or value not in ecosystems.INTERVALS:
        raise ConfigError(
            f"{CONFIG_NAME}: 'ecosystems.{ecosystem_id}.interval' must be "
            f"one of {ecosystems.INTERVALS} (got {value!r})."
        )
    return value


def load_config(root: Path) -> Optional[Config]:
    path = Path(root) / CONFIG_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{CONFIG_NAME} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_NAME} must contain a JSON object.")

    unknown = set(raw) - TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(
            f"{CONFIG_NAME}: unknown key(s) {', '.join(sorted(unknown))}. "
            f"Allowed keys: {', '.join(sorted(TOP_LEVEL_KEYS))}."
        )

    ecosystems_raw = raw.get("ecosystems")
    if not isinstance(ecosystems_raw, dict) or not ecosystems_raw:
        raise ConfigError(
            f"{CONFIG_NAME}: 'ecosystems' is required and must be a "
            f"non-empty JSON object (got {ecosystems_raw!r})."
        )

    resolved: dict[str, EcosystemConfig] = {}
    for ecosystem_id, ecosystem_value in ecosystems_raw.items():
        if ecosystem_id not in ecosystems.ECOSYSTEM_IDS:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown ecosystem id "
                f"'ecosystems.{ecosystem_id}'. "
                f"Allowed ids: {', '.join(ecosystems.ECOSYSTEM_IDS)}."
            )
        if ecosystem_value is not None and not isinstance(ecosystem_value, dict):
            raise ConfigError(
                f"{CONFIG_NAME}: 'ecosystems.{ecosystem_id}' must be null "
                f"or a JSON object (got {ecosystem_value!r})."
            )
        ecosystem_value = ecosystem_value or {}
        unknown_eco = set(ecosystem_value) - ECOSYSTEM_KEYS
        if unknown_eco:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown key(s) "
                f"{', '.join(sorted(unknown_eco))} in "
                f"'ecosystems.{ecosystem_id}'. "
                f"Allowed keys: {', '.join(sorted(ECOSYSTEM_KEYS))}."
            )

        interval_raw = ecosystem_value.get("interval")
        if interval_raw is None:
            interval = "weekly"
        else:
            interval = _valid_interval(interval_raw, ecosystem_id)

        resolved[ecosystem_id] = EcosystemConfig(interval=interval)

    return Config(ecosystems=resolved)
