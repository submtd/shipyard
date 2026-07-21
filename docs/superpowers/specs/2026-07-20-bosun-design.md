# bosun — design spec (increment 1)

**Suite:** Shipyard
**Plugin:** bosun (sixth and final core member; after keel, rigging, stow, ballast, hull)
**Increment:** 1 of bosun
**Date:** 2026-07-20

## What bosun is

bosun is the dependency-management sibling. The boundary with hull is settled:
**dependency UPDATES = bosun; dependency VULNERABILITY-SCANNING = a future hull
increment** (hull does secret scanning today). Increment 1 renders
`.github/dependabot.yml` — GitHub's native, declarative dependency-update config —
from a small committed `.bosun.json`, via the render-from-data engine
(rigging/hull/ballast lineage). Ownership is by filename, extending the suite:
keel = `changelog.yml`, rigging = `ci.yml`, hull = `security.yml`, bosun =
`.github/dependabot.yml` (a config, not a workflow — no collision with the
one-workflow-per-owner rule).

## The hybrid ecosystem model (the key design axis)

A Dependabot config is intrinsically a **list of ecosystems**. bosun uses a
**hybrid** model:

- **`github-actions` — always on.** Every repo using these Shipyard plugins has
  `.github/workflows/` with pinned action refs, so this ecosystem is emitted
  unconditionally (like hull is stack-agnostic). `detect_files=()`, `always_on=True`.
- **`pip` (python) and `npm` (node) — detected** by the shared marker files
  (python: `pyproject.toml`/`setup.py`/`setup.cfg`/`requirements.txt`; node:
  `package.json`), reusing rigging/ballast/stow's exact markers. `always_on=False`.

Rejected alternatives: pure **stack-first** would detect nothing on shipyard (no
manifests) → an empty, invalid `dependabot.yml` and no dogfood. **actions-only**
is the most minimal but its flat schema is throwaway — a dependabot config is a
list of ecosystems, so the `ecosystems` map is the honest durable shape, and
`detect.py` reusing rigging's markers makes pip/npm nearly free (and genuinely
useful to any python/node adopter on day one). The five-plugin precedent is
decisive: rigging ships node detection even though shipyard has no node.

**Critical seam:** the always-on policy lives in `detect`/`scaffold.propose_config`
(init-time), **not** in `render`. `render`/`plan` are a pure, policy-free total
function of the committed `.bosun.json`, so the byte-identity dogfood holds and a
`bosun:init` on a python repo proposes github-actions + detected pip.

## No injection surface

`dependabot.yml` is purely declarative — no `run:` steps, no `uses:`, no `${{ }}`
expressions. So bosun ships **no** injection machinery (no `iter_run_blocks`, no
`${{ }}` whitelist, no `test_injection.py`). Instead, `directory` is **fixed at
`"/"`** in inc 1 (a plan constant, not a config field), which removes the only
user-tainted free-text string from the renderer, leaving `interval` (enum-validated)
as the sole user input. `render` is guarded structurally by a **declarative-only
assertion**: `${{` and `run:` never appear in the output. Config values still get
charset/enum validation (interval enum via `fullmatch`/membership).

## Architecture

Mirrors rigging/hull: a stdlib-only pure engine (AST-purity-guarded), Python 3.9+,
all I/O in the `bosun:init` skill.

| Path | Responsibility | Pure |
|------|----------------|------|
| `bosun/__init__.py` | `__version__ = "0.1.0"` | ✓ |
| `bosun/ecosystems.py` | Pure-data registry (rigging/stacks.py + hull/scanners.py analogue). Frozen `EcosystemSpec{id, package_ecosystem, detect_files: tuple, always_on: bool}`. `REGISTRY = {githubActions → github-actions (detect_files=(), always_on=True); python → pip (the 4 markers, always_on=False); node → npm ((package.json,), always_on=False)}`. `ECOSYSTEM_IDS = tuple(REGISTRY)`. `INTERVALS = ("daily","weekly","monthly")`. No name/steps/env fields. | ✓ |
| `bosun/config.py` | `CONFIG_NAME=".bosun.json"`; `ConfigError`; frozen `EcosystemConfig{interval}` and `Config{ecosystems: dict[str, EcosystemConfig]}`. `load_config(root) -> Optional[Config]` (absent → None; invalid → `ConfigError` naming the field). Validates object root, non-empty `ecosystems` map, ids in `ECOSYSTEM_IDS`, null-or-object entries, `interval` in `INTERVALS`. No `NAME_RE`, no directory validation (inc 1 has neither field). | ✓ |
| `bosun/detect.py` | `detect_ecosystems(root) -> tuple[str,...]` — registry-order ids of the `always_on=False` specs whose markers exist (pathlib only); **never surfaces github-actions** (always-on, added by scaffold). | ✓ |
| `bosun/plan.py` | Frozen `Update{package_ecosystem, directory, interval}` and `DependabotPlan{version: int, updates: tuple[Update,...]}`. `build_plan(cfg)` emits one `Update(spec.package_ecosystem, "/", ecfg.interval)` per configured ecosystem in REGISTRY order. | ✓ |
| `bosun/render.py` | `render(plan) -> str` via a hand-rolled emitter: `version: 2` bare (Dependabot requires the integer); the `updates:` list with `package-ecosystem`/`directory`/`schedule.interval` as double-quoted scalars (ported `_quote`). No `iter_run_blocks`/whitelist. Same plan → byte-identical text. | ✓ |
| `bosun/scaffold.py` | `propose_config(signals) -> dict` (ALWAYS includes `githubActions` + each detected stack; validates every id/interval; `ValueError` naming a bad field; guaranteed to load); `DEPENDABOT_FILES() -> [".bosun.json", ".github/dependabot.yml"]`; `classify_files`. | ✓ |
| `skills/init/SKILL.md` | `bosun:init`. Frontmatter exactly `name`+`description`, `name == "init"`. | — |
| `.claude-plugin/plugin.json` | name `bosun`, version `0.1.0`, keywords `[dependencies, dependabot, github-actions, updates]`. | — |
| `tests/` | pytest suite + `tests/golden/`. **No `tests/__init__.py`.** | — |

## The config file: `.bosun.json`

Committed, camelCase, validated by `config.load_config`. One required key
`ecosystems` (NOT `stacks` — github-actions is not a language stack): a non-empty
map keyed by bosun ecosystem id (`githubActions` | `python` | `node`; camelCase,
aligned with the sibling stack ids where they exist). Each value is `null` (use
defaults) or an object with an optional `interval` (enum `daily`|`weekly`|`monthly`,
default `weekly`). Unknown id / interval outside enum / non-object entry / empty
`ecosystems` / non-object root → `ConfigError` naming the field. Ids map to
Dependabot's `package-ecosystem` vocabulary via the registry
(`githubActions`→`github-actions`, `python`→`pip`, `node`→`npm`), never in the config.

Example: `{"ecosystems": {"githubActions": {}, "python": {"interval": "monthly"}}}`

## What it scaffolds

Two files: `.bosun.json` (exclusive-create) and `.github/dependabot.yml` (rendered,
exclusive-create — no-clobber; a pre-existing foreign one stops init, no merge in
inc 1). shipyard's committed `.bosun.json = {"ecosystems": {"githubActions": {}}}`
renders:

```
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```

## Dogfood

shipyard is stdlib-only Python with **no** `pyproject.toml`/`setup.py`/`setup.cfg`/
`requirements.txt` and **no** `package.json`, so by the hybrid detection rule its
only ecosystem is the always-on **github-actions** — honestly github-actions-only,
not a fabricated pip entry. A real, net-new artifact that keeps the pinned action
refs across keel's `changelog.yml`, rigging's `ci.yml`, and hull's `security.yml`
(`actions/checkout@v4`, `actions/setup-python@v5`, `gitleaks/gitleaks-action@v2`)
current. `test_dogfood.py` (mirroring rigging/hull/ballast): `load_config(REPO)` not
None; `render(build_plan(load_config(REPO))) == committed .github/dependabot.yml`
byte-for-byte; the github-actions entry is present; the declarative-only guard
(`${{` and `run:` never appear).

**Required cross-plugin integration (ballast owns `pytest.ini`)** — the five-edit
lockstep, as one atomic PR: (a) `.ballast.json` gains `plugins/bosun/tests`
(testPaths) + `plugins/bosun` (pythonPath); (b) re-render `pytest.ini` via ballast;
(c) regenerate `plugins/ballast/tests/golden/monorepo.ini`; (d) update ballast's
`test_render.py` inline monorepo fixture; (e) extend ballast's `test_dogfood.py`
`test_rendered_testpaths_include_every_plugin` to include `plugins/bosun/tests`.

## Distribution

Registered in `.claude-plugin/marketplace.json` (`source ./plugins/bosun`, category
`workflow`), version `0.1.0`.

## Scope

**In scope (inc 1):** the pure `config → detect → plan → render` engine, the
`githubActions`/`python`/`node` ecosystem registry, `.bosun.json`, `dependabot.yml`
emission + the declarative-only guard, the `bosun:init` skill, the net-new dogfood +
the ballast lockstep, marketplace registration. Version `0.1.0`.

**Deferred:**
- More ecosystems (docker, gomod, cargo, bundler, maven, gradle, composer,
  gitsubmodule, terraform, …) — the registry grows additively.
- Renovate (heavier, non-native).
- Dependency vulnerability scanning — a future hull increment, never bosun.
- Per-ecosystem `directory` / monorepo `directories:` (needs a leading-`/`
  path validator — the inverse of ballast's rule); advanced knobs
  (open-pull-requests-limit, groups, ignore/allow, labels, reviewers,
  commit-message, versioning/rebase-strategy, target-branch, registries);
  richer schedule (day/time/timezone); subdirectory detection; migrating a
  foreign `dependabot.yml` (inc 1 is strict no-clobber); interactive config edit.
