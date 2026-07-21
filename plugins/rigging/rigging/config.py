"""Load and validate .rigging.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rigging import stacks

CONFIG_NAME = ".rigging.json"

NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class ConfigError(Exception):
    """Raised when .rigging.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    name: str
    stacks: dict[str, tuple[str, ...]]


def _valid_name(value, field="name"):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ConfigError(
            f"{CONFIG_NAME}: '{field}' must be a string matching "
            f"{NAME_RE.pattern} (got {value!r})."
        )
    return value


def _valid_versions(value, stack_id):
    if not isinstance(value, list) or not value:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.versions' must be a "
            f"non-empty list of strings (got {value!r})."
        )
    versions = []
    for v in value:
        if not isinstance(v, str) or not VERSION_RE.fullmatch(v):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.versions' entries must "
                f"be strings matching {VERSION_RE.pattern} (got {v!r})."
            )
        versions.append(v)
    return tuple(versions)


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

    name = _valid_name(raw.get("name", "ci"))

    stacks_raw = raw.get("stacks")
    if not isinstance(stacks_raw, dict) or not stacks_raw:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks' is required and must be a non-empty "
            f"JSON object (got {stacks_raw!r})."
        )

    resolved: dict[str, tuple[str, ...]] = {}
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
        versions_raw = stack_value.get("versions")
        if versions_raw is None:
            versions = stacks.REGISTRY[stack_id].default_versions
        else:
            versions = _valid_versions(versions_raw, stack_id)
        resolved[stack_id] = versions

    return Config(name=name, stacks=resolved)
