# rigging Custom Test Commands — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `.rigging.json` carry `stacks.<id>.testCommand` — an argv array that replaces a stack's (or its node package manager's) default test command — so a repo whose real test command is `turbo run test` isn't stuck with `npm test`.

**Architecture:** `testCommand` is validated at the config layer into `StackConfig.test_command` (a tuple), then resolved in `plan.build_plan` into the single test step that `_build_job` always appends. The registry's own defaults become argv too (python's `python -m pytest` moves out of `StackSpec.steps` into a new `StackSpec.default_test`), so user-supplied and built-in test commands travel exactly one rendering path — `render_argv` + `shlex.quote`. Injection is refused at load time, not quoted around.

**Tech Stack:** Python 3.9+, pytest, stdlib `shlex`/`json`/`re` only. No new dependencies, no new action pins.

## Global Constraints

- **`testCommand` is a hand-authored override, NOT detected by init.** It is added to `config.STACK_KEYS` / `load_config` only. `scaffold.propose_config` and `SIGNAL_KEYS` are **not** touched, so `test_scaffold.py` and the #33 coverage guard are unaffected. Do not add a `testCommand` signal.
- **Two independent injection guarantees, both required:** (1) `render_argv` runs `shlex.quote` on every element, so shell metacharacters are inert; (2) `_valid_test_command` rejects any element containing the literal `${{` — GitHub substitutes `${{ ... }}` at the YAML layer *before* any shell, so quoting is no defence and the value must be refused at load. Also reject any element containing a newline.
- **Not expressible, deliberately:** pipes, redirects, `&&`, subshells, env assignments. An argv array cannot represent them; a repo needing a shell pipeline needs a hand-written workflow. Do not add shell-string support.
- **`testCommand` replaces the *test* argv only** — never the install step or setup steps.
- **The seven existing goldens must stay byte-identical:** `python.yml`, `node.yml`, `polyglot.yml`, `node-pnpm.yml`, `node-yarn1.yml`, `node-yarn-berry.yml`, `node-bun.yml`. That is the proof the refactor changed nothing for repos not using `testCommand`.
- **Unknown config keys stay a hard `ConfigError`.** No escape hatch for hand-editing rendered steps.
- **Engine purity:** stdlib only under `plugins/rigging/rigging/`; `shlex` and `json` are the only stdlib touches. No `os`, `subprocess`, or networking.
- **Goldens are regenerated, never hand-edited.** New golden fixtures are added to `scripts/sync_action_pins.py`'s regen list and produced by running it, so a future pin bump regenerates them too.

---

### Task 1: Config layer — validate `testCommand` into `StackConfig.test_command`

**Files:**
- Modify: `plugins/rigging/rigging/config.py`
- Test: `plugins/rigging/tests/test_config.py`

**Interfaces:**
- Produces: `config.StackConfig.test_command: Optional[tuple[str, ...]]` (None = take the default); `config.EXPRESSION_MARKER = "${{"`; `config._valid_test_command(value, stack_id) -> Optional[tuple[str, ...]]`. `config.STACK_KEYS` gains `"testCommand"`.
- Consumes: existing `ConfigError`, `CONFIG_NAME`, `StackConfig`, `load_config`.

- [ ] **Step 1: Write the failing tests**

Add to `plugins/rigging/tests/test_config.py`:

```python
def test_test_command_preserved_as_tuple(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"testCommand": ["turbo", "run", "test"]}}
    }))
    assert cfg.stacks["node"].test_command == ("turbo", "run", "test")


def test_test_command_absent_is_none(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"node": {}}}))
    assert cfg.stacks["node"].test_command is None


def test_test_command_applies_to_python_too(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"testCommand": ["pytest", "-q"]}}
    }))
    assert cfg.stacks["python"].test_command == ("pytest", "-q")


def test_test_command_empty_list_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": []}}}))
    assert "testCommand" in str(e.value)


def test_test_command_not_a_list_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": "npm test"}}}))
    assert "testCommand" in str(e.value)


def test_test_command_non_string_element_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": ["npm", 7]}}}))
    assert "testCommand" in str(e.value)


def test_test_command_empty_string_element_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"stacks": {"node": {"testCommand": ["npm", ""]}}}))
    assert "testCommand" in str(e.value)


def test_test_command_with_actions_expression_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"testCommand": ["echo", "${{ secrets.TOKEN }}"]}}
        }))
    msg = str(e.value)
    assert "testCommand" in msg
    assert "${{" in msg


def test_test_command_with_newline_rejected(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "stacks": {"node": {"testCommand": ["npm", "test\nrm -rf /"]}}
        }))
    assert "testCommand" in str(e.value)


def test_shell_metacharacters_are_allowed_and_kept_literal(tmp_path):
    # A ; or a quote is inert once shlex.quote runs at render; the config layer
    # accepts it. Only ${{ and newline are refused.
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"testCommand": ["sh", "-c", "echo hi; echo bye"]}}
    }))
    assert cfg.stacks["node"].test_command == ("sh", "-c", "echo hi; echo bye")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -k test_command -v` (from the repo root)
Expected: FAIL — `StackConfig` has no `test_command`, and `testCommand` is an unknown stack key (`ConfigError`).

- [ ] **Step 3: Implement**

In `plugins/rigging/rigging/config.py`:

Add the marker constant beside `VERSION_RE` (after line 23):

```python
#: The literal that opens a GitHub Actions expression. A testCommand element
#: containing it is rejected at load: GitHub substitutes `${{ ... }}` at the
#: YAML layer, before any shell sees the line, so shlex.quote is no defence --
#: the only safe move is to refuse the value so it never reaches a rendered
#: `run:` block.
EXPRESSION_MARKER = "${{"
```

Add `"testCommand"` to `STACK_KEYS`:

```python
STACK_KEYS = frozenset({"versions", "packageManager", "testCommand"})
```

Add the field to `StackConfig` (after `package_manager`):

```python
    #: A custom test command as an argv tuple, replacing this stack's (or its
    #: node package manager's) default test argv. None takes the default. An
    #: argv tuple, not a shell string, so shell metacharacters are inert once
    #: rendered -- and pipes, redirects, and `&&` are simply not expressible,
    #: which is the point: a repo needing a shell pipeline needs a hand-written
    #: workflow, not this key.
    test_command: Optional[tuple[str, ...]] = None
```

Add the validator (after `_valid_package_manager`):

```python
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
        if "\n" in part:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.testCommand' entry {part!r} "
                f"contains a newline; each entry is one argv element."
            )
        argv.append(part)
    return tuple(argv)
```

Wire it into `load_config`, replacing the `resolved[stack_id] = StackConfig(...)` assignment:

```python
        package_manager = _valid_package_manager(
            stack_value.get("packageManager"), stack_id)
        test_command = _valid_test_command(
            stack_value.get("testCommand"), stack_id)
        resolved[stack_id] = StackConfig(versions=versions,
                                         package_manager=package_manager,
                                         test_command=test_command)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests/test_config.py -v`
Expected: PASS (new `test_command` tests plus all existing config tests).

- [ ] **Step 5: Commit**

```bash
git add plugins/rigging/rigging/config.py plugins/rigging/tests/test_config.py
git commit -m "feat(rigging): validate stacks.<id>.testCommand into StackConfig (#26)"
```

---

### Task 2: Rendering — resolve the effective test argv and preserve the goldens

**Files:**
- Modify: `plugins/rigging/rigging/stacks.py` (add `StackSpec.default_test`; move python's pytest step out of `steps`)
- Modify: `plugins/rigging/rigging/plan.py` (split `_manager_steps`; add `_resolve_test_argv`; append the test step in `_build_job`)
- Modify: `scripts/sync_action_pins.py` (add the two new golden fixtures to the regen list)
- Modify: `plugins/rigging/tests/test_stacks.py` (assert `default_test` values; python's `steps` no longer carries pytest)
- Modify: `plugins/rigging/tests/test_render.py` (byte-identity test for the two new goldens)
- Create: `plugins/rigging/tests/golden/node-testcommand.yml`, `plugins/rigging/tests/golden/python-testcommand.yml` (generated, not hand-written)

**Interfaces:**
- Consumes: `config.StackConfig.test_command` (Task 1).
- Produces: `stacks.StackSpec.default_test: tuple[str, ...]` (default `()`); `plan._resolve_test_argv(stack_id, manager_id, test_command) -> tuple[str, ...]`. `_build_job` gains a `test_command=None` parameter.

- [ ] **Step 1: Write the failing tests**

Add to `plugins/rigging/tests/test_stacks.py`:

```python
def test_python_default_test_is_pytest():
    assert stacks.REGISTRY["python"].default_test == ("python", "-m", "pytest")


def test_node_has_no_stack_default_test():
    # node's default test comes from its package manager, not the stack.
    assert stacks.REGISTRY["node"].default_test == ()


def test_python_steps_no_longer_carry_the_test_step():
    # pytest moved to default_test; steps is install-only now.
    runs = [s.run for s in stacks.REGISTRY["python"].steps if s.run]
    assert not any("pytest" in r for r in runs)
```

Add to `plugins/rigging/tests/test_render.py`:

```python
@pytest.mark.parametrize("data,golden", [
    ({"stacks": {"node": {"testCommand": ["turbo", "run", "test", "--concurrency=1"]}}},
     "node-testcommand.yml"),
    ({"stacks": {"python": {"testCommand": ["pytest", "-q"]}}},
     "python-testcommand.yml"),
])
def test_test_command_matches_its_golden(tmp_path, data, golden):
    cfg = load_config(write(tmp_path, data))
    assert render(build_plan(cfg)) == read_golden(golden)


def test_test_command_replaces_only_the_test_step_not_install(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"node": {"testCommand": ["turbo", "run", "test"]}}}))
    blocks = iter_run_blocks(render(build_plan(cfg)))
    assert blocks == ["npm ci", "turbo run test"]  # install default, test overridden


def test_existing_goldens_unchanged_after_refactor(tmp_path):
    # The whole point of the refactor: repos not using testCommand see no change.
    for data, golden in [
        ({"stacks": {"python": {"versions": ["3.9", "3.12"]}}}, "python.yml"),
        ({"stacks": {"node": {"versions": ["20"]}}}, "node.yml"),
    ]:
        cfg = load_config(write(tmp_path, {"name": "ci", **data}))
        assert render(build_plan(cfg)) == read_golden(golden)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/rigging/tests/test_stacks.py plugins/rigging/tests/test_render.py -k "default_test or test_command or steps_no_longer" -v`
Expected: FAIL — `default_test` does not exist; the golden files don't exist yet.

- [ ] **Step 3: Implement the registry change**

In `plugins/rigging/rigging/stacks.py`, add a field to `StackSpec` (after `steps`), with a default so construction stays valid:

```python
    steps: tuple[Step, ...]
    #: The stack's OWN default test argv, appended as the final job step when
    #: no packageManager supplies one and no testCommand overrides it. Stored
    #: as argv (not a Step) so it shares render_argv with a user's testCommand
    #: and with the node managers' `test`. Empty for node, whose test comes
    #: from its package manager instead.
    default_test: tuple[str, ...] = ()
```

Change python's `StackSpec`: remove the trailing pytest `Step` from `steps`, and add `default_test`:

```python
        steps=(
            Step(run=(
                "python -m pip install --upgrade pip\n"
                "pip install 'pytest>=8,<9'\n"
                "if [ -f requirements.txt ]; then pip install -r requirements.txt; fi"
            )),
        ),
        default_test=("python", "-m", "pytest"),
    ),
```

Change node's `StackSpec` to make the deferral explicit:

```python
        steps=(),
        default_test=(),  # node's default test comes from its package manager
    ),
```

- [ ] **Step 4: Implement the plan change**

In `plugins/rigging/rigging/plan.py`, replace `_manager_steps` so it returns install-only (no test), add `_resolve_test_argv`, and have `_build_job` append the resolved test step:

```python
def _manager_steps(stack_id: str, manager_id: str):
    """The setup, post-setup, and INSTALL steps a stack's package manager
    contributes. The test step is resolved separately (see _resolve_test_argv)
    so a testCommand can override it. Returns ((), (), ()) for a stack with no
    manager concept -- today every stack but node.
    """
    if stack_id != "node":
        return (), (), ()
    manager = stacks.NODE_PACKAGE_MANAGERS[manager_id]
    install_run = (stacks.Step(run=render_argv(manager.install)),)
    return manager.setup_steps, manager.post_setup_steps, install_run


def _resolve_test_argv(stack_id: str, manager_id: str,
                       test_command: tuple[str, ...] | None) -> tuple[str, ...]:
    """The effective test argv for a job: an explicit testCommand wins; else
    the node manager's default; else the stack's own default_test."""
    if test_command is not None:
        return test_command
    if stack_id == "node":
        return stacks.NODE_PACKAGE_MANAGERS[manager_id].test
    return stacks.REGISTRY[stack_id].default_test


def _build_job(stack_id: str, versions: tuple[str, ...],
               manager_id: str = stacks.DEFAULT_NODE_PACKAGE_MANAGER,
               test_command: tuple[str, ...] | None = None) -> Job:
    spec = stacks.REGISTRY[stack_id]
    setup_step = stacks.Step(
        uses=spec.setup_uses,
        uses_version=spec.setup_uses_version,
        with_={spec.setup_with_key: "${{ matrix.%s }}" % spec.matrix_var},
    )
    manager_setup, manager_post_setup, manager_install = _manager_steps(stack_id, manager_id)
    test_step = stacks.Step(
        run=render_argv(_resolve_test_argv(stack_id, manager_id, test_command)))
    return Job(
        id=spec.id,
        runs_on="ubuntu-latest",
        matrix_var=spec.matrix_var,
        versions=versions,
        steps=(
            CHECKOUT_STEP, *manager_setup, setup_step,
            *manager_post_setup, *spec.steps, *manager_install, test_step,
        ),
    )
```

Update `build_plan` to pass `test_command`:

```python
def build_plan(cfg: config.Config) -> CiPlan:
    jobs = tuple(
        _build_job(stack_id, stack_cfg.versions,
                   stack_cfg.package_manager or stacks.DEFAULT_NODE_PACKAGE_MANAGER,
                   stack_cfg.test_command)
        for stack_id, stack_cfg in cfg.stacks.items()
    )
    return CiPlan(name=cfg.name, jobs=jobs, push_branches=cfg.push_branches)
```

- [ ] **Step 5: Add the new goldens to the regeneration script and generate them**

In `scripts/sync_action_pins.py`, add two entries to the `goldens` dict literal (the one initialized at lines ~198-201, before the manager loop):

```python
goldens = {
    "python.yml":   RC(name="ci", stacks={"python": RSC(versions=("3.9", "3.12"))}),
    "polyglot.yml": RC(name="ci", stacks={"python": RSC(versions=("3.12",)), "node": RSC(versions=("20",))}),
    "node-testcommand.yml": RC(name="ci", stacks={"node": RSC(versions=("20",), test_command=("turbo", "run", "test", "--concurrency=1"))}),
    "python-testcommand.yml": RC(name="ci", stacks={"python": RSC(versions=("3.12",), test_command=("pytest", "-q"))}),
}
```

Then generate all goldens from the registries (this also re-renders the
dogfooded `.github/workflows/ci.yml` and `security.yml`, which must NOT move):

Run: `python3 scripts/sync_action_pins.py`
Expected: prints "regenerated the workflows and goldens from the registries." Then confirm the ONLY new/changed rendered files are the two new goldens:

Run: `git status --short`
Expected: `plugins/rigging/tests/golden/node-testcommand.yml` and `.../python-testcommand.yml` are new (`??`), alongside your source edits (`stacks.py`, `plan.py`, `sync_action_pins.py`, the two test files). NO existing golden, and NEITHER `.github/workflows/ci.yml` nor `.github/workflows/security.yml`, may appear as modified. If any rendered artifact moved, the refactor changed output — STOP and report; do not commit.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests -q`
Expected: all pass, including the seven byte-identity goldens, the two new goldens, and `test_iter_run_blocks_returns_unquoted_bodies_in_order` (unchanged: python still renders install then `python -m pytest`).

If a pre-existing test in `test_stacks.py` pins python's old two-step shape (e.g. asserts `len(REGISTRY["python"].steps) == 2` or that a python step is `python -m pytest`), update it to the new shape — python's `steps` is now install-only and its test lives in `default_test`. Do not weaken any assertion beyond that reshaping; if you are unsure whether a failing assertion is a genuine regression or just the reshaping, report it rather than editing it.

- [ ] **Step 7: Commit**

```bash
git add plugins/rigging/rigging/stacks.py plugins/rigging/rigging/plan.py \
        scripts/sync_action_pins.py plugins/rigging/tests/test_stacks.py \
        plugins/rigging/tests/test_render.py plugins/rigging/tests/golden/
git commit -m "feat(rigging): render stacks.<id>.testCommand as the job's test step (#26)"
```

---

### Task 3: Injection safety, skill docs, and changelog

**Files:**
- Modify: `plugins/rigging/tests/test_injection.py` (testCommand is the first user-controlled text reaching a `run:` block — this is the load-bearing coverage)
- Modify: `plugins/rigging/skills/init/SKILL.md` (document `testCommand` as a manual override)
- Modify: `CHANGELOG.md`

**Interfaces:**
- Consumes: `config.load_config`, `config.ConfigError`, `plan.build_plan`, `render.render`, `render.iter_run_blocks` (all existing).

- [ ] **Step 1: Write the injection tests**

Add to `plugins/rigging/tests/test_injection.py`:

```python
# --- Assertion 6: testCommand is the first user-controlled text that reaches
# a `run:` line, so it gets both guarantees: refused at load if it carries an
# Actions expression or a newline, and shlex-quoted (inert) otherwise. --------


@pytest.mark.parametrize("hostile", [
    ["echo", "${{ github.event.issue.title }}"],
    ["echo", "${{ secrets.TOKEN }}"],
    ["npm", "test\nrm -rf /"],
])
def test_hostile_test_command_rejected_before_render(tmp_path, hostile):
    write_config(tmp_path, {"name": "ci", "stacks": {"node": {"testCommand": hostile}}})
    with pytest.raises(ConfigError):
        load_config(tmp_path)


def test_accepted_test_command_renders_no_expression_and_stays_quoted(tmp_path):
    # A ; and a quote are accepted (shlex.quote makes them inert) and must not
    # produce a ${{ }} expression in any run block.
    out = render_for(tmp_path, {"node": {"testCommand": ["sh", "-c", "echo hi; echo 'x'"]}})
    for block in iter_run_blocks(out):
        assert "${{" not in block
    # The whitelisted matrix expression is still the ONLY expression in the file.
    for expr in EXPRESSION_RE.findall(out):
        assert WHITELIST_RE.fullmatch(expr)


def test_accepted_test_command_is_shell_quoted_in_the_run_line(tmp_path):
    out = render_for(tmp_path, {"node": {"testCommand": ["sh", "-c", "echo hi; echo bye"]}})
    # The metacharacter-bearing element is single-quoted by shlex.quote, so the
    # `;` cannot start a second command at the shell layer.
    assert "'echo hi; echo bye'" in out
```

- [ ] **Step 2: Run the injection tests to verify they pass**

Run: `python3 -m pytest plugins/rigging/tests/test_injection.py -v`
Expected: PASS (the new assertions plus all existing injection guarantees).

- [ ] **Step 3: Document `testCommand` in the init skill**

In `plugins/rigging/skills/init/SKILL.md`, find the section describing `.rigging.json`'s per-stack keys (`versions`, `packageManager`). Add a `testCommand` entry after `packageManager`, matching the surrounding prose style. Use exactly this content (adapt only the surrounding markdown formatting to match the file):

> - **`testCommand`** (optional, per stack): the test command as a JSON array
>   of arguments — e.g. `["turbo", "run", "test", "--concurrency=1"]` — replacing
>   the stack's default (`python -m pytest`, or the node package manager's
>   `test` script). It is an argv array, not a shell string: each element is one
>   argument, and shell constructs (pipes, `&&`, redirects, `$VAR`) are not
>   interpreted. A repo needing a shell pipeline needs a hand-written workflow.
>   `init` never writes this key — it is a manual override for when the default
>   guesses wrong (notably `bun run test` for a repo that wants a different
>   runner).

If the skill has no per-stack key section, add a short "Custom test command" subsection near where `packageManager` is discussed, carrying the same content.

- [ ] **Step 4: Verify the skill doc references nothing false**

Run: `python3 -m pytest plugins/rigging/tests -q`
Expected: all pass (doc-only change; this confirms nothing regressed).

- [ ] **Step 5: Add the changelog entry**

Under `## [Unreleased]` in `CHANGELOG.md`, add to the `### Added` list (matching the discursive style of the surrounding entries):

```markdown
- **`rigging` can run a repo's real test command, not just `npm test`.**
  `.rigging.json`'s per-stack config gained `testCommand`, a JSON argv array
  (`["turbo", "run", "test", "--concurrency=1"]`) that replaces the stack's
  default test command — `python -m pytest`, or the node package manager's
  `test` script. It is an argv array, not a shell string, so shell
  metacharacters are inert and pipes/`&&`/redirects are simply not
  expressible; a value carrying a `${{ ... }}` Actions expression or a newline
  is refused at load, before it could reach a rendered `run:` line. `init`
  does not write it — it is the manual escape hatch for when the default test
  command guesses wrong.
```

- [ ] **Step 6: Verify the changelog gate passes**

Run: `python3 scripts/check_changelog.py $(git merge-base main HEAD) HEAD`
Expected: "CHANGELOG.md Unreleased section gained content — ok".

- [ ] **Step 7: Commit**

```bash
git add plugins/rigging/tests/test_injection.py plugins/rigging/skills/init/SKILL.md CHANGELOG.md
git commit -m "test(rigging): injection guarantees for testCommand; document it (#26)"
```

---

## Notes for the executor

- **This is increment 2 of 3 for issue #26.** Increment 1 (package managers) already landed. Increment 3 (service containers) is a separate future plan; do not build it here. Issue #26 stays open after this.
- **`testCommand` deliberately does not flow through `propose_config`.** If you find yourself editing `scaffold.py`, `test_scaffold.py`, or `SIGNAL_KEYS`, stop — that is out of scope and would wrongly imply init detects a custom command.
- **The byte-identity of the seven existing goldens is the refactor's safety net.** Task 2 Step 5 is the gate: if any existing golden moves, the refactor is wrong.
