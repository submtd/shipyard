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


@dataclass(frozen=True)
class ServiceSpec:
    """One service container and how to drive it in a GitHub Actions job."""

    id: str
    #: Docker image WITHOUT a tag; image_ref appends the repo-chosen version.
    image: str
    #: The container's port, mapped host:container 1:1 and used in the URL.
    port: int
    #: Container environment, rendered under the service's `env:`. Ordered so
    #: the rendered YAML is deterministic.
    env: tuple[tuple[str, str], ...]
    #: The full Docker `--health-*` options string. A registry constant so a
    #: user string never reaches `options:`; every service MUST carry one, or
    #: the job races container startup and flakes.
    health_options: str
    #: The connection-URL template, composed with .format(port=...). Holds the
    #: registry's own credentials and default database name -- never user input.
    url_template: str

    def image_ref(self, version: str) -> str:
        return f"{self.image}:{version}"

    @property
    def url(self) -> str:
        return self.url_template.format(port=self.port)


_HEALTH = "--health-interval 10s --health-timeout 5s --health-retries 5"

SERVICE_REGISTRY: dict[str, ServiceSpec] = {
    "postgres": ServiceSpec(
        id="postgres",
        image="postgres",
        port=5432,
        env=(("POSTGRES_PASSWORD", "postgres"), ("POSTGRES_DB", "postgres")),
        health_options=f"--health-cmd pg_isready {_HEALTH}",
        url_template="postgresql://postgres:postgres@localhost:{port}/postgres",
    ),
    "mysql": ServiceSpec(
        id="mysql",
        image="mysql",
        port=3306,
        env=(("MYSQL_ROOT_PASSWORD", "mysql"), ("MYSQL_DATABASE", "mysql")),
        health_options=f'--health-cmd "mysqladmin ping" {_HEALTH}',
        url_template="mysql://root:mysql@localhost:{port}/mysql",
    ),
    "redis": ServiceSpec(
        id="redis",
        image="redis",
        port=6379,
        env=(),
        health_options=f'--health-cmd "redis-cli ping" {_HEALTH}',
        url_template="redis://localhost:{port}",
    ),
}

SERVICE_IDS: tuple[str, ...] = tuple(SERVICE_REGISTRY)
