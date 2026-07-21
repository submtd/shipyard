"""Load and validate .ballast.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ballast import stacks

CONFIG_NAME = ".ballast.json"

IMPORT_MODES = ("importlib", "prepend", "append")

# Charset check only: non-empty, no whitespace anywhere in the string. The
# structural rules (no leading "/", no ".." segment) are enforced separately
# in _valid_path so the error messages can be specific about which rule
# tripped. fullmatch (not match+$) so a trailing newline can't sneak past
# the anchor -- see the fullmatch-vs-$ lesson from rigging/stow. Whitespace
# (not just newlines) is rejected because these values land in pytest.ini's
# testpaths/pythonpath, which pytest tokenizes on whitespace -- a path like
# "my tests" would silently split into two nonexistent paths and pytest
# would fall back to scanning the whole tree. Same class of value as
# FLAG_RE (addOpts), which already excludes all whitespace.
PATH_RE = re.compile(r"\S+")

# A non-empty token with no whitespace/newline, e.g. "-q", "--strict-markers",
# "--cov=x".
FLAG_RE = re.compile(r"\S+")


class ConfigError(Exception):
    """Raised when .ballast.json exists but cannot be used."""


@dataclass(frozen=True)
class PytestConfig:
    test_paths: tuple[str, ...]
    python_path: tuple[str, ...]
    import_mode: str
    add_opts: tuple[str, ...]


@dataclass(frozen=True)
class Config:
    stacks: dict[str, PytestConfig]


def _valid_path(value: object) -> bool:
    if not isinstance(value, str) or not PATH_RE.fullmatch(value):
        return False
    if value.startswith("/"):
        return False
    if any(segment == ".." for segment in value.split("/")):
        return False
    return True


def _valid_paths(value, stack_id, field, *, allow_empty: bool) -> tuple[str, ...]:
    if not isinstance(value, list) or (not allow_empty and not value):
        empty_note = "" if allow_empty else "non-empty "
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.{field}' must be a "
            f"{empty_note}list of relative path strings (got {value!r})."
        )
    paths = []
    for entry in value:
        if not _valid_path(entry):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.{field}' entries must be "
                f"relative path strings with no whitespace, no leading '/', "
                f"and no '..' segment (got {entry!r})."
            )
        paths.append(entry)
    return tuple(paths)


def _valid_import_mode(value, stack_id) -> str:
    if not isinstance(value, str) or value not in IMPORT_MODES:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.importMode' must be one of "
            f"{IMPORT_MODES} (got {value!r})."
        )
    return value


def _valid_add_opts(value, stack_id) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.addOpts' must be a list of "
            f"flag tokens (got {value!r})."
        )
    opts = []
    for entry in value:
        if not isinstance(entry, str) or not FLAG_RE.fullmatch(entry):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.addOpts' entries must be "
                f"non-empty tokens with no whitespace (got {entry!r})."
            )
        opts.append(entry)
    return tuple(opts)


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
    if not isinstance(stacks_raw, dict) or not stacks_raw:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks' is required and must be a non-empty "
            f"JSON object (got {stacks_raw!r})."
        )

    resolved: dict[str, PytestConfig] = {}
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
        spec = stacks.REGISTRY[stack_id]

        test_paths_raw = stack_value.get("testPaths")
        if test_paths_raw is None:
            test_paths = spec.default_test_paths
        else:
            test_paths = _valid_paths(
                test_paths_raw, stack_id, "testPaths", allow_empty=False
            )

        python_path_raw = stack_value.get("pythonPath")
        if python_path_raw is None:
            python_path = ()
        else:
            python_path = _valid_paths(
                python_path_raw, stack_id, "pythonPath", allow_empty=True
            )

        import_mode_raw = stack_value.get("importMode")
        if import_mode_raw is None:
            import_mode = spec.default_import_mode
        else:
            import_mode = _valid_import_mode(import_mode_raw, stack_id)

        add_opts_raw = stack_value.get("addOpts")
        if add_opts_raw is None:
            add_opts = ()
        else:
            add_opts = _valid_add_opts(add_opts_raw, stack_id)

        resolved[stack_id] = PytestConfig(
            test_paths=test_paths,
            python_path=python_path,
            import_mode=import_mode,
            add_opts=add_opts,
        )

    return Config(stacks=resolved)
