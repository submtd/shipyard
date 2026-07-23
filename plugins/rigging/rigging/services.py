"""The service-container registry: databases and caches a CI job can run
alongside its tests, and how to drive each in GitHub Actions.

Pure data module. Stdlib only; no subprocess, no os, no networking -- the same
AST purity test that covers the rest of the engine covers this file.

Service images are pinned by major TAG (postgres:16), not by digest, a
deliberate inconsistency with the Action SHA-pinning rule: a service container
is an ephemeral fixture on a private network that never sees the workflow token
or the checked-out repo, and a tag keeps getting security patches without a
human. The health check is a registry constant, never user input, so no
user-supplied string ever lands in a Docker `options:` line.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ServiceSpec:
    """One service container and how to drive it in a GitHub Actions job."""

    id: str
    #: Docker image WITHOUT a tag; image_ref appends the repo-chosen version.
    image: str
    #: The container's port, mapped host:container 1:1 and used in the URL.
    port: int
    #: Container environment that is NOT the database name (e.g. the password),
    #: rendered under the service's `env:` before the database pair. Ordered so
    #: the rendered YAML is deterministic. The database name is composed
    #: separately at resolve time (see database_env) so a repo can choose it.
    base_env: tuple[tuple[str, str], ...]
    #: The full Docker `--health-*` options string. A registry constant so a
    #: user string never reaches `options:`; every service MUST carry one, or
    #: the job races container startup and flakes.
    health_options: str
    #: The connection-URL template, composed with .format(port=..., database=...).
    #: Holds the registry's own credentials -- never user input. A service with
    #: no database concept (redis) simply omits the `{database}` placeholder, so
    #: the argument is ignored for it.
    url_template: str
    #: The container env var that names the database (POSTGRES_DB, MYSQL_DATABASE),
    #: or None for a service with no database concept (redis). When set, the
    #: chosen database is rendered as this env var, appended after base_env.
    database_env: Optional[str] = None
    #: The database name used when the repo does not set `database`. Equal to the
    #: value this service hardcoded before the key existed, so an omitted
    #: `database` reproduces the pre-existing bytes exactly. None when there is
    #: no database concept (redis).
    default_database: Optional[str] = None

    def image_ref(self, version: str) -> str:
        return f"{self.image}:{version}"

    def url(self, database: Optional[str]) -> str:
        """The connection URL for `database`. A service without a `{database}`
        placeholder (redis) ignores the argument -- str.format drops unused
        keyword arguments."""
        return self.url_template.format(port=self.port, database=database)


_HEALTH = "--health-interval 10s --health-timeout 5s --health-retries 5"

SERVICE_REGISTRY: dict[str, ServiceSpec] = {
    "postgres": ServiceSpec(
        id="postgres",
        image="postgres",
        port=5432,
        base_env=(("POSTGRES_PASSWORD", "postgres"),),
        health_options=f"--health-cmd pg_isready {_HEALTH}",
        url_template="postgresql://postgres:postgres@localhost:{port}/{database}",
        database_env="POSTGRES_DB",
        default_database="postgres",
    ),
    "mysql": ServiceSpec(
        id="mysql",
        image="mysql",
        port=3306,
        base_env=(("MYSQL_ROOT_PASSWORD", "mysql"),),
        # `mysqladmin ping` is a LIVENESS probe, not a readiness one: it returns
        # exit 0 as soon as the server answers the socket (even on "Access
        # denied"), which can be a beat before MySQL will serve queries. That is
        # the standard GitHub Actions idiom and --health-retries covers the gap;
        # it is not a query-level check. Do not mistake it for one.
        health_options=f'--health-cmd "mysqladmin ping" {_HEALTH}',
        url_template="mysql://root:mysql@localhost:{port}/{database}",
        database_env="MYSQL_DATABASE",
        default_database="mysql",
    ),
    "redis": ServiceSpec(
        id="redis",
        image="redis",
        port=6379,
        base_env=(),
        health_options=f'--health-cmd "redis-cli ping" {_HEALTH}',
        url_template="redis://localhost:{port}",
        database_env=None,
        default_database=None,
    ),
}

SERVICE_IDS: tuple[str, ...] = tuple(SERVICE_REGISTRY)
