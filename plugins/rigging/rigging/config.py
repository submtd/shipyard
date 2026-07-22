"""Load and validate .rigging.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rigging import stacks

CONFIG_NAME = ".rigging.json"

#: Accepted keys. An unknown key is an error rather than something to
#: ignore: silently dropping it means the user believes they configured
#: something they didn't, and the resulting behaviour change surfaces far
#: from its cause.
TOP_LEVEL_KEYS = frozenset({"name", "stacks", "pushBranches"})
STACK_KEYS = frozenset({"versions"})


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")


class ConfigError(Exception):
    """Raised when .rigging.json exists but cannot be used."""


#: Branches whose pushes trigger CI. Pull requests always trigger it, so
#: listing every branch here (the old `on: [push, pull_request]`) ran the
#: whole matrix twice for any PR opened from a branch in the same repo.
#: Restricting push to the long-lived branches keeps both signals and pays
#: for each once. Defaults to the conventional trunk; a repo on `master` or
#: with a `develop` line sets its own -- silently defaulting would leave it
#: with no push CI at all.
DEFAULT_PUSH_BRANCHES: tuple[str, ...] = ("main",)

#: A git branch name, minus the ambiguous and shell-significant characters.
#: Deliberately narrower than git's own rules: this value is rendered into
#: YAML, so a name that needed quoting or escaping is a name we refuse.
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


@dataclass(frozen=True)
class StackConfig:
    """One stack's settings.

    A dataclass rather than a bare versions tuple because the next two
    increments each add a per-stack key (a custom test command, then service
    containers). Parallel dicts keyed by stack id would be three chances for
    the same repo's settings to desync; one container per stack cannot.
    """

    versions: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    name: str
    stacks: dict[str, StackConfig]
    push_branches: tuple[str, ...] = DEFAULT_PUSH_BRANCHES


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


def _valid_push_branches(value):
    if value is None:
        return DEFAULT_PUSH_BRANCHES
    if not isinstance(value, list) or not value:
        raise ConfigError(
            f"{CONFIG_NAME}: 'pushBranches' must be a non-empty list of "
            f"branch names (got {value!r})."
        )
    branches = []
    for branch in value:
        if not isinstance(branch, str) or not BRANCH_RE.fullmatch(branch):
            raise ConfigError(
                f"{CONFIG_NAME}: 'pushBranches' entries must be strings "
                f"matching {BRANCH_RE.pattern} (got {branch!r})."
            )
        branches.append(branch)
    return tuple(branches)


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

    name = _valid_name(raw.get("name", "ci"))
    push_branches = _valid_push_branches(raw.get("pushBranches"))

    stacks_raw = raw.get("stacks")
    if not isinstance(stacks_raw, dict) or not stacks_raw:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks' is required and must be a non-empty "
            f"JSON object (got {stacks_raw!r})."
        )

    resolved: dict[str, StackConfig] = {}
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
                f"Allowed keys: {', '.join(sorted(STACK_KEYS))}."
            )

        versions_raw = stack_value.get("versions")
        if versions_raw is None:
            versions = stacks.REGISTRY[stack_id].default_versions
        else:
            versions = _valid_versions(versions_raw, stack_id)
        resolved[stack_id] = StackConfig(versions=versions)

    return Config(name=name, stacks=resolved, push_branches=push_branches)
