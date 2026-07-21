# ballast — design spec (increment 1)

**Suite:** Shipyard
**Plugin:** ballast (fourth member; after keel, rigging, stow)
**Increment:** 1 of ballast
**Date:** 2026-07-20

## What ballast is

ballast owns a python repo's **pytest-runner configuration**. "Tests don't run
right" is overwhelmingly a config problem — wrong import mode, unset or wrong
testpaths, missing pythonpath — which is precisely shipyard's own monorepo
situation. ballast writes a durable `.ballast.json` and renders a `pytest.ini`
from it deterministically, so that the `python -m pytest` step rigging's CI runs
actually resolves and collects the right tests.

Increment 1 ships **ballast v0.1.0**: the pure `config → render` engine that
emits `pytest.ini`, a `.ballast.json` config, and a `ballast:init` skill. Single
file model (render + byte-identity drift guard), python-only, no overlap with
rigging (which *runs* tests), stow (`.gitignore`), or keel (git lifecycle).

## Scope, and why python-only

Python has exactly one canonical, declarative, byte-stable test-config artifact:
the `[pytest]` INI table (`pytest.ini`). Node does **not** — its test config
forks across jest/vitest/node:test and is imperative JS/TS (`jest.config.js`),
not a declaratively-renderable committed file; the only stable declarative
surface (`package.json` `scripts.test`) is already what rigging invokes. There is
no single honest node artifact for ballast to *own*, so emitting one would be
guesswork. Python-only is the honest MVP; node is an explicit deferred item (the
init skill tells a node user ballast doesn't configure node runners yet).
Detection still uses the **same** marker files as rigging/stow for python.

## Composition (the load-bearing seam with rigging)

rigging owns `.github/workflows/ci.yml` and its `python -m pytest` step; ballast
owns `pytest.ini` — the file that step *reads*. rigging decides *how/when* CI
runs pytest; ballast decides *what* pytest collects (testpaths) and *how* it
resolves packages (import-mode). This is the deepest seam in the suite because it
is exactly shipyard's own problem: without `--import-mode=importlib` + explicit
testpaths, pytest either scans the whole tree or dies on the same-basename
collision the suite already fights (`test_smoke.py` in four plugins). Zero shared
file; the handoff is the `pytest.ini` rigging's runner reads. With stow
(`.gitignore`) and keel (git) ballast is fully orthogonal. The engine imports
only stdlib + its own package (AST purity guard) — never a sibling.

**Honest caveat (disclosed, not hidden):** a `pytest.ini` alone does not make a
*test-less* repo's CI green — pytest exits 5 on an empty suite. ballast owns "the
runner is configured correctly"; "there is a green test to run" is the natural
inc-2 artifact (a no-clobber starter test). The inc-1 init skill runs
`python -m pytest --collect-only` and warns plainly when zero tests are found.

## Architecture

Mirrors the siblings: a stdlib-only pure engine (AST-purity-guarded), Python
3.9+, all I/O in the `ballast:init` skill.

| Path | Responsibility | Pure |
|------|----------------|------|
| `ballast/__init__.py` | `__version__ = "0.1.0"` | ✓ |
| `ballast/stacks.py` | Pure-data `StackSpec` registry. python only: `detect_files=("pyproject.toml","setup.py","setup.cfg","requirements.txt")`, plus config-field defaults (`import_mode="importlib"`, `test_paths=("tests",)`). `STACK_IDS = ("python",)`. Extensible seam where node slots in later with no structural change. | ✓ |
| `ballast/config.py` | `load_config(root) -> Optional[Config]` (absent → None; invalid → `ConfigError`; stow-style 3-way contract). Validates camelCase `.ballast.json`. Frozen `Config{stacks: dict[str, PytestConfig]}` and `PytestConfig{test_paths, python_path, import_mode, add_opts}`. Exposes `PATH_RE`/`FLAG_RE`/`IMPORT_MODES`. | ✓ |
| `ballast/detect.py` | `detect_stacks(root) -> tuple[str,...]` by shared marker-file existence, registry order, pathlib only. | ✓ |
| `ballast/render.py` | `render(config) -> str`: the deterministic `pytest.ini` emitter (the heart). | ✓ |
| `ballast/scaffold.py` | `propose_config(signals) -> dict` (validated, `ValueError` naming a bad field, guaranteed to load); `CONFIG_FILES = [".ballast.json", "pytest.ini"]`; `classify_files`. | ✓ |
| `skills/init/SKILL.md` | `ballast:init`. Frontmatter exactly `name`+`description`, `name == "init"`. | — |
| `.claude-plugin/plugin.json` | name `ballast`, version `0.1.0`, keywords `[pytest, testing, config]`. | — |
| `tests/` | pytest suite + `tests/golden/`. **No `tests/__init__.py`.** | — |

No `plan.py` (unlike rigging): a single stack maps directly to the table.

## The config file: `.ballast.json`

Committed, camelCase, validated by `config.load_config`. Top-level `stacks`:
required, non-empty object keyed by opted-in stack id (inc 1: only `python`;
unknown id → `ConfigError`). Each stack value is an object with:

- `testPaths` — optional non-empty list of path-safe strings (`PATH_RE`: no
  newline, no leading `/`, no `..` segment); default `["tests"]`.
- `pythonPath` — optional list of path-safe strings; default `[]`; omitted from
  render when empty.
- `importMode` — optional enum `importlib | prepend | append`; default
  `"importlib"` (the opinionated default — precisely the import-collision class
  ballast exists to fix, and pytest's recommended mode).
- `addOpts` — optional list of whitespace-free flag tokens (`FLAG_RE`) appended
  after the `--import-mode=` flag; default `[]`.

Example: `{"stacks": {"python": {"testPaths": ["tests"], "importMode": "importlib"}}}`

## The emitter (`render`)

`render(config) -> str` emits exactly (python stack):

```
[pytest]
addopts = --import-mode=<mode>[ <flag> <flag>...]
testpaths =
    <path>
    <path>
pythonpath =
    <path>
    <path>
```

- `addopts` line: `--import-mode=<importMode>` followed by each `addOpts` token
  space-separated. Always present (import-mode is always set).
- `testpaths`: header line `testpaths =` then each path on its own line indented
  4 spaces.
- `pythonpath`: same shape, emitted **only when non-empty**.
- Exactly one trailing newline. Deterministic: same config in → byte-identical
  text out. Golden fixtures under `tests/golden/` pin the format independently of
  the dogfood.

`PATH_RE`/`FLAG_RE` reject newlines and INI-structural characters at config load,
so render can never emit a second `[section]` header or a line-break inside a
value. A `test_render`/`test_injection`-style assertion pins that the only INI
section header in any output is the single leading `[pytest]`.

## File model

**Render-from-data (rigging's model) for `pytest.ini`** — *not* stow's
managed-block. The `[pytest]` table's keys (`testpaths`/`pythonpath`/`addopts`)
are singular (each appears once); a "block that owns addopts" while a user also
sets addopts is a duplicate-key conflict, not a merge — so managed-block
structurally doesn't fit. Because `pytest.ini` is a **dedicated single-owner
file** (unlike co-owned `pyproject.toml`/`setup.cfg`), wholesale ownership is
honest: config → deterministic emitter → exact bytes, drift-guarded by a
byte-identity test. `.ballast.json` uses exclusive-create (`open(path,"x")`) like
every sibling config. On a pre-existing **foreign** `pytest.ini`, init is
strictly no-clobber: it reports and stops, never migrates in inc 1.

## Dogfood

The elegant, precedent-faithful part. shipyard's own `pytest.ini` is bespoke:

```
[pytest]
addopts = --import-mode=importlib
testpaths =
    plugins/keel/tests
    plugins/rigging/tests
    plugins/stow/tests
pythonpath =
    plugins/keel
    plugins/rigging
    plugins/stow
```

The "a generic generator would clobber this" fear assumed a *dumb* generator
that only knows `testpaths=tests`. ballast's config carries `testPaths` and
`pythonPath` as **lists** plus `importMode`, so it reproduces this bespoke
monorepo config **exactly**. shipyard adopts ballast by committing a
`.ballast.json` whose python stack encodes `importMode="importlib"`,
`testPaths=[the four plugin test dirs incl plugins/ballast/tests]`,
`pythonPath=[the four plugin dirs incl plugins/ballast]`, `addOpts=[]`.
`render(load_config(REPO))` then produces `pytest.ini` byte-for-byte, and
`test_dogfood.py` asserts `render(load_config(REPO)) == (REPO/"pytest.ini").read_text()`
— identical in spirit to rigging's `render(build_plan(load_config(REPO))) == ci.yml`.

ballast's own arrival is expressed *through* ballast: adding `plugins/ballast/tests`
+ `plugins/ballast` to `.ballast.json` regenerates `pytest.ini` (now four
entries), which is exactly what collects ballast's own tests. The hand-authored
bespoke config becomes ballast-owned, byte-identically. No `pyproject.toml` is
invented for ceremony (shipyard has none; 3.9 stdlib can't write TOML); no fake
single-project fixture stands in.

## Distribution

Registered in `.claude-plugin/marketplace.json` (`source ./plugins/ballast`,
category `workflow`), version `0.1.0`.

## Scope

**In scope (increment 1):** the pure `config → render` engine, the python
registry, `.ballast.json`, `pytest.ini` emission, the `ballast:init` skill, the
byte-identity dogfood on shipyard's real `pytest.ini`, marketplace registration.
Version `0.1.0`.

**Deferred:**
- A starter/example test + `tests/` skeleton (keel-style no-clobber) — the inc-2
  artifact that closes the "configured but nothing to run → pytest exit 5 → red
  CI" gap.
- node test-runner config (no single canonical declarative artifact).
- `pyproject.toml [tool.pytest.ini_options]` / `setup.cfg [tool:pytest]` targets
  (co-owned files needing TOML-aware managed-block splicing; 3.9 can't write TOML).
- Coverage config (would couple ballast to a non-stdlib dependency).
- Arbitrary extra pytest keys (markers, filterwarnings, minversion) beyond the
  structured set — wholesale ownership can't carry hand-added keys.
- Migrating a pre-existing foreign `pytest.ini` (inc 1 is strictly no-clobber).
- A second skill (e.g. `ballast:doctor`) and any advisory hook.
