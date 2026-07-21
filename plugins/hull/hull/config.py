"""Load and validate .hull.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from hull import scanners

CONFIG_NAME = ".hull.json"

#: Accepted keys. An unknown key is an error rather than something to
#: ignore: silently dropping it means the user believes they configured
#: something they didn't, and the resulting behaviour change surfaces far
#: from its cause.
TOP_LEVEL_KEYS = frozenset({"name", "scanner", "pushBranches"})


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


#: Branches whose pushes trigger the scan. Pull requests always trigger it,
#: so the old `on: [push, pull_request]` ran the whole scan twice for any PR
#: raised from a branch in the same repo. Kept byte-identical in meaning to
#: rigging's key of the same name -- a repo scaffolded by both ends up with
#: these workflows side by side, and two different trigger shapes would be a
#: puzzle with no answer.
DEFAULT_PUSH_BRANCHES: tuple[str, ...] = ("main",)

#: A git branch name, minus the ambiguous and shell-significant characters.
#: Deliberately narrower than git's own rules: this value is rendered into
#: YAML, so a name that needed quoting or escaping is a name we refuse.
BRANCH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


class ConfigError(Exception):
    """Raised when .hull.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    name: str
    scanner: str
    push_branches: tuple[str, ...] = DEFAULT_PUSH_BRANCHES


def _valid_name(value, field="name"):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ConfigError(
            f"{CONFIG_NAME}: '{field}' must be a string matching "
            f"{NAME_RE.pattern} (got {value!r})."
        )
    return value


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


def _valid_scanner(value):
    if not isinstance(value, str) or value not in scanners.SCANNER_IDS:
        raise ConfigError(
            f"{CONFIG_NAME}: 'scanner' must be one of "
            f"{', '.join(scanners.SCANNER_IDS)} (got {value!r})."
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

    name = _valid_name(raw.get("name", "security"))
    scanner = _valid_scanner(raw.get("scanner", "gitleaks"))
    push_branches = _valid_push_branches(raw.get("pushBranches"))

    return Config(name=name, scanner=scanner, push_branches=push_branches)
