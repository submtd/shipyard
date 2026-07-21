"""Load and validate .stow.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from stow import stacks

CONFIG_NAME = ".stow.json"


class ConfigError(Exception):
    """Raised when .stow.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    stacks: dict[str, dict]


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

    stacks_raw = raw.get("stacks")
    if not isinstance(stacks_raw, dict):
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks' is required and must be a JSON "
            f"object (got {stacks_raw!r}). An empty object ({{}}) is "
            f"allowed and means base-only (no language stacks)."
        )

    resolved: dict[str, dict] = {}
    for stack_id, stack_value in stacks_raw.items():
        if stack_id not in stacks.STACK_IDS:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown stack id 'stacks.{stack_id}'. "
                f"Allowed ids: {', '.join(stacks.STACK_IDS)}."
            )
        if stack_value is not None and not isinstance(stack_value, dict):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}' must be null or a "
                f"JSON object (got {stack_value!r})."
            )
        resolved[stack_id] = stack_value or {}

    return Config(stacks=resolved)
