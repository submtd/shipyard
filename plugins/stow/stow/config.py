"""Load and validate .stow.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from stow import stacks

CONFIG_NAME = ".stow.json"

#: Accepted keys. An unknown key is an error rather than something to
#: ignore: silently dropping it means the user believes they configured
#: something they didn't, and the resulting behaviour change surfaces far
#: from its cause.
#: Stack values carry no options yet, so the allowed set is empty --
#: accepting a key and then never reading it would be the same lie.
TOP_LEVEL_KEYS = frozenset({"stacks"})
STACK_KEYS = frozenset()



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

    unknown = set(raw) - TOP_LEVEL_KEYS
    if unknown:
        raise ConfigError(
            f"{CONFIG_NAME}: unknown key(s) {', '.join(sorted(unknown))}. "
            f"Allowed keys: {', '.join(sorted(TOP_LEVEL_KEYS))}."
        )

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
        stack_value = stack_value or {}
        unknown_stack = set(stack_value) - STACK_KEYS
        if unknown_stack:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown key(s) "
                f"{', '.join(sorted(unknown_stack))} in 'stacks.{stack_id}'. "
                f"Stack values take no options; use an empty object or null."
            )
        resolved[stack_id] = stack_value

    return Config(stacks=resolved)
