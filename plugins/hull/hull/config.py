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
TOP_LEVEL_KEYS = frozenset({"name", "scanner", "pushBranches", "licenseSecret"})


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


#: A GitHub Actions secret NAME -- never a secret value. It is interpolated
#: into `${{ secrets.<NAME> }}` in the rendered workflow, which is the one
#: place in hull where a config string lands inside an Actions expression
#: rather than merely inside a quoted YAML scalar. So this pattern is
#: deliberately stricter than anything else in this file: leading letter or
#: underscore, then letters/digits/underscores, nothing else. No dot, no
#: dash, no space, no brace, no quote -- which means a value that passes here
#: cannot close the expression it sits in, cannot open a second one, and
#: cannot break out of the double-quoted scalar the renderer wraps it in.
#: GitHub's own secret names are a subset of this (they are upper-case
#: alphanumeric-plus-underscore and may not start with a digit), so the
#: strictness costs a user nothing they could actually have created.
SECRET_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


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
    #: Name of the repo/org secret holding the scanner's license key, or None
    #: when there is none to pass. Optional and defaulting to None so every
    #: config written before this key existed keeps rendering byte-identical
    #: output; when it IS set, plan.py adds `<scanner license_env>:
    #: "${{ secrets.<licenseSecret> }}"` to the scan step's env alongside
    #: GITHUB_TOKEN. hull never sees or stores the key itself -- only the
    #: name of the secret GitHub should hand the job at run time.
    license_secret: Optional[str] = None


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


def _valid_license_secret(value, scanner):
    """Validate an optional `licenseSecret` against SECRET_NAME_RE and the
    chosen scanner.

    Two separate failures are caught here, and they are worth distinguishing:

    1. A name that is not a plausible GitHub Actions secret identifier. This
       is the injection guard -- the value is interpolated into
       `${{ secrets.<NAME> }}`, so anything containing a brace, a quote or
       whitespace could restructure the expression (or the YAML around it)
       rather than name a secret. Rejecting at load time means the renderer
       is never handed such a string in the first place.
    2. A name set for a scanner that has no license gate at all
       (`ScannerSpec.license_env is None`). Accepting it would leave the user
       believing they had configured something that is silently discarded --
       the same failure mode the unknown-key check above exists to prevent,
       so it gets the same treatment: a loud error naming the field.
    """
    if value is None:
        return None
    if not isinstance(value, str) or not SECRET_NAME_RE.fullmatch(value):
        raise ConfigError(
            f"{CONFIG_NAME}: 'licenseSecret' must be a GitHub Actions secret "
            f"name matching {SECRET_NAME_RE.pattern} (got {value!r})."
        )
    if scanners.REGISTRY[scanner].license_env is None:
        raise ConfigError(
            f"{CONFIG_NAME}: 'licenseSecret' is set but scanner {scanner!r} "
            f"has no license key to pass it to; remove 'licenseSecret'."
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
    # Validated after `scanner`, and given it, because whether the key is
    # meaningful at all depends on which scanner was chosen.
    license_secret = _valid_license_secret(raw.get("licenseSecret"), scanner)

    return Config(name=name, scanner=scanner, push_branches=push_branches,
                  license_secret=license_secret)
