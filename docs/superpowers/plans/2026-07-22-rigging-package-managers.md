# rigging Package Managers Implementation Plan (increment 1 of 3)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teach rigging to drive pnpm, yarn (both majors), and bun, instead of refusing every JavaScript repo that is not plain npm.

**Architecture:** rigging is a pure pipeline — `config.load_config` -> `plan.build_plan` -> `render.render` — driven by a data registry in `stacks.py`. Today the node `StackSpec` hardcodes `npm ci` / `npm test`, and `FOREIGN_NODE_LOCKFILES` exists solely to *refuse* other managers. This inverts that: a `NODE_PACKAGE_MANAGERS` registry says how to drive each one, detection selects which, and the choice is written into `.rigging.json` so config still fully determines output.

**Tech Stack:** Python 3.9+, stdlib only (`shlex` is the one new import), pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-22-rigging-js-toolchains-design.md` (increment 1 only; increments 2 and 3 get their own plans)

## Global Constraints

- **Engine purity.** No `os`, `subprocess`, or networking may enter any module under `plugins/rigging/rigging/`. An AST test enforces this repo-wide. `shlex` and `json` are stdlib and permitted.
- **Stdlib only.** No new dependencies, in engine or tests.
- **The three existing goldens must not move.** `plugins/rigging/tests/golden/node.yml`, `python.yml`, and `polyglot.yml` are byte-identity assertions. An npm repo's output must be byte-identical after every task in this plan. If one changes, the change is wrong.
- **Action refs are SHA pins.** `owner/repo@<40-hex>` with a version tag in a sibling field. An existing test rejects a `@v4`-style ref.
- **Rendered output must never contain `${{ github.* }}`, and no `run:` block may contain `${{`.** Existing tests enforce both. Note the one legitimate `${{ matrix.node }}` in a `with:` block — that is pre-existing and stays.
- **Unknown config keys raise `ConfigError`; unknown signal keys raise `ValueError`.** Both name the offending key.
- **Run from the repo root**, `/Users/steveharmeyer/Development/submtd/shipyard`. Full suite: `python3 -m pytest -q`. It is at **1354 passed** before Task 1.
- **Exact pins to use:**
  - `pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271` version `v6.0.9`
  - `oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6` version `v2.2.0`

### A note on expected test counts

Each task below states an expected count. **Treat it as a prediction, not a contract.** A previous plan in this repo stated counts that proved wrong because pre-existing tests encoded assumptions the change invalidated — five tests used a string as a stand-in for an *invalid* value that the change made valid.

That is likely here too: tests currently assert that pnpm/yarn/bun repos are *refused*. Those assertions become false by design.

So: if your count differs, do not force it to match. Work out which pre-existing tests changed meaning, fix them minimally, and report exactly which ones and why in your report. A test that has to change is a signal worth surfacing, not noise to suppress.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `plugins/rigging/rigging/config.py` | Load and validate `.rigging.json` | Add `StackConfig`; add `packageManager` key |
| `plugins/rigging/rigging/stacks.py` | Stack + manager registries | Add `PackageManager`, `NODE_PACKAGE_MANAGERS`; delete `FOREIGN_NODE_LOCKFILES` |
| `plugins/rigging/rigging/plan.py` | Config -> plan | Build node steps from the selected manager |
| `plugins/rigging/rigging/detect.py` | Repo-marker detection | Resolve the manager; refuse the ambiguous cases |
| `plugins/rigging/rigging/scaffold.py` | Signals -> `.rigging.json` | Accept and validate the `packageManager` signal |
| `plugins/rigging/tests/golden/node-*.yml` | Byte-identity pins | Create four |
| `plugins/rigging/skills/init/SKILL.md` | Operator instructions | Rewrite section 2a |
| `CHANGELOG.md` | Release notes | New `Unreleased` entry |

`render.py` is **not** modified — it already renders whatever `Step`s the plan hands it.

---

### Task 1: `StackConfig`, a pure refactor

`Config.stacks` is `dict[str, tuple[str, ...]]` today. Increments 1-3 each add a per-stack key, so this introduces the structure that holds them. **No behaviour changes in this task** — it exists so that "output did not move" is proven by a commit that adds no feature.

**Files:**
- Modify: `plugins/rigging/rigging/config.py`
- Modify: `plugins/rigging/rigging/plan.py` (`build_plan` only)
- Test: `plugins/rigging/tests/test_config.py`, `plugins/rigging/tests/test_render.py`

**Interfaces:**
- Produces: `config.StackConfig`, a frozen dataclass with `versions: tuple[str, ...]`. `Config.stacks` becomes `dict[str, StackConfig]`. Consumed by every later task.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/rigging/tests/test_config.py`:

```python
def test_stacks_values_are_stack_configs(tmp_path):
    """The per-stack container the next three increments hang their keys
    off. Today it holds only versions."""
    from rigging.config import StackConfig

    cfg = load_config(write(tmp_path, {"stacks": {"python": {"versions": ["3.12"]}}}))
    assert cfg.stacks["python"] == StackConfig(versions=("3.12",))


def test_stack_config_is_frozen():
    from rigging.config import StackConfig

    sc = StackConfig(versions=("3.12",))
    with pytest.raises(Exception):
        sc.versions = ("3.11",)


def test_registry_defaults_still_fill_in_absent_versions(tmp_path):
    """A stack with `{}` still takes its registry default -- the refactor
    must not have moved where defaults come from."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].versions == REGISTRY["node"].default_versions
```

Add to that file's imports if not already present:

```python
from rigging.stacks import REGISTRY
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -k stack_config -v`

Expected: FAIL — `ImportError: cannot import name 'StackConfig'`.

- [ ] **Step 3: Add `StackConfig` and use it**

In `plugins/rigging/rigging/config.py`, add above `Config`:

```python
@dataclass(frozen=True)
class StackConfig:
    """One stack's settings.

    A dataclass rather than a bare versions tuple because the next two
    increments each add a per-stack key (a custom test command, then service
    containers). Parallel dicts keyed by stack id would be three chances for
    the same repo's settings to desync; one container per stack cannot.
    """

    versions: tuple[str, ...]
```

Change `Config.stacks`:

```python
    stacks: dict[str, StackConfig]
```

In `load_config`, change the `resolved` annotation and the assignment at the end of the per-stack loop. Find where it currently assigns the versions tuple into `resolved[stack_id]` and wrap it:

```python
    resolved: dict[str, StackConfig] = {}
```

```python
        resolved[stack_id] = StackConfig(versions=versions)
```

- [ ] **Step 4: Update the one consumer**

In `plugins/rigging/rigging/plan.py`, `build_plan` currently unpacks `cfg.stacks.items()` as `(stack_id, versions)`. Change it to:

```python
def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, stack_cfg.versions)
        for stack_id, stack_cfg in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
```

`_build_job`'s signature is unchanged.

- [ ] **Step 5: Fix any pre-existing tests that construct `Config` directly**

Search for them: `grep -rn "Config(" plugins/rigging/tests/`

Any test building `Config(name=..., stacks={"python": ("3.12",)})` must become `stacks={"python": StackConfig(versions=("3.12",))}`. Change only the construction; leave every assertion alone. If an assertion reads `cfg.stacks["python"] == ("3.12",)`, it becomes `cfg.stacks["python"].versions == ("3.12",)`.

- [ ] **Step 6: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1357 passed` (1354 + 3 new), with any pre-existing tests mechanically updated per Step 5. **The three goldens must still pass** — this task renders identical output.

- [ ] **Step 7: Commit**

```bash
git add plugins/rigging/
git commit -m "refactor(rigging): per-stack config becomes a StackConfig dataclass

No behaviour change: identical rendered output, goldens untouched. The next
three increments each add a per-stack key, and parallel dicts keyed by stack
id would be three chances for one repo's settings to desync.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: The `PackageManager` registry, npm only

Introduces the registry and argv-based steps with exactly one entry, so npm's output is proven unchanged before any new manager exists.

**Files:**
- Modify: `plugins/rigging/rigging/stacks.py`
- Modify: `plugins/rigging/rigging/plan.py`
- Test: `plugins/rigging/tests/test_stacks.py`, `plugins/rigging/tests/test_plan.py`, `plugins/rigging/tests/test_render.py`

**Interfaces:**
- Produces:
  - `stacks.PackageManager`, frozen dataclass: `id: str`, `lockfiles: tuple[str, ...]`, `setup_steps: tuple[Step, ...] = ()`, `install: tuple[str, ...]`, `test: tuple[str, ...]`
  - `stacks.NODE_PACKAGE_MANAGERS: dict[str, PackageManager]`, with `"npm"` only
  - `stacks.DEFAULT_NODE_PACKAGE_MANAGER: str = "npm"`
  - `plan.render_argv(argv: tuple[str, ...]) -> str` — shell-quotes each element and joins with a single space
- Consumes: `StackConfig` from Task 1.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/rigging/tests/test_stacks.py`:

```python
def test_npm_manager_is_registered():
    from rigging.stacks import DEFAULT_NODE_PACKAGE_MANAGER, NODE_PACKAGE_MANAGERS

    assert DEFAULT_NODE_PACKAGE_MANAGER == "npm"
    npm = NODE_PACKAGE_MANAGERS["npm"]
    assert npm.lockfiles == ("package-lock.json",)
    assert npm.install == ("npm", "ci")
    assert npm.test == ("npm", "test")
    assert npm.setup_steps == ()


def test_manager_ids_match_their_keys():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for key, manager in NODE_PACKAGE_MANAGERS.items():
        assert manager.id == key


def test_node_spec_no_longer_carries_its_own_steps():
    """The node stack's steps now come from the selected manager. A leftover
    `steps` tuple would silently win or silently be ignored -- either way it
    would be a second, drifting source of truth."""
    assert REGISTRY["node"].steps == ()


def test_python_spec_still_carries_its_own_steps():
    """Only node is manager-driven. Python's steps are multi-line shell and
    stay exactly where they were."""
    assert REGISTRY["python"].steps
```

Append to `plugins/rigging/tests/test_plan.py`:

```python
def test_render_argv_leaves_simple_words_unquoted():
    """npm's output must be byte-identical, so the common case has to render
    without quotes."""
    from rigging.plan import render_argv

    assert render_argv(("npm", "ci")) == "npm ci"


def test_render_argv_quotes_what_the_shell_would_otherwise_read():
    from rigging.plan import render_argv

    assert render_argv(("a", "b c")) == "a 'b c'"
    assert render_argv(("a", "b;c")) == "a 'b;c'"
    assert render_argv(("a", "$HOME")) == "a '$HOME'"


def test_node_job_steps_come_from_the_manager():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("20",))})
    steps = build_plan(cfg).jobs[0].steps
    assert [s.run for s in steps if s.run] == ["npm ci", "npm test"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_stacks.py -k manager -v`

Expected: FAIL — `ImportError: cannot import name 'NODE_PACKAGE_MANAGERS'`.

- [ ] **Step 3: Add the registry**

In `plugins/rigging/rigging/stacks.py`, add after `StackSpec` and before `REGISTRY`:

```python
@dataclass(frozen=True)
class PackageManager:
    """How to drive one JavaScript package manager in CI.

    Install and test are argv TUPLES rather than shell strings, and that is
    deliberate: increment 2 lets a repo supply its own test command, and an
    argv array is the shape that makes shell metacharacters inert. Keeping
    the registry's own defaults in the same shape means user-supplied and
    built-in commands travel one rendering path, so neither can acquire
    quoting behaviour the other lacks.
    """

    id: str
    #: Root-level lockfiles that prove this manager is in charge. Several
    #: for bun, which has shipped two names.
    lockfiles: tuple[str, ...]
    install: tuple[str, ...]
    test: tuple[str, ...]
    #: Extra steps this manager needs before `setup-node` runs -- installing
    #: the manager itself. Empty for npm and yarn, which ship with node.
    setup_steps: tuple[Step, ...] = ()
```

Replace the node entry's `steps=(Step(run="npm ci"), Step(run="npm test"))` with `steps=()`, and delete `NODE_PACKAGE_MANAGER` and `FOREIGN_NODE_LOCKFILES` along with their comment blocks. Add after `STACK_IDS`:

```python
#: The manager assumed when a repo has a package.json and no other signal.
#: That is simply what an npm repo looks like: npm ships with node, so the
#: absence of any other manager's marker is itself the signal.
DEFAULT_NODE_PACKAGE_MANAGER: str = "npm"

#: How to drive each JavaScript package manager. This replaces the old
#: FOREIGN_NODE_LOCKFILES table, which existed only to say "we cannot drive
#: this" -- the same lockfiles now say WHICH manager to drive.
#:
#: It lives here, beside the node StackSpec, for the reason that table did:
#: these commands are a property of the node job, and whoever changes how
#: that job works has to walk past them.
NODE_PACKAGE_MANAGERS: dict[str, PackageManager] = {
    "npm": PackageManager(
        id="npm",
        lockfiles=("package-lock.json",),
        install=("npm", "ci"),
        test=("npm", "test"),
    ),
}
```

- [ ] **Step 4: Build node's steps from the manager**

In `plugins/rigging/rigging/plan.py`, add `import shlex` at the top with the other stdlib imports, then add above `_build_job`:

```python
def render_argv(argv: tuple[str, ...]) -> str:
    """Render an argv tuple as one shell line, quoting each element.

    `shlex.quote` is what makes a metacharacter inert, but note what it does
    NOT do: GitHub substitutes `${{ ... }}` at the YAML layer, before any
    shell sees the line, so quoting is no defence against an Actions
    expression. That is rejected at validation instead -- quoting handles the
    shell, and the shell is not the only reader of this string.
    """
    return " ".join(shlex.quote(part) for part in argv)


def _manager_steps(stack_id: str, manager_id: str):
    """The setup and run steps contributed by a stack's package manager.

    Returns `((), ())` for a stack that has no manager concept -- today every
    stack but node.
    """
    if stack_id != "node":
        return (), ()
    manager = stacks.NODE_PACKAGE_MANAGERS[manager_id]
    runs = (
        stacks.Step(run=render_argv(manager.install)),
        stacks.Step(run=render_argv(manager.test)),
    )
    return manager.setup_steps, runs
```

Change `_build_job` to take the manager and place the manager's setup steps **before** `setup-node`:

```python
def _build_job(stack_id: str, versions: tuple[str, ...],
               manager_id: str = stacks.DEFAULT_NODE_PACKAGE_MANAGER) -> Job:
    spec = stacks.REGISTRY[stack_id]
    setup_step = stacks.Step(
        uses=spec.setup_uses,
        uses_version=spec.setup_uses_version,
        with_={spec.setup_with_key: "${{ matrix.%s }}" % spec.matrix_var},
    )
    # The manager's own installer runs before setup-node, matching pnpm's
    # documented order. Nothing here depends on it today (no dependency
    # caching is configured), but the documented order is the one that stays
    # correct if caching is ever added.
    manager_setup, manager_runs = _manager_steps(stack_id, manager_id)
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        matrix_var=spec.matrix_var,
        versions=versions,
        steps=(CHECKOUT_STEP, *manager_setup, setup_step, *spec.steps, *manager_runs),
    )
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1364 passed` (1357 + 7 new). **The `node.yml` and `polyglot.yml` goldens must still pass byte-for-byte** — this is the whole point of shipping npm alone. If either fails, `render_argv` or the step ordering is wrong; stop and report BLOCKED rather than editing the golden.

- [ ] **Step 6: Commit**

```bash
git add plugins/rigging/
git commit -m "feat(rigging): node's steps come from a package-manager registry

npm only, so identical output proves the plumbing before any new manager
exists. Install and test are argv tuples: increment 2 lets a repo supply its
own test command, and argv is the shape that makes metacharacters inert.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: The `packageManager` config key

**Files:**
- Modify: `plugins/rigging/rigging/config.py`
- Modify: `plugins/rigging/rigging/plan.py` (`build_plan`)
- Test: `plugins/rigging/tests/test_config.py`, `plugins/rigging/tests/test_plan.py`

**Interfaces:**
- Consumes: `StackConfig` (Task 1), `NODE_PACKAGE_MANAGERS` (Task 2).
- Produces: `StackConfig.package_manager: Optional[str] = None`, and `STACK_KEYS` gains `"packageManager"`.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/rigging/tests/test_config.py`:

```python
def test_package_manager_defaults_to_none(tmp_path):
    """None means "unset", which build_plan reads as npm. Not written out as
    a default so a config authored today does not freeze one answer in."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].package_manager is None


def test_package_manager_is_read(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": "pnpm"}}}))
    assert cfg.stacks["node"].package_manager == "pnpm"


@pytest.mark.parametrize("bad", ["npm7", "", "NPM", 5, ["npm"], None])
def test_unknown_package_manager_raises_naming_the_field(tmp_path, bad):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"packageManager": bad}}}))
    assert "packageManager" in str(e.value)


def test_package_manager_rejected_for_a_stack_that_has_no_managers(tmp_path):
    """Python has no package-manager concept, so setting one is a user
    believing they configured something that is silently discarded -- the
    same failure the unknown-key check exists to prevent."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"python": {"packageManager": "npm"}}}))
    assert "packageManager" in str(e.value)
```

Append to `plugins/rigging/tests/test_plan.py`:

```python
def test_configured_manager_drives_the_node_job():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={
        "node": StackConfig(versions=("20",), package_manager="npm")})
    assert [s.run for s in build_plan(cfg).jobs[0].steps if s.run] == [
        "npm ci", "npm test"]


def test_unset_manager_falls_back_to_the_default():
    from rigging.config import Config, StackConfig

    cfg = Config(name="ci", stacks={"node": StackConfig(versions=("20",))})
    assert [s.run for s in build_plan(cfg).jobs[0].steps if s.run] == [
        "npm ci", "npm test"]
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -k package_manager -v`

Expected: FAIL — `ConfigError: unknown key(s) packageManager` for the reading test, `AttributeError` for the default test.

- [ ] **Step 3: Add the field and its validator**

In `plugins/rigging/rigging/config.py`, extend `STACK_KEYS`:

```python
STACK_KEYS = frozenset({"versions", "packageManager"})
```

Add the field to `StackConfig`, after `versions`:

```python
    #: Which JavaScript package manager drives this stack's job, or None to
    #: take the registry default. Only meaningful for `node`; validated
    #: against stacks.NODE_PACKAGE_MANAGERS rather than a free string, so an
    #: unknown value fails here instead of rendering a workflow that runs a
    #: command the runner does not have.
    package_manager: Optional[str] = None
```

Add the validator beside `_valid_versions`:

```python
def _valid_package_manager(value, stack_id):
    """Validate an optional `packageManager` for one stack.

    Rejects it outright for a stack with no manager concept (today, anything
    but node) rather than accepting a setting that would do nothing. That is
    the same reasoning the unknown-key check applies one level up: a silently
    discarded setting leaves the user believing they configured something.
    """
    if value is None:
        return None
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
```

In `load_config`'s per-stack loop, call it and pass the result into `StackConfig`:

```python
        package_manager = _valid_package_manager(
            stack_value.get("packageManager"), stack_id)
        resolved[stack_id] = StackConfig(versions=versions,
                                         package_manager=package_manager)
```

- [ ] **Step 4: Use it in the plan**

In `plugins/rigging/rigging/plan.py`, change `build_plan`:

```python
def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, stack_cfg.versions,
                   stack_cfg.package_manager or stacks.DEFAULT_NODE_PACKAGE_MANAGER)
        for stack_id, stack_cfg in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1374 passed` (1364 + 10 new; the parametrized test contributes 6). Goldens unchanged — no config in the repo sets the new key.

- [ ] **Step 6: Commit**

```bash
git add plugins/rigging/
git commit -m "feat(rigging): .rigging.json gains stacks.<id>.packageManager

Validated against the manager registry, and refused outright for a stack
with no manager concept rather than silently discarded.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: pnpm, yarn (both majors), and bun

**Files:**
- Modify: `plugins/rigging/rigging/stacks.py`
- Create: `plugins/rigging/tests/golden/node-pnpm.yml`, `node-yarn1.yml`, `node-yarn-berry.yml`, `node-bun.yml`
- Test: `plugins/rigging/tests/test_stacks.py`, `plugins/rigging/tests/test_render.py`

**Interfaces:**
- Consumes: `PackageManager` and `NODE_PACKAGE_MANAGERS` (Task 2), the `packageManager` config key (Task 3).
- Produces: registry entries `"pnpm"`, `"yarn1"`, `"yarn-berry"`, `"bun"`.

- [ ] **Step 1: Add the four entries**

In `plugins/rigging/rigging/stacks.py`, add to `NODE_PACKAGE_MANAGERS` after `npm`:

```python
    "pnpm": PackageManager(
        id="pnpm",
        lockfiles=("pnpm-lock.yaml",),
        install=("pnpm", "install", "--frozen-lockfile"),
        test=("pnpm", "test"),
        # pnpm does not ship with node, so the runner has to install it.
        setup_steps=(Step(
            uses="pnpm/action-setup@0ebf47130e4866e96fce0953f49152a61190b271",
            uses_version="v6.0.9",
        ),),
    ),
    # Yarn 1 and Yarn 2+ are two toolchains sharing one lockfile name, and
    # their install flags are mutually incompatible: --frozen-lockfile is an
    # error on berry, --immutable is an error on classic. They are separate
    # registry entries because they are separate tools, not one tool with a
    # version field -- a single entry would need a conditional in the
    # renderer, which is exactly the drift this registry exists to prevent.
    "yarn1": PackageManager(
        id="yarn1",
        lockfiles=("yarn.lock",),
        install=("yarn", "install", "--frozen-lockfile"),
        test=("yarn", "test"),
    ),
    "yarn-berry": PackageManager(
        id="yarn-berry",
        lockfiles=("yarn.lock",),
        install=("yarn", "install", "--immutable"),
        test=("yarn", "test"),
    ),
    "bun": PackageManager(
        id="bun",
        # bun has shipped two lockfile names: the original binary `bun.lockb`
        # and the newer text `bun.lock`. A repo may carry either depending on
        # when, and with which bun, it was last installed.
        lockfiles=("bun.lockb", "bun.lock"),
        install=("bun", "install", "--frozen-lockfile"),
        # `bun run test` rather than `bun test`: the latter runs bun's own
        # test runner, while every other entry here runs the repo's `test`
        # script. A repo using vitest under bun would otherwise silently run
        # a different suite than it does locally.
        test=("bun", "run", "test"),
        setup_steps=(Step(
            uses="oven-sh/setup-bun@0c5077e51419868618aeaa5fe8019c62421857d6",
            uses_version="v2.2.0",
        ),),
    ),
```

- [ ] **Step 2: Write the failing golden tests**

Append to `plugins/rigging/tests/test_render.py`:

```python
@pytest.mark.parametrize("manager,golden", [
    ("pnpm", "node-pnpm.yml"),
    ("yarn1", "node-yarn1.yml"),
    ("yarn-berry", "node-yarn-berry.yml"),
    ("bun", "node-bun.yml"),
])
def test_each_manager_matches_its_golden(tmp_path, manager, golden):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": manager}}}))
    assert render(build_plan(cfg)) == read_golden(golden)


def test_npm_goldens_did_not_move(tmp_path):
    """Adding four managers must not perturb the one that already worked."""
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert render(build_plan(cfg)) == read_golden("node.yml")


def test_yarn_majors_render_incompatible_flags(tmp_path):
    """The whole reason they are separate entries. If these two ever render
    the same install line, one of them is broken."""
    def install_line(manager):
        cfg = load_config(write(tmp_path, {
            "stacks": {"node": {"packageManager": manager}}}))
        return [l for l in render(build_plan(cfg)).splitlines()
                if "yarn install" in l][0]

    assert "--frozen-lockfile" in install_line("yarn1")
    assert "--immutable" in install_line("yarn-berry")


def test_manager_setup_runs_before_setup_node(tmp_path):
    """pnpm and bun install the manager itself; doing that after setup-node
    would work today but breaks the moment dependency caching is added."""
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"packageManager": "pnpm"}}}))
    out = render(build_plan(cfg))
    assert out.index("pnpm/action-setup") < out.index("actions/setup-node")
```

Append to `plugins/rigging/tests/test_stacks.py`:

```python
def test_every_manager_setup_step_is_sha_pinned():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager in NODE_PACKAGE_MANAGERS.values():
        for step in manager.setup_steps:
            assert _SHA_PINNED_REF_RE.fullmatch(step.uses), step.uses
            assert step.uses_version


def test_no_manager_command_embeds_an_expression():
    """Registry commands become `run:` lines. An expression here would be
    interpolated by Actions before any shell saw it."""
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    for manager in NODE_PACKAGE_MANAGERS.values():
        for part in manager.install + manager.test:
            assert "${{" not in part


def test_bun_runs_the_repos_test_script_not_buns_runner():
    from rigging.stacks import NODE_PACKAGE_MANAGERS

    assert NODE_PACKAGE_MANAGERS["bun"].test == ("bun", "run", "test")
```

- [ ] **Step 3: Run to verify the goldens fail**

Run: `python3 -m pytest plugins/rigging/tests/test_render.py -k manager -v`

Expected: FAIL — `FileNotFoundError` for the four golden files.

- [ ] **Step 4: Generate the goldens, then read every one before committing**

```bash
cd /Users/steveharmeyer/Development/submtd/shipyard/plugins/rigging
for m in pnpm yarn1 yarn-berry bun; do
  python3 -c "
import json, pathlib, sys, tempfile
sys.path.insert(0, '.')
from rigging.config import load_config
from rigging.plan import build_plan
from rigging.render import render
d = pathlib.Path(tempfile.mkdtemp())
(d/'.rigging.json').write_text(json.dumps({'stacks': {'node': {'packageManager': '$m'}}}))
pathlib.Path('tests/golden/node-$m.yml').write_text(render(build_plan(load_config(d))))
"
done
cat tests/golden/node-pnpm.yml tests/golden/node-bun.yml
```

**Do not skip reading them.** A golden generated from the implementation only proves the implementation is deterministic, not that it is right. Check each one against what a working GitHub Actions workflow needs: `pnpm/action-setup` appears before `actions/setup-node`; the install and test lines are the manager's real commands; no `env:` block appeared; every `uses:` carries its version comment.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1385 passed` (1374 + 11 new; the parametrized golden test contributes 4). `node.yml`, `python.yml`, and `polyglot.yml` must all still pass.

- [ ] **Step 6: Commit**

```bash
git add plugins/rigging/
git commit -m "feat(rigging): drive pnpm, yarn 1, yarn berry, and bun

Yarn's two majors are separate registry entries because their install flags
are mutually incompatible, not one entry with a version field -- a single
entry would need a conditional in the renderer.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Detection selects the manager, and refuses when it cannot

The task that replaces refusal with selection. `detect.py` currently has `_declared_package_manager` and `_node_unsupported_reason`, which exist to refuse; they become the selector.

**Files:**
- Modify: `plugins/rigging/rigging/detect.py`
- Modify: `plugins/rigging/rigging/scaffold.py`
- Test: `plugins/rigging/tests/test_detect.py`, `plugins/rigging/tests/test_scaffold.py`

**Interfaces:**
- Consumes: `NODE_PACKAGE_MANAGERS`, `DEFAULT_NODE_PACKAGE_MANAGER` (Task 2); the `packageManager` config key (Task 3); the four entries (Task 4).
- Produces:
  - `detect.node_package_manager(root) -> tuple[Optional[str], Optional[str]]` — `(manager_id, reason)`. Exactly one is non-None: a manager id on success, or a refusal reason on failure.
  - `scaffold.propose_config` accepts a `packageManagers` signal, `dict[str, str]` of stack id -> manager id.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/rigging/tests/test_detect.py`:

```python
from rigging.detect import node_package_manager


@pytest.mark.parametrize("lockfile,expected", [
    ("package-lock.json", "npm"),
    ("pnpm-lock.yaml", "pnpm"),
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
])
def test_lockfile_selects_the_manager(tmp_path, lockfile, expected):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("")
    assert node_package_manager(tmp_path) == (expected, None)


def test_bare_package_json_is_npm(tmp_path):
    """npm ships with node, so no other manager's marker IS the signal."""
    (tmp_path / "package.json").write_text("{}")
    assert node_package_manager(tmp_path) == ("npm", None)


def test_package_manager_field_selects_when_no_lockfile(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    assert node_package_manager(tmp_path) == ("pnpm", None)


@pytest.mark.parametrize("declared,expected", [
    ("yarn@1.22.19", "yarn1"),
    ("yarn@3.6.4", "yarn-berry"),
    ("yarn@4.0.0", "yarn-berry"),
])
def test_yarn_major_selects_the_toolchain(tmp_path, declared, expected):
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": declared}))
    (tmp_path / "yarn.lock").write_text("")
    assert node_package_manager(tmp_path) == (expected, None)


def test_yarn_lockfile_without_a_declared_major_is_refused(tmp_path):
    """Yarn 1 takes --frozen-lockfile and berry takes --immutable; each is an
    error on the other. yarn.lock does not say which, and guessing produces a
    workflow that dies on its install step -- the exact outcome the refusal
    machinery exists to prevent."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "yarn.lock" in reason
    assert "packageManager" in reason


def test_two_manager_lockfiles_are_refused_naming_both(tmp_path):
    """Mid-migration or a stale file. Either answer is as likely wrong as
    right, so precedence would be a coin flip wearing a rule's clothing."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "pnpm-lock.yaml" in reason and "yarn.lock" in reason


def test_lockfile_disagreeing_with_declared_manager_is_refused(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "pnpm" in reason and "yarn.lock" in reason


def test_unparseable_package_json_is_not_a_refusal(tmp_path):
    """A package.json we cannot read is not evidence of anything. With a
    lockfile present the lockfile still decides."""
    (tmp_path / "package.json").write_text("{ not json")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert node_package_manager(tmp_path) == ("pnpm", None)


def test_no_package_json_reports_nothing(tmp_path):
    assert node_package_manager(tmp_path) == (None, None)
```

Ensure `import json` and `import pytest` are present at the top of that file.

Append to `plugins/rigging/tests/test_scaffold.py`:

```python
def test_package_managers_signal_reaches_the_config(tmp_path):
    from rigging.config import load_config

    cfg = propose_config({"stacks": ["node"],
                          "packageManagers": {"node": "pnpm"}})
    assert cfg["stacks"]["node"]["packageManager"] == "pnpm"
    (tmp_path / ".rigging.json").write_text(json.dumps(cfg))
    assert load_config(tmp_path).stacks["node"].package_manager == "pnpm"


def test_absent_package_managers_signal_omits_the_key():
    assert propose_config({"stacks": ["node"]})["stacks"]["node"] == {}


def test_unknown_manager_in_the_signal_is_rejected():
    with pytest.raises(ValueError, match="packageManagers"):
        propose_config({"stacks": ["node"], "packageManagers": {"node": "npm7"}})


def test_manager_for_a_stack_not_being_proposed_is_rejected():
    """A signal naming a stack that is not in `stacks` is a caller mistake,
    and dropping it silently would leave nothing on disk to notice by."""
    with pytest.raises(ValueError, match="packageManagers"):
        propose_config({"stacks": ["python"], "packageManagers": {"node": "pnpm"}})
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_detect.py -k package_manager -v`

Expected: FAIL — `ImportError: cannot import name 'node_package_manager'`.

- [ ] **Step 3: Rewrite detection as selection**

In `plugins/rigging/rigging/detect.py`, keep `_declared_package_manager` as-is (it already parses the `packageManager` field and returns None on any failure). Add beneath it:

```python
def _declared_yarn_major(root):
    """Return 1 or 2 for a declared yarn version, or None if undeclared.

    2 means "berry or later" -- every major from 2 up takes the same
    `--immutable` flag, so they need no further distinction.
    """
    path = root / "package.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    declared = data.get("packageManager")
    if not isinstance(declared, str) or "@" not in declared:
        return None
    name, _, version = declared.partition("@")
    if name.strip().lower() != "yarn":
        return None
    major = version.strip().split(".", 1)[0]
    if not major.isdigit():
        return None
    return 1 if int(major) == 1 else 2


def _yarn_id(root):
    """Which yarn toolchain, or None when it cannot be determined."""
    major = _declared_yarn_major(root)
    if major is None:
        return None
    return "yarn1" if major == 1 else "yarn-berry"


def node_package_manager(root):
    """Select the package manager driving this repo, or explain why not.

    Returns `(manager_id, reason)`; exactly one is non-None. `(None, None)`
    means there is no node stack here at all, which is not a refusal.

    Ambiguity is refused rather than resolved by precedence. Two different
    lockfiles at the root means the repo is mid-migration or carrying a stale
    file, and either answer is as likely to be wrong as right -- a wrong guess
    renders a workflow that dies on its install step, which is precisely the
    failure this module was built to prevent.
    """
    root = Path(root)
    if not (root / "package.json").is_file():
        return None, None

    found = {}
    for manager_id, manager in stacks.NODE_PACKAGE_MANAGERS.items():
        for lockfile in manager.lockfiles:
            if (root / lockfile).is_file():
                found.setdefault(lockfile, set()).add(manager_id)

    # yarn1 and yarn-berry share yarn.lock, so one lockfile mapping to both
    # is not ambiguity between managers -- it is one manager whose major is
    # still unknown. Collapse them before counting.
    families = set()
    for lockfile, ids in found.items():
        families.add("yarn" if ids <= {"yarn1", "yarn-berry"} else sorted(ids)[0])

    if len(families) > 1:
        names = ", ".join(sorted(found))
        return None, (
            f"found more than one package manager's lockfile at the repo "
            f"root ({names}). That means this project is mid-migration or "
            f"carrying a stale lockfile, and rigging will not guess which "
            f"one is authoritative -- the wrong guess renders a workflow "
            f"whose install step fails on every run. Remove the lockfile "
            f"that is no longer in use and re-run."
        )

    declared = _declared_package_manager(root)

    if families:
        family = next(iter(families))
        if declared is not None and declared != family:
            lockfile = next(iter(found))
            return None, (
                f"package.json declares `packageManager` as {declared}, but "
                f"the repo root has {lockfile}, which belongs to {family}. "
                f"rigging will not guess which one is authoritative; make "
                f"them agree and re-run."
            )
        if family == "yarn":
            yarn_id = _yarn_id(root)
            if yarn_id is None:
                return None, (
                    "found yarn.lock at the repo root, but nothing says which "
                    "yarn major this project uses. Yarn 1 installs with "
                    "`--frozen-lockfile` and Yarn 2+ with `--immutable`, and "
                    "each flag is an error on the other -- so rigging cannot "
                    "write an install step that works without knowing. Add a "
                    "`packageManager` field to package.json (e.g. "
                    "\"yarn@4.0.0\") and re-run."
                )
            return yarn_id, None
        return family, None

    # No lockfile. The declared field still decides, and a bare package.json
    # means npm: npm ships with node, so no other manager's marker IS the
    # signal.
    if declared == "yarn":
        yarn_id = _yarn_id(root)
        return (yarn_id, None) if yarn_id else (None, (
            "package.json declares yarn as its packageManager, but without a "
            "major version rigging cannot tell whether to install with "
            "`--frozen-lockfile` (Yarn 1) or `--immutable` (Yarn 2+). Pin it "
            "as e.g. \"yarn@4.0.0\" and re-run."
        ))
    if declared is not None and declared in stacks.NODE_PACKAGE_MANAGERS:
        return declared, None
    return stacks.DEFAULT_NODE_PACKAGE_MANAGER, None
```

Then rewrite `_node_unsupported_reason` to delegate, so `unsupported_reasons` keeps its existing contract:

```python
def _node_unsupported_reason(root):
    """Return why rigging cannot drive this repo's node stack, or None."""
    _, reason = node_package_manager(root)
    return reason
```

Delete the old body that referenced `FOREIGN_NODE_LOCKFILES` and `NODE_PACKAGE_MANAGER`.

- [ ] **Step 4: Accept the signal in scaffold**

In `plugins/rigging/rigging/scaffold.py`, extend `SIGNAL_KEYS`:

```python
SIGNAL_KEYS = frozenset({"name", "stacks", "versions", "pushBranches",
                         "unsupported", "packageManagers"})
```

Add the validator beside `_valid_unsupported`:

```python
def _valid_package_managers(signals, stack_ids):
    """Validate the optional `packageManagers` signal.

    A mapping of stack id -> manager id, normally `detect.node_package_manager`'s
    answer. A manager named for a stack that is not being proposed is a caller
    mistake rather than something to drop: a dropped signal here means the
    scaffolded repo silently gets the default manager, and the resulting red
    install step surfaces far from its cause.
    """
    managers = signals.get("packageManagers")
    if managers is None:
        return {}
    if not isinstance(managers, dict):
        raise ValueError(
            f"signals['packageManagers'] must be a dict of stack id -> "
            f"manager id (got {managers!r})."
        )
    for stack_id, manager_id in managers.items():
        if stack_id not in stack_ids:
            raise ValueError(
                f"signals['packageManagers'] names stack {stack_id!r}, which "
                f"is not in signals['stacks']."
            )
        if manager_id not in NODE_PACKAGE_MANAGERS:
            raise ValueError(
                f"signals['packageManagers'][{stack_id!r}] must be one of "
                f"{', '.join(NODE_PACKAGE_MANAGERS)} (got {manager_id!r})."
            )
    return managers
```

In `propose_config`, call the validator immediately after the `versions_by_id` block and before `stacks_out = {}`:

```python
    package_managers = _valid_package_managers(signals, set(stack_ids))
```

The existing loop builds `stacks_out[stack_id]` as either `{"versions": list(versions)}` or `{}`. Both branches need the new key, so add it once after the branch, at the end of the loop body — replacing the current `stacks_out[stack_id] = {"versions": list(versions)}` / `else: stacks_out[stack_id] = {}` pair with:

```python
        entry = {}
        if versions:
            for version in versions:
                if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
                    raise ValueError(
                        f"signals['versions'][{stack_id!r}] entries must be "
                        f"non-empty strings matching {VERSION_RE.pattern} "
                        f"(got {version!r})."
                    )
            entry["versions"] = list(versions)
        if stack_id in package_managers:
            entry["packageManager"] = package_managers[stack_id]
        stacks_out[stack_id] = entry
```

Read the surrounding loop before editing — the `versions` validation above must keep running before anything is written to `entry`, since a bad version must raise rather than produce a partial config.

`scaffold.py` currently imports `from rigging.stacks import STACK_IDS`. Extend that line to `from rigging.stacks import NODE_PACKAGE_MANAGERS, STACK_IDS` and use the bare name in the validator rather than adding a module import.

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: roughly `1408 passed`. **Several pre-existing tests in `test_detect.py` and `test_scaffold.py` assert that pnpm/yarn/bun repos are REFUSED — those assertions are now false by design.** Rewrite each to assert the manager is selected instead, and list every one you changed in your report. Do not delete a test to make a count match.

- [ ] **Step 6: Commit**

```bash
git add plugins/rigging/
git commit -m "feat(rigging): detection selects the package manager

Inverts the refusal table: the same lockfiles that meant 'cannot drive this'
now say which manager to drive. Ambiguity -- two lockfiles, or a lockfile
disagreeing with packageManager -- is still refused, because either answer
would be as likely wrong as right.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: Documentation

**Files:**
- Modify: `plugins/rigging/skills/init/SKILL.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Rewrite SKILL.md section 2a**

The section is titled "2a. Check whether rigging can actually drive what it detected" and currently instructs the agent to call `unsupported_reasons` and refuse. Replace its body with instructions to call the selector:

```markdown
## 2a. Select the JavaScript package manager

*(Fresh-scaffold flow only — run this immediately after section 2 and before
anything is proposed, shown, or written.)*

rigging detects `node` off `package.json` alone, and every JavaScript repo has
one — pnpm, yarn, and bun repos included. Which manager is in charge decides
the install and test steps entirely, and the wrong answer renders a workflow
that fails on its first step of every run.

    python3 -c "import sys, json; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from rigging.detect import node_package_manager; from pathlib import Path; print(json.dumps(node_package_manager(Path('.'))))"

This prints a two-element list, `[manager, reason]`, of which exactly one is
non-null:

- **A manager** (`"npm"`, `"pnpm"`, `"yarn1"`, `"yarn-berry"`, `"bun"`) — pass
  it to `propose_config` as `signals['packageManagers'] = {'node': <manager>}`.
  Say which manager you detected and what told you, rather than presenting it
  as a choice you made.
- **A reason** — this is a **refusal**, not a warning. Print it verbatim; it
  already names the files it found and what the user must do. Do not scaffold
  the node stack. If python is also detected, scaffold that alone and say
  plainly that node was omitted and why.
- **Both null** — there is no `package.json`, so there is no node stack to
  configure. Carry on.

The two refusals are both genuine ambiguity rather than missing support:

- **Two managers' lockfiles at the root.** The repo is mid-migration or
  carrying a stale file. rigging will not pick by precedence, because either
  answer is as likely to be wrong as right.
- **A `yarn.lock` with no declared major.** Yarn 1 installs with
  `--frozen-lockfile`, Yarn 2+ with `--immutable`, and each is an error on the
  other. Adding a `packageManager` field to `package.json` resolves it.
```

- [ ] **Step 2: Update the "not here yet" list in SKILL.md**

Replace the bullet beginning "**pnpm, yarn, and bun steps.**" with:

```markdown
- **package managers beyond npm, pnpm, yarn, and bun** — those four are
  driven; anything else is not detected and not expressible.
```

Leave the "custom test commands" and "service containers" bullets exactly as
they are — both are still true, and both are the next two increments.

- [ ] **Step 3: Add the changelog entry**

Under `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Added

- **`rigging` drives pnpm, yarn, and bun, not just npm.** `.rigging.json`
  gained `stacks.node.packageManager`, and `rigging:init` detects the right
  value rather than asking. The node job's install and test steps now come
  from a package-manager registry instead of being hardcoded to `npm ci` /
  `npm test`, so an npm repo's rendered workflow is byte-identical while a
  pnpm repo finally gets one that works.

  Yarn 1 and Yarn 2+ are separate entries (`yarn1`, `yarn-berry`) because
  their install flags are mutually incompatible — `--frozen-lockfile` is an
  error on berry and `--immutable` is an error on classic — and `yarn.lock`
  does not say which. When nothing declares the major, `rigging:init` refuses
  and says so, rather than guessing and rendering an install step that cannot
  work.

  Two lockfiles at the repo root is likewise a refusal, not a precedence
  rule: it means the project is mid-migration or carrying a stale file, and
  rigging will not pick for you.

### Fixed

- **`rigging:init` no longer refuses every pnpm, yarn, and bun repo.** 0.6.0
  taught it to refuse rather than hand those repos an `npm ci` workflow that
  could never pass. That was right, and it left them with no CI at all. The
  refusal table has been inverted: the same lockfiles that meant "cannot
  drive this" now say which manager to drive.
```

- [ ] **Step 4: Verify and commit**

Run: `python3 -m pytest -q` — the count must be unchanged from Task 5 (documentation only).

```bash
git add plugins/rigging/skills/init/SKILL.md CHANGELOG.md
git commit -m "docs(rigging): document package-manager selection

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `python3 -m pytest -q` passes.
- [ ] `git diff main -- plugins/rigging/tests/golden/node.yml plugins/rigging/tests/golden/python.yml plugins/rigging/tests/golden/polyglot.yml` → **empty**. The most important check here: an npm or python repo's workflow must be untouched.
- [ ] `grep -rn "FOREIGN_NODE_LOCKFILES\|NODE_PACKAGE_MANAGER\b" plugins/rigging/` → only `DEFAULT_NODE_PACKAGE_MANAGER` and `NODE_PACKAGE_MANAGERS` remain; the old refusal table is gone from engine, tests, and docs.
- [ ] Engine purity: `grep -nE "^(import|from) (os|subprocess|socket|urllib|requests)" plugins/rigging/rigging/*.py` → no matches.
- [ ] Every rendered golden contains no `${{` in any `run:` line: `grep -n "run:.*\${{" plugins/rigging/tests/golden/*.yml` → no matches.
- [ ] Open the PR with `keel:finish-work`. It does **not** close #26 — increments 2 and 3 remain.
