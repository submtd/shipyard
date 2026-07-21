# ballast increment 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build ballast v0.1.0 — a stdlib-only pure engine that renders a python repo's `pytest.ini` from a committed `.ballast.json`, plus a `ballast:init` skill, dogfooded byte-for-byte on shipyard's own bespoke monorepo `pytest.ini`.

**Architecture:** Mirror rigging/stow: pure engine (`config → render`) driven by a python-only stacks registry; `render(config) -> str` is the deterministic `pytest.ini` emitter; the drift guard is a rigging-style dogfood (`render(load_config(REPO)) == committed pytest.ini`). No `plan.py` (single stack).

**Tech Stack:** Python 3.9+, stdlib only. pytest.

## Global Constraints

- **Runtime dependencies: stdlib only.** Tests may use pytest.
- **Python 3.9+.** `from __future__ import annotations` where `X | None` appears; no `match`.
- **The engine is pure.** `stacks.py`, `config.py`, `detect.py`, `render.py`, `scaffold.py` MUST NOT import `subprocess`/`os`/networking; pathlib/json/re only. An AST `test_purity.py` enforces this.
- **`.ballast.json` keys are camelCase.** `config.load_config(root) -> Optional[Config]` returns `None` when absent, raises `ConfigError` on any invalid-but-present file.
- **Render safety.** `PATH_RE`/`FLAG_RE` reject newlines and INI-structural characters at config load, so `render` can never emit a second `[section]` header or a broken value. `render` output contains exactly one INI section header: the leading `[pytest]`.
- Skill frontmatter uses **only** `name` and `description`; `name` MUST equal the dir (`init`).
- **No `plugins/ballast/tests/__init__.py`** — the repo-wide guard forbids `plugins/*/tests/__init__.py` (same-basename collision under `--import-mode=importlib`).
- Work on branch `feature/ballast` (already created off `main`). Do NOT switch branches. Commit with `git -c user.name="Steve Harmeyer" -c user.email="harmeyersteve@gmail.com"`.
- New plugin → version **0.1.0**.

---

## File Structure

```
plugins/ballast/
├── ballast/
│   ├── __init__.py     __version__ = "0.1.0"
│   ├── stacks.py       StackSpec registry (python only); STACK_IDS   [pure]
│   ├── config.py       load_config -> Config|None; PytestConfig; PATH_RE/FLAG_RE/IMPORT_MODES [pure]
│   ├── detect.py       detect_stacks(root)                            [pure]
│   ├── render.py       render(config) -> str  (pytest.ini emitter)    [pure]
│   └── scaffold.py     propose_config, classify_files, CONFIG_FILES   [pure]
├── skills/init/SKILL.md
├── .claude-plugin/plugin.json
└── tests/  (NO __init__.py)
    ├── golden/  test_stacks.py test_config.py test_detect.py
    ├── test_render.py test_scaffold.py test_purity.py test_dogfood.py test_smoke.py
```

Also modified: `pytest.ini` (add ballast paths — see Task 1 note), `.claude-plugin/marketplace.json`, `.ballast.json` (new), `CHANGELOG.md`, `README.md`.

---

### Task 1: Skeleton, pytest wiring, and the python stacks registry

**Files:** Modify `pytest.ini`; Create `plugins/ballast/ballast/__init__.py`, `plugins/ballast/.claude-plugin/plugin.json`, `plugins/ballast/ballast/stacks.py`; Test `plugins/ballast/tests/test_stacks.py`.

**Interfaces — Produces:**
- `ballast.__version__ == "0.1.0"`.
- `stacks.StackSpec` — frozen dataclass: `id: str`, `detect_files: tuple[str,...]`, `default_test_paths: tuple[str,...]`, `default_import_mode: str`.
- `stacks.REGISTRY = {"python": StackSpec(id="python", detect_files=("pyproject.toml","setup.py","setup.cfg","requirements.txt"), default_test_paths=("tests",), default_import_mode="importlib")}`.
- `stacks.STACK_IDS = tuple(REGISTRY)  # ("python",)`.

`plugin.json`: `{"name":"ballast","displayName":"ballast","version":"0.1.0","description":"Configures the pytest runner: renders pytest.ini from .ballast.json so tests resolve and collect correctly.","license":"MIT","keywords":["pytest","testing","config"]}`.

**pytest.ini note (IMPORTANT):** ballast will *own* `pytest.ini` via the Task 7 dogfood, but its own tests must run during Tasks 1–6. Add `plugins/ballast/tests` to `testpaths` and `plugins/ballast` to `pythonpath` in the existing format (4-space-indented entries, keeping keel/rigging/stow). Task 7 regenerates `pytest.ini` from `.ballast.json` and MUST reproduce this file byte-for-byte (the dogfood) — so keep the format exactly as the existing entries.

- [ ] **Step 1: Write failing tests** — `test_stacks.py`: `REGISTRY` keys `("python",)`; the python spec's fields exact; `STACK_IDS == ("python",)`; `import ballast; ballast.__version__=="0.1.0"`.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** skeleton + plugin.json + pytest.ini edit + stacks.py.
- [ ] **Step 4: Run** test_stacks green, then FULL suite `python3 -m pytest -q` (keel 296 + rigging 130 + stow 163 + new; confirm the three prior counts unchanged, no shadowing).
- [ ] **Step 5: Commit** `feat(ballast): package skeleton, pytest wiring, python stacks registry`.

---

### Task 2: `config.py` — `.ballast.json` loader/validator

**Files:** Create `plugins/ballast/ballast/config.py`; Test `plugins/ballast/tests/test_config.py`.

**Interfaces:**
- Consumes: `stacks.STACK_IDS`, `stacks.REGISTRY`.
- Produces:
  - `config.ConfigError`.
  - `config.IMPORT_MODES = ("importlib", "prepend", "append")`.
  - `config.PATH_RE` — rejects a string containing a newline, a leading `/`, or a `..` path segment (accepts normal relative paths like `tests`, `plugins/keel/tests`). Use `fullmatch` (remember the `$`-allows-trailing-newline pitfall — use `fullmatch` or `\Z`).
  - `config.FLAG_RE` — a non-empty token with no whitespace/newline (e.g. `-q`, `--strict-markers`, `--cov=x`).
  - `config.PytestConfig` — frozen: `test_paths: tuple[str,...]`, `python_path: tuple[str,...]`, `import_mode: str`, `add_opts: tuple[str,...]`.
  - `config.Config` — frozen: `stacks: dict[str, PytestConfig]` (ordered).
  - `config.load_config(root) -> Optional[Config]`.

**Rules:** absent → None; unreadable/invalid JSON/non-object → `ConfigError`. `stacks` required, non-empty object; each key ∈ `STACK_IDS` (unknown/`base`-style → `ConfigError` naming it + allowed ids); each value must be a `null`/object → a `PytestConfig`. Per field: `testPaths` optional non-empty list of `PATH_RE`-valid strings (default `REGISTRY[id].default_test_paths`); `pythonPath` optional list of `PATH_RE` strings (default `()`); `importMode` optional ∈ `IMPORT_MODES` (default `REGISTRY[id].default_import_mode`); `addOpts` optional list of `FLAG_RE` tokens (default `()`). Any wrong type/shape/charset → `ConfigError` naming the field.

- [ ] **Step 1: Write failing tests** — absent→None; `{"stacks":{"python":{}}}`→defaults (test_paths `("tests",)`, import_mode `"importlib"`, python_path `()`, add_opts `()`); explicit values flow through as tuples; unknown id → ConfigError naming it; `importMode` outside enum → ConfigError; `testPaths` empty list / non-string / a path with a newline / leading `/` / `..` segment each → ConfigError; `addOpts` token with whitespace → ConfigError; non-object stack value → ConfigError; bad JSON → ConfigError.
- [ ] **Step 2–4:** verify fail → implement → green + full suite.
- [ ] **Step 5: Commit** `feat(ballast): .ballast.json loader with path/flag charset validation`.

---

### Task 3: `detect.py`

**Files:** Create `plugins/ballast/ballast/detect.py`; Test `plugins/ballast/tests/test_detect.py`.

**Interfaces:** `detect.detect_stacks(root) -> tuple[str,...]` — registry ids whose `detect_files` exist at `<root>`, registry order; pathlib only.

- [ ] **Step 1:** tests — each python marker alone → `("python",)`; a node-only `package.json` repo → `()` (node unsupported in inc 1); empty dir → `()`.
- [ ] **Step 2–4:** verify fail → implement → green + full suite.
- [ ] **Step 5: Commit** `feat(ballast): python stack detection`.

---

### Task 4: `render.py` — the `pytest.ini` emitter + golden fixtures + structural-safety test

**Files:** Create `plugins/ballast/ballast/render.py`, `plugins/ballast/tests/golden/*.ini`; Test `plugins/ballast/tests/test_render.py`.

**Interfaces:** Consumes `config.Config`/`config.PytestConfig`. Produces `render.render(config: Config) -> str`.

**Emitter rules (exact, python stack):**
```
[pytest]
addopts = --import-mode=<import_mode>[ <flag>]...
testpaths =
    <path>
    <path>
pythonpath =
    <path>
    <path>
```
- `addopts` line: `addopts = --import-mode=<import_mode>` then each `add_opts` token space-separated (import-mode first, always present).
- `testpaths`: header `testpaths =` then each `test_paths` entry on its own line indented exactly 4 spaces.
- `pythonpath`: same shape, emitted ONLY when `python_path` is non-empty.
- Exactly one trailing `\n`. Deterministic.

- [ ] **Step 1: Hand-author golden fixtures** matching the emitter rules: `golden/defaults.ini` (python defaults: import-mode importlib, testpaths `tests`, no pythonpath, no addOpts), `golden/monorepo.ini` (import-mode importlib, four-ish testpaths + pythonpaths — mirror shipyard's shape), `golden/addopts.ini` (import-mode + a couple flags, single testpath). Then write `test_render.py`: `render(load_config(<fixture .ballast.json>))` equals each golden byte-for-byte; pythonpath omitted when empty and present when set; all three import modes render; addOpts tokens appended after the import-mode flag; determinism (`render(c)==render(c)`); **structural safety**: the only INI section header in any rendered output is the leading `[pytest]` (assert `output.count("[") ...` / regex for `^\[.*\]$` lines == 1), and no rendered line contains a stray newline in a value.
- [ ] **Step 2: Verify fail.** **Step 3: Implement** render.py (iterate emitter to match goldens — goldens are the intended output). **Step 4:** green + full suite.
- [ ] **Step 5: Commit** `feat(ballast): deterministic pytest.ini emitter with golden fixtures`.

---

### Task 5: `scaffold.py` + purity test

**Files:** Create `plugins/ballast/ballast/scaffold.py`; Test `plugins/ballast/tests/test_scaffold.py`, `plugins/ballast/tests/test_purity.py`.

**Interfaces:**
- `scaffold.CONFIG_FILES = [".ballast.json", "pytest.ini"]`.
- `scaffold.classify_files(root, candidates) -> dict` — present/absent (copy sibling).
- `scaffold.propose_config(signals: dict) -> dict` — `signals["stacks"]` is a list of registry ids (inc 1: `["python"]`); optional per-stack `testPaths`/`pythonPath`/`importMode`/`addOpts`. Emits a `.ballast.json` dict guaranteed to round-trip through `config.load_config`; validates against `STACK_IDS`/`IMPORT_MODES`/`PATH_RE`/`FLAG_RE` and raises `ValueError` naming the bad field.

- [ ] **Step 1: Write failing tests** — `test_scaffold.py`: `propose_config({"stacks":["python"]})` round-trips through `load_config`; explicit fields flow through; unknown id / bad importMode / a path failing PATH_RE / a flag failing FLAG_RE each → `ValueError` naming the field; `classify_files` present/absent incl `.ballast.json` and `pytest.ini`; `CONFIG_FILES` value. `test_purity.py`: AST harness (copy sibling) `PURE_MODULES=("stacks","config","detect","render","scaffold")`, hooks-dir-absent-safe.
- [ ] **Step 2: Verify fail.** **Step 3: Implement.** **Step 4: Prove purity bites** — temp `import subprocess` in scaffold.py → purity test fails → REVERT (git diff clean). **Step 5:** green + full suite.
- [ ] **Step 6: Commit** `feat(ballast): scaffold helpers + engine-purity AST test`.

---

### Task 6: the `ballast:init` skill

**Files:** Create `plugins/ballast/skills/init/SKILL.md`. Mirror `rigging:init`/`stow:init` (read them). Frontmatter EXACTLY `name: init` + `description`.

Flow:
1. Confirm repo root.
2. 3-way `.ballast.json` check (absent → fresh; loads → use as-is; ConfigError → stop, surface error, write nothing).
3. Fresh-scaffold: `detect_stacks` (via `python3 -c` with `sys.path.insert(0, "${CLAUDE_PLUGIN_ROOT}")`); if no python detected, tell the user (and note node test config is unsupported in inc 1); `propose_config`; show `.ballast.json`; confirm; exclusive-create (`open(".ballast.json","x")`).
4. Render `pytest.ini` from `render(load_config(Path(".")))`. **No-clobber**: write only if `pytest.ini` is absent. If a `pytest.ini` already exists, do NOT overwrite/migrate — report it exists and stop (inc 1 is no-clobber on a foreign file).
5. Verify: reload config, assert `render(...) == pytest.ini` on disk, and run `python -m pytest --collect-only`; **if zero tests collected, warn plainly** that ballast configured the runner but there is no test to run yet (a starter test is a later increment / the user's to add). Report; point at rigging:init (runs the tests in CI), stow:init, keel:init.

- [ ] **Step 1:** Write SKILL.md. **Step 2:** validate frontmatter (`ok init`). **Step 3:** smoke-test the one-liners against a scratch repo with the real ballast package (CLAUDE_PLUGIN_ROOT=plugins/ballast). **Step 4:** full suite green. **Step 5:** Commit `feat(ballast): ballast:init skill`.

---

### Task 7: Dogfood, marketplace, docs, smoke

**Files:** Create `.ballast.json`; Modify `pytest.ini` (regenerate), `.claude-plugin/marketplace.json`, `CHANGELOG.md`, `README.md`; Test `plugins/ballast/tests/test_dogfood.py`, `plugins/ballast/tests/test_smoke.py`.

- [ ] **Step 1: Adopt ballast on shipyard.** Write repo-root `.ballast.json` encoding shipyard's real settings AND ballast's own entries: python stack with `importMode="importlib"`, `testPaths=["plugins/keel/tests","plugins/rigging/tests","plugins/stow/tests","plugins/ballast/tests"]`, `pythonPath=["plugins/keel","plugins/rigging","plugins/stow","plugins/ballast"]`, `addOpts=[]`. Regenerate `pytest.ini` from ballast: `python3 -c "import sys; sys.path.insert(0,'plugins/ballast'); from ballast.config import load_config; from ballast.render import render; from pathlib import Path; open('pytest.ini','w').write(render(load_config(Path('.'))))"`. **Confirm the regenerated `pytest.ini` is byte-identical to the Task-1 hand-edited one** (same entries, same format) — if it differs, the Task-1 format or the emitter must be reconciled so they match; the committed `pytest.ini` becomes ballast's output. Verify the full suite still collects (all four plugins' tests) after regeneration.
- [ ] **Step 2: Write `test_dogfood.py`** — `REPO = Path(__file__).resolve().parents[3]`; assert `render(load_config(REPO)) == (REPO/"pytest.ini").read_text()` byte-for-byte; assert `"plugins/ballast/tests"` is in the rendered testpaths (ballast's own tests are collected).
- [ ] **Step 3: Write `test_smoke.py`** — `ballast.__version__=="0.1.0"`; `plugin.json` name/version; `marketplace.json` lists `ballast`; `skills/init/SKILL.md` frontmatter exactly `{name,description}` name `init`; every ballast module imports; end-to-end `render(load_config(<tmp fixture>))` non-empty starting with `[pytest]`; the repo-wide guard `test_no_plugin_tests_dir_is_a_package` (or rely on rigging's — but add it here too for stow-parity if the sibling did).
- [ ] **Step 4: Register** ballast in `.claude-plugin/marketplace.json`.
- [ ] **Step 5: Docs** — CHANGELOG `## [Unreleased]` `### Added` bullet for ballast v0.1.0 (renders pytest.ini from .ballast.json; import-mode/testpaths/pythonpath; dogfooded on shipyard's own bespoke config). README: add ballast to the suite intro + status.
- [ ] **Step 6: Run** full suite green (keel 296 + rigging 130 + stow 163 + ballast); changelog gate `python3 scripts/check_changelog.py main "$(git branch --show-current)"` → exit 0; confirm no `plugins/ballast/tests/__init__.py`. Report counts.
- [ ] **Step 7: Commit** `feat(ballast): dogfood shipyard's pytest.ini, register in marketplace, docs`.

---

## Self-Review

**Spec coverage.** Registry → T1; the pytest-config loader with path/flag safety → T2; detection → T3; the deterministic emitter + structural safety → T4; scaffold seam + purity → T5; the init skill (no-clobber pytest.ini, `--collect-only` zero-tests warning) → T6; the byte-identity dogfood on shipyard's real pytest.ini + marketplace + docs → T7. Single file model (render, not managed-block) → T4/T7. Python-only → T1 registry. No `tests/__init__.py` → Global Constraints.

**Placeholder scan.** No TBD/TODO. Golden fixtures authored in T4 Step 1; the dogfood `.ballast.json` values are concrete in T7 Step 1.

**Type consistency.** `StackSpec`/`REGISTRY`/`STACK_IDS` (T1) → consumed in T2–T7. `Config{stacks}`/`PytestConfig{test_paths,python_path,import_mode,add_opts}`/`PATH_RE`/`FLAG_RE`/`IMPORT_MODES` (T2) → consumed in T4/T5/T7. `render` (T4), `propose_config`/`classify_files`/`CONFIG_FILES` (T5) → consumed in T6/T7. The Task-1 hand-edited `pytest.ini` format and the Task-4 emitter must agree so T7's dogfood is a byte-for-byte no-op — called out explicitly in T7 Step 1.
