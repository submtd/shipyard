# rigging Service Containers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `.rigging.json` declare per-stack service containers (`postgres`, `mysql`, `redis`) so a repo whose tests need a live database gets a rendered job with a `services:` block, a health check it cannot forget, and the connection URL in an env var of its choosing.

**Architecture:** A `SERVICE_REGISTRY` (new `services.py`) owns each service's image, port, container env, health check, and connection-URL template — everything except the two things the repo picks: the image `version` and the `urlEnv` name. Config validates `stacks.<id>.services` into `StackConfig.services`; `plan.build_plan` resolves each into (a) a rendered `services:` block and (b) a job-level `env:` entry mapping `urlEnv` to the composed URL; `render` emits both at the job level. The seven-plus existing goldens stay byte-identical.

**Tech Stack:** Python 3.9+, pytest, stdlib only (`json`, `re`, `dataclasses`). No new dependencies, no new action pins.

## Global Constraints

- **The health check is rigging's property, never the user's.** A service with no `--health-cmd` races container startup and flakes — the worst CI failure, because red comes to mean "re-run". `SERVICE_REGISTRY` owns the health options; no user string ever reaches a Docker `options:` line.
- **External verification is mandatory and load-bearing.** The health commands, container env var names, and default ports are correct only if they match the service images' and GitHub's own documented service-container examples. Green byte-identity tests CANNOT catch a wrong health command — it renders fine and flakes at runtime. Task 1 verifies each against GitHub's documented examples and cites the source; do not invent them.
- **Images are pinned by major tag (`postgres:16`), NOT by digest.** Deliberate inconsistency with the Action SHA-pinning rule: a service container is an ephemeral fixture on a private network that never sees the workflow token or the repo, and a tag keeps getting security patches without a human. (An Action runs inside the job with the token — different threat model.)
- **`urlEnv` is a strict identifier:** `^[A-Za-z_][A-Za-z0-9_]*$`, the same strictness and reasoning as hull's `licenseSecret` — it is rendered into YAML adjacent to values that matter, and no legitimate env var name is excluded.
- **The connection URL is composed by rigging from registry constants** (credentials, DB name, host `localhost`, the registry port) — it is never user input. `version` selects only the image tag; it does not appear in the URL.
- **Both `version` and `urlEnv` are required per declared service.** A service with no `urlEnv` hands the repo nothing; there is no sensible version default.
- **Services attach per stack**, inside `stacks.<id>`, not at the top level — a polyglot repo where node needs Postgres and python does not must not pay for a DB in the python job.
- **The URL env var lands at the job level** (`env:` sibling of `steps:`), so every step in the job — including install/migration steps — sees it.
- **Existing goldens stay byte-identical:** `python.yml`, `node.yml`, `polyglot.yml`, `node-pnpm.yml`, `node-yarn1.yml`, `node-yarn-berry.yml`, `node-bun.yml`, `node-testcommand.yml`, `python-testcommand.yml`. A job with no services emits no `services:` and no `env:` line.
- **Engine purity:** stdlib only under `plugins/rigging/rigging/`.
- **Unknown config keys stay a hard `ConfigError`** — inside a service entry too.

## Render order (job level)

A serviced job renders in exactly this order; `services:` and `env:` appear only when non-empty:

```yaml
  node:
    runs-on: "ubuntu-latest"
    strategy:
      matrix:
        node: ["20"]
    services:
      postgres:
        image: "postgres:16"
        env:
          POSTGRES_PASSWORD: "postgres"
          POSTGRES_DB: "postgres"
        ports:
          - "5432:5432"
        options: "--health-cmd pg_isready --health-interval 10s --health-timeout 5s --health-retries 5"
    env:
      TEST_DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/postgres"
    steps:
      - uses: "actions/checkout@..."
      - uses: "actions/setup-node@..."
        with:
          node-version: "${{ matrix.node }}"
      - run: "npm ci"
      - run: "npm test"
```

---

### Task 1: `SERVICE_REGISTRY` — the service catalogue (externally verified)

**Files:**
- Create: `plugins/rigging/rigging/services.py`
- Test: `plugins/rigging/tests/test_services.py`

**Interfaces:**
- Produces: `services.ServiceSpec` (frozen dataclass: `id`, `image`, `port`, `env: tuple[tuple[str,str],...]`, `health_options: str`, `url_template: str`; property `image_ref(version)` → `f"{image}:{version}"`; property `url` → `url_template.format(port=port)`), `services.SERVICE_REGISTRY: dict[str, ServiceSpec]`, `services.SERVICE_IDS: tuple[str,...]`.

- [ ] **Step 1: Verify the health commands, env vars, and ports against GitHub's docs**

Before writing any values, confirm each service's health check, container env, and default port against GitHub's own service-container documentation and the image's Docker Hub page. Use WebFetch on:
- GitHub Actions "Creating PostgreSQL service containers" and "Creating Redis service containers" (docs.github.com) for the canonical `--health-cmd`/`--health-interval`/`--health-timeout`/`--health-retries` values and the `POSTGRES_PASSWORD` env requirement.
- The MySQL image docs for the `MYSQL_ROOT_PASSWORD` requirement and the `mysqladmin ping` health command.

Record in the report the exact documented health command per service and the URL you fetched it from. This is the one thing byte-identity tests cannot check; if a value cannot be confirmed from a source, say so rather than guessing.

- [ ] **Step 2: Write the failing tests**

Create `plugins/rigging/tests/test_services.py`:

```python
import re

from rigging.services import SERVICE_REGISTRY, SERVICE_IDS, ServiceSpec


def test_service_ids_derived_from_registry():
    assert SERVICE_IDS == tuple(SERVICE_REGISTRY)


def test_initial_services_are_postgres_mysql_redis():
    assert set(SERVICE_IDS) == {"postgres", "mysql", "redis"}


def test_image_ref_appends_the_version_tag():
    assert SERVICE_REGISTRY["postgres"].image_ref("16") == "postgres:16"


def test_url_is_composed_from_registry_constants_not_the_version():
    pg = SERVICE_REGISTRY["postgres"]
    # version selects the image tag only; it is not in the URL.
    assert pg.url == "postgresql://postgres:postgres@localhost:5432/postgres"
    assert SERVICE_REGISTRY["redis"].url == "redis://localhost:6379"
    assert SERVICE_REGISTRY["mysql"].url == "mysql://root:mysql@localhost:3306/mysql"


def test_every_service_carries_a_health_check():
    # The health check is the whole reason this is a registry; none may be empty.
    for sid, spec in SERVICE_REGISTRY.items():
        assert "--health-cmd" in spec.health_options, sid


def test_health_options_carry_no_actions_expression():
    for spec in SERVICE_REGISTRY.values():
        assert "${{" not in spec.health_options
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_services.py -v`
Expected: FAIL (`rigging.services` does not exist).

- [ ] **Step 4: Implement `services.py`**

Create `plugins/rigging/rigging/services.py` with the `ServiceSpec` dataclass and `SERVICE_REGISTRY`. Use the health commands, env vars, and ports **exactly as verified in Step 1**. The values below are the expected canonical forms — reconcile against Step 1 and correct any that the docs contradict:

```python
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
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests/test_services.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add plugins/rigging/rigging/services.py plugins/rigging/tests/test_services.py
git commit -m "feat(rigging): SERVICE_REGISTRY for postgres, mysql, redis (#26)"
```

---

### Task 2: Config layer — validate `stacks.<id>.services`

**Files:**
- Modify: `plugins/rigging/rigging/config.py`
- Test: `plugins/rigging/tests/test_config.py`

**Interfaces:**
- Consumes: `services.SERVICE_REGISTRY` (Task 1).
- Produces: `config.ResolvedService` (frozen dataclass: `service_id: str`, `version: str`, `url_env: str`); `config.StackConfig.services: tuple[ResolvedService, ...]` (default `()`); `config.URL_ENV_RE`; `config._valid_services(value, stack_id) -> tuple[ResolvedService, ...]`. `config.STACK_KEYS` gains `"services"`.

- [ ] **Step 1: Write the failing tests**

Add to `plugins/rigging/tests/test_config.py`:

```python
from rigging.config import ResolvedService  # add to existing imports


def test_services_resolve_to_tuple_of_resolved_services(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}}}
    }))
    assert cfg.stacks["node"].services == (
        ResolvedService(service_id="postgres", version="16",
                        url_env="TEST_DATABASE_URL"),
    )


def test_services_absent_is_empty_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].services == ()


def test_unknown_service_id_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "cassandra": {"version": "5", "urlEnv": "DB_URL"}}}}}))
    msg = str(e.value)
    assert "cassandra" in msg and "postgres" in msg  # names the bad id and the allowed set


def test_service_missing_version_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"urlEnv": "DB_URL"}}}}}))
    assert "version" in str(e.value)


def test_service_missing_url_env_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16"}}}}}))
    assert "urlEnv" in str(e.value)


@pytest.mark.parametrize("bad_env", ["1DB", "DB URL", "DB-URL", "${{x}}", ""])
def test_bad_url_env_rejected(tmp_path, bad_env):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": bad_env}}}}}))
    assert "urlEnv" in str(e.value)


@pytest.mark.parametrize("bad_version", ["16 rc", "1.0}}", "${{ x }}", "a b"])
def test_bad_service_version_rejected(tmp_path, bad_version):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": bad_version, "urlEnv": "DB_URL"}}}}}))
    assert "version" in str(e.value)


def test_unknown_key_inside_a_service_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": {
            "postgres": {"version": "16", "urlEnv": "DB_URL", "port": 5432}}}}}))
    assert "port" in str(e.value)


def test_services_not_a_dict_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"services": ["postgres"]}}}))
    assert "services" in str(e.value)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -k service -v`
Expected: FAIL (`services` is an unknown stack key; `ResolvedService` does not exist).

- [ ] **Step 3: Implement**

In `plugins/rigging/rigging/config.py`:

Add imports and the identifier regex near the other `_RE` constants:

```python
from rigging import services as services_registry

#: A GitHub Actions env var name. Same strictness as hull's licenseSecret and
#: for the same reason: it is rendered into YAML adjacent to values that matter,
#: and no legitimate env var name is excluded by this pattern.
URL_ENV_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

#: A Docker image tag the repo may pin a service to. Reuses VERSION_RE's shape
#: (charset-valid tags only) so a value needing YAML quoting or carrying an
#: Actions expression is refused before render.
SERVICE_VERSION_RE = VERSION_RE
```

Add `"services"` to `STACK_KEYS`:

```python
STACK_KEYS = frozenset({"versions", "packageManager", "testCommand", "services"})
```

Add the resolved-service dataclass (near `StackConfig`):

```python
@dataclass(frozen=True)
class ResolvedService:
    """One service a stack's job runs: which registry service, at what image
    version, and the env var its connection URL is exposed in."""

    service_id: str
    version: str
    url_env: str
```

Add `services` to `StackConfig` (after `test_command`):

```python
    #: Service containers this stack's job runs alongside its tests, in config
    #: order. Empty when none are declared.
    services: tuple[ResolvedService, ...] = ()
```

Add the validator (after `_valid_test_command`):

```python
_SERVICE_KEYS = frozenset({"version", "urlEnv"})


def _valid_services(value, stack_id):
    """Validate the optional `services` mapping into a tuple of ResolvedService.

    A service id must be one the registry knows (a workflow rigging cannot
    health-check is worse than none); `version` and `urlEnv` are both required
    (a service with no urlEnv exposes nothing, and there is no version to
    default to); and `urlEnv` must be a plain env var identifier, since it is
    rendered into YAML. The image is pinned by tag, and the connection URL is
    composed by rigging from registry constants, so neither is user input here.
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
        resolved.append(ResolvedService(service_id=service_id, version=version,
                                        url_env=url_env))
    return tuple(resolved)
```

Wire it into `load_config`, extending the `StackConfig(...)` construction:

```python
        test_command = _valid_test_command(
            stack_value.get("testCommand"), stack_id)
        service_list = _valid_services(stack_value.get("services"), stack_id)
        resolved[stack_id] = StackConfig(versions=versions,
                                         package_manager=package_manager,
                                         test_command=test_command,
                                         services=service_list)
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -v`
Expected: PASS (new service tests plus all existing config tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/rigging/rigging/config.py plugins/rigging/tests/test_config.py
git commit -m "feat(rigging): validate stacks.<id>.services into StackConfig (#26)"
```

---

### Task 3: Render — `services:` and job-level `env:`

**Files:**
- Modify: `plugins/rigging/rigging/plan.py` (Job gains `services` + `env`; `_build_job`/`build_plan` resolve them)
- Modify: `plugins/rigging/rigging/render.py` (`_job_lines` emits `services:` and `env:` when present)
- Modify: `scripts/sync_action_pins.py` (add the serviced golden to the regen list)
- Test: `plugins/rigging/tests/test_plan.py`, `plugins/rigging/tests/test_render.py`, `plugins/rigging/tests/test_injection.py`
- Create: `plugins/rigging/tests/golden/node-postgres.yml`, `plugins/rigging/tests/golden/node-redis.yml` (generated, not hand-written)

**Interfaces:**
- Consumes: `config.StackConfig.services`, `config.ResolvedService`, `services.SERVICE_REGISTRY`.
- Produces: `plan.Job.services: tuple[RenderedService, ...]` and `plan.Job.env: tuple[tuple[str, str], ...]`, where `RenderedService` is a small frozen dataclass (`name: str`, `image: str`, `env: tuple[tuple[str,str],...]`, `port: int`, `options: str`).

- [ ] **Step 1: Write the failing tests**

Add to `plugins/rigging/tests/test_render.py`:

```python
@pytest.mark.parametrize("data,golden", [
    ({"stacks": {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}}}},
     "node-postgres.yml"),
    # redis pins the two things postgres does not exercise: a service with NO
    # container env (so no `env:` block under it), and a health command whose
    # inner quotes must survive YAML double-quote escaping.
    ({"stacks": {"node": {"services": {
        "redis": {"version": "7", "urlEnv": "REDIS_URL"}}}}},
     "node-redis.yml"),
])
def test_serviced_node_job_matches_golden(tmp_path, data, golden):
    cfg = load_config(write(tmp_path, data))
    assert render(build_plan(cfg)) == read_golden(golden)


def test_a_job_with_no_services_renders_no_services_or_env_block(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    out = render(build_plan(cfg))
    assert "services:" not in out
    assert "\n    env:\n" not in out  # no job-level env block


def test_url_env_lands_at_job_level_and_carries_the_composed_url(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}}}}))
    out = render(build_plan(cfg))
    assert '    env:\n      TEST_DATABASE_URL: "postgresql://postgres:postgres@localhost:5432/postgres"' in out


def test_health_options_render_into_the_services_options_line(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "DB_URL"}}}}}))
    out = render(build_plan(cfg))
    assert "--health-cmd pg_isready" in out
```

Add to `plugins/rigging/tests/test_injection.py`:

```python
def test_service_options_never_contain_an_actions_expression(tmp_path):
    out = render_for(tmp_path, {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "DB_URL"}}}})
    # every ${{ }} in the file is still only the whitelisted matrix form
    for expr in EXPRESSION_RE.findall(out):
        assert WHITELIST_RE.fullmatch(expr)


def test_hostile_url_env_is_refused_before_render(tmp_path):
    write_config(tmp_path, {"name": "ci", "stacks": {"node": {"services": {
        "postgres": {"version": "16", "urlEnv": "${{ secrets.X }}"}}}}})
    with pytest.raises(ConfigError):
        load_config(tmp_path)
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_render.py -k "service or url_env or health" plugins/rigging/tests/test_injection.py -k "service or url_env" -v`
Expected: FAIL (Job has no `services`/`env`; golden absent).

- [ ] **Step 3: Implement the plan layer**

In `plugins/rigging/rigging/plan.py`:

Add a rendered-service dataclass and extend `Job`:

```python
from rigging import services as services_registry


@dataclass(frozen=True)
class RenderedService:
    """A service container resolved to exactly what render emits."""

    name: str
    image: str
    env: tuple[tuple[str, str], ...]
    port: int
    options: str


@dataclass(frozen=True)
class Job:
    """One CI job for a configured stack."""

    id: str
    runs_on: str
    matrix_var: str
    versions: tuple[str, ...]
    steps: tuple[stacks.Step, ...]
    #: Service containers for this job, in config order. Empty when none.
    services: tuple[RenderedService, ...] = ()
    #: Job-level environment (today: each service's connection URL under its
    #: urlEnv), in config order. Empty when none.
    env: tuple[tuple[str, str], ...] = ()
```

Add a resolver and thread services through `_build_job` and `build_plan`:

```python
def _resolve_services(service_list):
    """Turn config.ResolvedService entries into (rendered services, job env)."""
    rendered = []
    env = []
    for rs in service_list:
        spec = services_registry.SERVICE_REGISTRY[rs.service_id]
        rendered.append(RenderedService(
            name=spec.id,
            image=spec.image_ref(rs.version),
            env=spec.env,
            port=spec.port,
            options=spec.health_options,
        ))
        env.append((rs.url_env, spec.url))
    return tuple(rendered), tuple(env)
```

`_build_job` gains a `services=()` parameter, calls `_resolve_services`, and passes both to `Job`. `build_plan` passes `stack_cfg.services`:

```python
def _build_job(stack_id, versions, manager_id=stacks.DEFAULT_NODE_PACKAGE_MANAGER,
               test_command=None, services=()):
    ...  # unchanged up through test_step
    rendered_services, job_env = _resolve_services(services)
    return Job(
        id=spec.id, runs_on="ubuntu-latest", matrix_var=spec.matrix_var,
        versions=versions,
        steps=(CHECKOUT_STEP, *manager_setup, setup_step,
               *manager_post_setup, *spec.steps, *manager_install, test_step),
        services=rendered_services,
        env=job_env,
    )


def build_plan(cfg):
    jobs = tuple(
        _build_job(stack_id, sc.versions,
                   sc.package_manager or stacks.DEFAULT_NODE_PACKAGE_MANAGER,
                   sc.test_command, sc.services)
        for stack_id, sc in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
```

- [ ] **Step 4: Implement the render layer**

In `plugins/rigging/rigging/render.py`, extend `_job_lines` to emit `services:` and `env:` (in that order) after the matrix and before `steps:`, only when present. The matrix block ends the current list before `"    steps:"`; insert the new blocks between them:

```python
def _job_lines(job) -> list[str]:
    versions = ", ".join(_quote(version) for version in job.versions)
    lines = [
        f"  {job.id}:",
        f"    runs-on: {_quote(job.runs_on)}",
        "    strategy:",
        "      matrix:",
        f"        {job.matrix_var}: [{versions}]",
    ]
    if job.services:
        lines.append("    services:")
    for service in job.services:
        lines.append(f"      {service.name}:")
        lines.append(f"        image: {_quote(service.image)}")
        if service.env:
            lines.append("        env:")
            for key, value in service.env:
                lines.append(f"          {key}: {_quote(value)}")
        lines.append("        ports:")
        lines.append(f"          - {_quote(f'{service.port}:{service.port}')}")
        lines.append(f"        options: {_quote(service.options)}")
    if job.env:
        lines.append("    env:")
        for key, value in job.env:
            lines.append(f"      {key}: {_quote(value)}")
    lines.append("    steps:")
    for step in job.steps:
        lines.extend(_step_lines(step))
    return lines
```

Note the two emptiness guards that keep the existing goldens byte-identical: `services:` is emitted only when `job.services` is non-empty, and the job-level `env:` only when `job.env` is non-empty. A service with no container env (redis) emits no `env:` under it — hence the `if service.env:` guard.

- [ ] **Step 5: Add the serviced golden to the regen script and generate it**

In `scripts/sync_action_pins.py`, add to the `goldens` dict:

```python
    "node-postgres.yml": RC(name="ci", stacks={"node": RSC(
        services=(RS(service_id="postgres", version="16", url_env="TEST_DATABASE_URL"),))}),
    "node-redis.yml": RC(name="ci", stacks={"node": RSC(
        services=(RS(service_id="redis", version="7", url_env="REDIS_URL"),))}),
```

and add `ResolvedService as RS` to that script's rigging imports
(`from rigging.config import Config as RC, StackConfig as RSC, ResolvedService as RS, ...`).

Run: `python3 scripts/sync_action_pins.py`
Then confirm ONLY the new golden is new and nothing else moved:

Run: `git status --short`
Expected: `plugins/rigging/tests/golden/node-postgres.yml` and `node-redis.yml` new (`??`), plus your source edits. NO existing golden, NEITHER `.github/workflows/ci.yml` nor `security.yml`, modified. If any existing rendered artifact moved, STOP and report — the guard blocks that emit an empty `services:`/`env:` on a service-less job.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests -q`
Expected: all pass, including the nine byte-identity goldens and the new serviced golden.

- [ ] **Step 7: Inspect the generated golden by eye**

Read BOTH `plugins/rigging/tests/golden/node-postgres.yml` and `node-redis.yml` and confirm each matches the "Render order" block in this plan exactly (redis has no `env:` under the service and a quoted `--health-cmd`) — `services:` → postgres image/env/ports/options → job `env:` with the composed URL → `steps:`. A wrong health-cmd or a mis-indented block passes byte-identity against itself; only a human read catches it here.

- [ ] **Step 8: Commit**

```bash
git add plugins/rigging/rigging/plan.py plugins/rigging/rigging/render.py \
        scripts/sync_action_pins.py plugins/rigging/tests/test_plan.py \
        plugins/rigging/tests/test_render.py plugins/rigging/tests/test_injection.py \
        plugins/rigging/tests/golden/node-postgres.yml \
        plugins/rigging/tests/golden/node-redis.yml
git commit -m "feat(rigging): render service containers and the connection-URL env (#26)"
```

---

### Task 4: Detection passthrough, skill docs, changelog — and close #26

**Files:**
- Modify: `plugins/rigging/skills/init/SKILL.md`
- Modify: `CHANGELOG.md`
- (Check only) `plugins/rigging/rigging/scaffold.py` — see Step 1.

- [ ] **Step 1: Decide the propose_config posture (check, likely no change)**

Like `testCommand`, a service is a hand-authored declaration, not something `rigging:init` can detect (nothing in a repo reliably says "these tests need Postgres"). Confirm `scaffold.propose_config` does NOT need a `services` signal: read `scaffold.py` and verify no signal work is required. If confirmed, make NO change to `scaffold.py`/`SIGNAL_KEYS` and note it. If you find a reason init must emit it, STOP and report — that is a design change, not this task.

- [ ] **Step 2: Document `services` in the init skill**

In `plugins/rigging/skills/init/SKILL.md`, near the `testCommand` section added last increment, add a `services` subsection with this content (adapt formatting to match the file):

> - **`services`** (optional, per stack): service containers the job runs
>   alongside its tests, as `{"<service>": {"version": "<tag>", "urlEnv":
>   "<ENV_NAME>"}}`. Supported services: `postgres`, `mysql`, `redis`. rigging
>   owns the image, port, credentials, and — crucially — the health check, so
>   the job waits for the container to be ready instead of racing it. The repo
>   picks only the image `version` (a major tag, e.g. `"16"`) and the `urlEnv`
>   the connection URL is exposed in (a plain env var name); rigging composes
>   the URL from its own credentials and sets it at the job level, so every
>   step sees it. `init` does not write this — declare it by hand when a suite
>   needs a live database.

- [ ] **Step 3: Add the changelog entry**

Under `## [Unreleased]` → `### Added` in `CHANGELOG.md`:

```markdown
- **`rigging` jobs can run a database alongside their tests.** `.rigging.json`'s
  per-stack config gained `services` — `postgres`, `mysql`, or `redis` — as
  `{"postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}`. rigging owns
  the image tag, port, credentials, and the **health check** (so the job waits
  for readiness instead of racing the container and flaking), and composes the
  connection URL from its own credentials into the job-level env var the repo
  names. Images are pinned by major tag, not digest — an ephemeral test fixture
  on a private network has a different threat model from an Action that runs
  with the workflow token. This is the third and final increment of #26: a repo
  needing a live Postgres can now use rigging end to end.
```

- [ ] **Step 4: Verify the changelog gate and full suite**

Run: `python3 scripts/check_changelog.py $(git merge-base main HEAD) HEAD`
Expected: "gained content — ok".
Run: `python3 -m pytest -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add plugins/rigging/skills/init/SKILL.md CHANGELOG.md
git commit -m "docs(rigging): document services; close #26 (#26)"
```

---

## Notes for the executor

- **This closes #26** (all three increments landed). The PR body should say "Closes #26".
- **`services` does not flow through `propose_config`** — like `testCommand`, it is a manual declaration. Do not wire it into `scaffold.py`/`SIGNAL_KEYS`.
- **The health commands are the one thing tests cannot validate** (Global Constraints). Task 1's external verification and Task 3 Step 7's by-eye golden read are the substitutes. Do not skip them.
- **Byte-identity of the nine existing goldens** is the refactor's safety net; Task 3 Step 5 is the gate.
- **#30 relevance:** these service images are tag-pinned by design and have no Dependabot path — but tags self-update, so unlike the trufflehog SHA pin they do not go stale. Note in the PR that this does not enlarge #30.
