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

#: Accepted keys. An unknown key is an error, not something to ignore: the
#: rendered pytest.ini spells these lowercase (testpaths, pythonpath,
#: addopts), so mirroring the rendered names here instead of the camelCase
#: config names is the natural mistake -- and silently discarding it leaves
#: pytest scanning the whole tree, a symptom that shows up nowhere near the
#: cause.
TOP_LEVEL_KEYS = frozenset({"stacks"})
STACK_KEYS = frozenset({"testPaths", "pythonPath", "importMode", "addOpts"})

# Charset check only: non-empty, no whitespace anywhere in the string. The
# structural rules (no leading "/", no ".." segment, no leading "#"/";") are
# enforced separately in _valid_path so the error messages can be specific
# about which rule tripped. fullmatch (not match+$) so a trailing newline
# can't sneak past the anchor -- see the fullmatch-vs-$ lesson from
# rigging/stow. Whitespace (not just newlines) is rejected because these
# values land in pytest.ini's testpaths/pythonpath, which pytest tokenizes
# on whitespace -- a path like "my tests" would silently split into two
# nonexistent paths and pytest would fall back to scanning the whole tree.
# Same class of value as FLAG_RE (addOpts), which already excludes all
# whitespace. A leading "#" or ";" is rejected for the same reason: pytest
# parses pytest.ini with iniconfig, which treats any line (including an
# indented continuation line) whose first non-space character is "#" or ";"
# as a COMMENT and strips it -- a testPaths/pythonPath entry of "#unit" or
# ";src" would render into pytest.ini and then be silently dropped, leaving
# testpaths empty and pytest scanning the whole tree.
#
# Quotes and the other shell-significant characters are excluded for a
# sharper reason than the ones above: pytest does not merely tokenize these
# values on whitespace, it *shlex-splits* them. An unbalanced quote is fatal
# to the entire run -- shlex raises ValueError("No closing quotation") from
# inside pytest's own config layer, before collection starts, so the user
# gets a traceback rather than a bad value. A plain \S+ let that through:
#
#     {"stacks": {"python": {"addOpts": ["-k'foo"]}}}
#       -> addopts = --import-mode=importlib -k'foo
#       -> pytest --collect-only: ValueError: No closing quotation
#
# Rendering a pytest.ini that stops pytest from starting is precisely the
# failure ballast exists to prevent, so the charset excludes every character
# that changes how the value is tokenized downstream.
_SHLEX_SIGNIFICANT = "'\"\\`$"

PATH_RE = re.compile(rf"[^\s{re.escape(_SHLEX_SIGNIFICANT)}]+")

# Flags that are actively harmful in a COMMITTED pytest.ini, which every run
# in every environment inherits. Two families:
#   - interactive debuggers block on stdin and hang CI until it times out;
#   - cache-dependent selection makes WHICH TESTS RUN depend on a previous
#     local run's .pytest_cache, silently narrowing the suite.
# Deliberately NOT denied: -s/--capture=no and -x/--exitfirst are defensible
# standing preferences, not hostile.
DENIED_ADD_OPTS = frozenset({
    "--pdb", "--trace", "--pdbcls",
    "--lf", "--last-failed", "--ff", "--failed-first",
    "--sw", "--stepwise", "--stepwise-skip",
})

# A non-empty token with no whitespace/newline and nothing shlex-significant,
# e.g. "-q", "--strict-markers", "--cov=x".
FLAG_RE = re.compile(rf"[^\s{re.escape(_SHLEX_SIGNIFICANT)}]+")


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
    if value[0] in "#;":
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
                f"relative path strings with no whitespace, no quotes or "
                f"other shell-significant characters, no leading '/', "
                f"no leading '#' or ';', and no '..' segment (got {entry!r})."
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
                f"non-empty tokens with no whitespace and no quotes or "
                f"other shell-significant characters (got {entry!r})."
            )
        flag = entry.split("=", 1)[0]
        if flag in DENIED_ADD_OPTS:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.addOpts' must not contain "
                f"{flag!r} -- it is unsafe in a committed pytest.ini "
                f"(interactive debuggers hang CI; cache-dependent selection "
                f"silently narrows the suite)."
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

    unknown_top = set(raw) - TOP_LEVEL_KEYS
    if unknown_top:
        raise ConfigError(
            f"{CONFIG_NAME}: unknown key(s) {', '.join(sorted(unknown_top))}. "
            f"Allowed keys: {', '.join(sorted(TOP_LEVEL_KEYS))}."
        )

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
        unknown = set(stack_value) - STACK_KEYS
        if unknown:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown key(s) "
                f"{', '.join(sorted(unknown))} in 'stacks.{stack_id}'. "
                f"Allowed keys: {', '.join(sorted(STACK_KEYS))}."
            )
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
