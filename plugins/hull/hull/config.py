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
TOP_LEVEL_KEYS = frozenset({"name", "scanner"})


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class ConfigError(Exception):
    """Raised when .hull.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    name: str
    scanner: str


def _valid_name(value, field="name"):
    if not isinstance(value, str) or not NAME_RE.fullmatch(value):
        raise ConfigError(
            f"{CONFIG_NAME}: '{field}' must be a string matching "
            f"{NAME_RE.pattern} (got {value!r})."
        )
    return value


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

    return Config(name=name, scanner=scanner)
