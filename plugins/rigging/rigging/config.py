"""Load and validate .rigging.json. Stdlib only; no subprocess."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from rigging import services as services_registry
from rigging import stacks

CONFIG_NAME = ".rigging.json"

#: Accepted keys. An unknown key is an error rather than something to
#: ignore: silently dropping it means the user believes they configured
#: something they didn't, and the resulting behaviour change surfaces far
#: from its cause.
TOP_LEVEL_KEYS = frozenset({"name", "stacks", "pushBranches"})
STACK_KEYS = frozenset({"versions", "packageManager", "testCommand", "services"})


NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$")

#: A GitHub Actions env var name. Same strictness as hull's licenseSecret and
#: for the same reason: it is rendered into YAML adjacent to values that matter,
#: and no legitimate env var name is excluded by this pattern.
URL_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: A Docker image tag the repo may pin a service to. Reuses VERSION_RE's shape
#: (charset-valid tags only) so a value needing YAML quoting or carrying an
#: Actions expression is refused before render.
SERVICE_VERSION_RE = VERSION_RE

#: A service database name the repo may choose. Letters, digits, underscore and
#: hyphen only -- safe both as a URL path segment and inside a double-quoted
#: YAML scalar, and narrow enough to refuse whitespace, quotes, and `${{` (none
#: of those characters are in the class), so a chosen name can never need YAML
#: quoting or smuggle an Actions expression into the rendered URL/env.
SERVICE_DATABASE_RE = re.compile(r"^[A-Za-z0-9_-]+$")

#: The literal that opens a GitHub Actions expression. A testCommand element
#: containing it is rejected at load: GitHub substitutes `${{ ... }}` at the
#: YAML layer, before any shell sees the line, so shlex.quote is no defence --
#: the only safe move is to refuse the value so it never reaches a rendered
#: `run:` block.
EXPRESSION_MARKER = "${{"


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
class ResolvedService:
    """One service a stack's job runs: which registry service, at what image
    version, the env var its connection URL is exposed in, and optionally the
    database name to create and connect to (None takes the service's default)."""

    service_id: str
    version: str
    url_env: str
    #: The database name, or None to take the service's registry default. Only
    #: meaningful for a service with a database concept (postgres, mysql);
    #: rejected at load for one without (redis). None is the default so an
    #: omitted `database` reproduces the pre-existing rendered bytes exactly.
    database: Optional[str] = None


@dataclass(frozen=True)
class StackConfig:
    """One stack's settings.

    A dataclass rather than a bare versions tuple because the next two
    increments each add a per-stack key (a custom test command, then service
    containers). Parallel dicts keyed by stack id would be three chances for
    the same repo's settings to desync; one container per stack cannot.
    """

    versions: tuple[str, ...]

    #: Which JavaScript package manager drives this stack's job, or None to
    #: take the registry default. Only meaningful for `node`; validated
    #: against stacks.NODE_PACKAGE_MANAGERS rather than a free string, so an
    #: unknown value fails here instead of rendering a workflow that runs a
    #: command the runner does not have.
    package_manager: Optional[str] = None

    #: A custom test command as an argv tuple, replacing this stack's (or its
    #: node package manager's) default test argv. None takes the default. An
    #: argv tuple, not a shell string, so shell metacharacters are inert once
    #: rendered -- and pipes, redirects, and `&&` are simply not expressible,
    #: which is the point: a repo needing a shell pipeline needs a hand-written
    #: workflow, not this key.
    test_command: Optional[tuple[str, ...]] = None

    #: Service containers this stack's job runs alongside its tests, in config
    #: order. Empty when none are declared.
    services: tuple[ResolvedService, ...] = ()


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


def _valid_package_manager(value, stack_id):
    """Validate an optional `packageManager` for one stack.

    Rejects it outright for a stack with no manager concept (today, anything
    but node) rather than accepting a setting that would do nothing. That is
    the same reasoning the unknown-key check applies one level up: a silently
    discarded setting leaves the user believing they configured something.
    """
    if value is None:
        return None
    # isinstance BEFORE the membership test: an unhashable value (a list, a
    # dict) raises TypeError out of `in` on a dict, and the contract here is
    # that bad config raises ConfigError naming the field.
    if not isinstance(value, str):
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.packageManager' must be a "
            f"string (got {value!r})."
        )
    if stack_id != "node":
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.packageManager' is set, but "
            f"stack {stack_id!r} has no package manager to select; remove it."
        )
    if value not in stacks.NODE_PACKAGE_MANAGERS:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.packageManager' must be one "
            f"of {', '.join(stacks.NODE_PACKAGE_MANAGERS)} (got {value!r})."
        )
    return value


def _valid_test_command(value, stack_id):
    """Validate an optional `testCommand` for one stack into an argv tuple.

    Two refusals carry the injection guarantee (the rest is handled by
    shlex.quote at render): an element containing `${{` (a GitHub Actions
    expression opener, substituted before any shell runs and unquotable) or a
    newline (which would break out of the single argv line) is rejected here,
    at load, so neither can reach a rendered `run:` block.
    """
    if value is None:
        return None
    if not isinstance(value, list) or not value:
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.testCommand' must be a "
            f"non-empty list of strings (got {value!r})."
        )
    argv = []
    for part in value:
        if not isinstance(part, str) or not part:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.testCommand' entries must "
                f"be non-empty strings (got {part!r})."
            )
        if EXPRESSION_MARKER in part:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.testCommand' entry {part!r} "
                f"contains {EXPRESSION_MARKER!r}, a GitHub Actions expression "
                f"opener. It is substituted before any shell runs and cannot be "
                f"made safe by quoting; remove it."
            )
        # splitlines() catches every line break -- \n, \r, \r\n, and the
        # Unicode separators (U+2028/U+2029/NEL) -- not just \n. A bare \r is a
        # line break to a YAML parser, so it would let the rendered run: command
        # differ from what was written even though shlex.quote keeps it inert at
        # the shell layer. `part.splitlines() != [part]` is true for any element
        # carrying a break, including a trailing one (which `len(...) > 1` would
        # miss).
        if part.splitlines() != [part]:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.testCommand' entry {part!r} "
                f"contains a line break; each entry is one argv element."
            )
        argv.append(part)
    return tuple(argv)


_SERVICE_KEYS = frozenset({"version", "urlEnv", "database"})


def _valid_services(value, stack_id):
    """Validate the optional `services` mapping into a tuple of ResolvedService.

    A service id must be one the registry knows (a workflow rigging cannot
    health-check is worse than none); `version` and `urlEnv` are both required
    (a service with no urlEnv exposes nothing, and there is no version to
    default to); and `urlEnv` must be a plain env var identifier, since it is
    rendered into YAML. `database` is optional -- omitted, the service's
    registry default is used, which reproduces the pre-existing bytes; set, it
    names the database rigging composes into both the container env and the
    connection URL, and is rejected for a service with no database concept. The
    image is pinned by tag, and the connection URL is composed by rigging from
    registry constants, so neither is user input here.
    """
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise ConfigError(
            f"{CONFIG_NAME}: 'stacks.{stack_id}.services' must be a JSON object "
            f"of service id -> settings (got {value!r})."
        )
    resolved = []
    for service_id, entry in value.items():
        if service_id not in services_registry.SERVICE_REGISTRY:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.services' names unknown "
                f"service {service_id!r}. Allowed: "
                f"{', '.join(services_registry.SERVICE_IDS)}."
            )
        spec = services_registry.SERVICE_REGISTRY[service_id]
        if not isinstance(entry, dict):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.services.{service_id}' must "
                f"be a JSON object (got {entry!r})."
            )
        unknown = set(entry) - _SERVICE_KEYS
        if unknown:
            raise ConfigError(
                f"{CONFIG_NAME}: unknown key(s) {', '.join(sorted(unknown))} in "
                f"'stacks.{stack_id}.services.{service_id}'. Allowed keys: "
                f"{', '.join(sorted(_SERVICE_KEYS))}."
            )
        version = entry.get("version")
        if not isinstance(version, str) or not SERVICE_VERSION_RE.fullmatch(version):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.services.{service_id}.version' "
                f"is required and must be a string matching "
                f"{SERVICE_VERSION_RE.pattern} (got {version!r})."
            )
        url_env = entry.get("urlEnv")
        if not isinstance(url_env, str) or not URL_ENV_RE.fullmatch(url_env):
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.services.{service_id}.urlEnv' "
                f"is required and must be an env var name matching "
                f"{URL_ENV_RE.pattern} (got {url_env!r})."
            )
        database = entry.get("database")
        if database is not None:
            # Reject `database` for a service with no database concept (redis)
            # rather than silently ignore it -- the same reasoning as
            # _valid_package_manager rejecting packageManager off node: a
            # discarded setting leaves the user believing they configured
            # something. Name the field so the message is actionable.
            if spec.database_env is None:
                raise ConfigError(
                    f"{CONFIG_NAME}: 'stacks.{stack_id}.services.{service_id}."
                    f"database' is set, but service {service_id!r} has no "
                    f"database to name; remove it."
                )
            if not isinstance(database, str) or not SERVICE_DATABASE_RE.fullmatch(database):
                raise ConfigError(
                    f"{CONFIG_NAME}: 'stacks.{stack_id}.services.{service_id}."
                    f"database' must be a string matching "
                    f"{SERVICE_DATABASE_RE.pattern} (got {database!r})."
                )
        resolved.append(ResolvedService(service_id=service_id, version=version,
                                        url_env=url_env, database=database))
    return tuple(resolved)


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
        package_manager = _valid_package_manager(
            stack_value.get("packageManager"), stack_id)
        test_command = _valid_test_command(
            stack_value.get("testCommand"), stack_id)
        service_list = _valid_services(stack_value.get("services"), stack_id)
        resolved[stack_id] = StackConfig(versions=versions,
                                         package_manager=package_manager,
                                         test_command=test_command,
                                         services=service_list)

    return Config(name=name, stacks=resolved, push_branches=push_branches)
