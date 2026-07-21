# rigging — design spec (increment 1)

**Suite:** Shipyard
**Plugin:** rigging (second member, after keel)
**Increment:** 1 of rigging
**Date:** 2026-07-20

## What rigging is

rigging authors CI pipelines. It is the Shipyard sibling that keel deliberately
defers CI and stack tooling to (keel:init writes no `.gitignore`/`.editorconfig`
and does no stack detection). Where keel owns the *git* lifecycle, rigging owns
the *build* lifecycle: turning a repo's stack into a correct, safe GitHub Actions
workflow — centrally, as a plugin, so the logic updates without every repo
forking a template.

Increment 1 ships **rigging v0.1.0**: a stdlib-only pure engine that authors one
injection-safe GitHub Actions **test** workflow per repo, driven by a data-only
stack registry (Python + Node), plus a single `rigging:init` skill that detects
the stack(s), proposes and confirms a committed `.rigging.json`, and scaffolds
the workflow with absolute no-clobber.

## Why increment 1 is scoped this way

Like keel increment 1 was the rule engine (not every skill), rigging increment 1
is the authoring engine (not every job type). The irreducible core of "author a
CI pipeline" is: **detect stack → build a workflow model → render safe YAML**,
with untrusted GitHub context structurally barred from `run:` steps. Two stacks
(not one, not three): one stack proves nothing about the registry being genuinely
data-driven; two forces it and exercises the polyglot multi-job path; a third
(go) adds cost without a new pattern. Everything else — more stacks, lint/build
jobs, caching, custom commands, hooks, cross-plugin reads — defers behind a clean
data seam.

## Architecture

rigging mirrors keel's proven separation: a **pure engine** (data in, data out,
no subprocess/IO — enforced by an AST purity test), with all IO and interaction
pushed to the `rigging:init` skill, which gathers signals via bash and calls the
pure functions. Stdlib only, Python 3.9+ (`from __future__ import annotations`
where `X | None` appears; no `match`).

The one intentional divergence from keel: **there is no `templates/` directory.**
keel scaffolds static files, so a templates dir kept byte-identical to live copies
by a drift guard is the right model. rigging *generates* its artifact, so
`render()` over the data registry is the single source of truth. keel's
byte-identity drift guard is reproduced honestly for a generator, as a **dogfood
test**: `render(shipyard's own .rigging.json)` must equal the committed
`.github/workflows/ci.yml` byte-for-byte, plus golden fixtures pin the
non-dogfooded stack combinations.

### Module layout (all under `plugins/rigging/`)

| Path | Responsibility | Pure |
|------|----------------|------|
| `rigging/__init__.py` | `__version__ = "0.1.0"` (matches plugin.json, pinned by smoke test) | ✓ |
| `rigging/stacks.py` | The stack REGISTRY as pure data — the extensibility seam. Frozen `StackSpec`/`Step` dataclasses and `REGISTRY` (python, node): each spec = id, detect files, setup action (`uses`), matrix var, default versions, and **literal** run commands (first-party actions only). `STACK_IDS` derives from `REGISTRY`. rigging's analog of keel's `TOPOLOGIES`/`STRATEGIES` data tuples. | ✓ |
| `rigging/config.py` | `load_config(root) -> Config \| None`; `ConfigError` on any invalid value (keel/config.py mirror). Validates each `stacks` key against `stacks.STACK_IDS` (unknown → ConfigError listing allowed ids), each version string against a safe charset, and `name` against a filename-safe charset so it cannot escape `.github/workflows/`. Preserves stacks key order. | ✓ |
| `rigging/detect.py` | `detect_stacks(root) -> tuple[str, ...]` — registry ids whose detect files exist, ordered by `REGISTRY`; pathlib existence only. Feeds the skill's proposal; the committed, confirmed config (not detection) is the authority at render time. | ✓ |
| `rigging/plan.py` | `build_plan(cfg) -> CiPlan` — one `Job` per configured stack, in config order, mapping validated config + registry into a render-ready plan. | ✓ |
| `rigging/render.py` | `render(plan) -> str` — a deterministic stdlib emitter that double-quotes every scalar (so `"3.10"` cannot coerce to the float `3.1`), top-level `permissions: contents: read`, and exposes `iter_run_blocks(yaml)` reused by the security test (and the future workflow-injection hook). The single source of truth for output; no templates dir. | ✓ |
| `rigging/scaffold.py` | Pure skill helpers (keel/scaffold.py mirror): `propose_config(signals)` → camelCase dict guaranteed to round-trip through `load_config`; `classify_files(root, candidates)` present/absent no-clobber map; `CI_FILES` candidate list. Invalid signals raise `ValueError` naming the field. | ✓ |
| `skills/init/SKILL.md` | The one shipped skill, `rigging:init`. Frontmatter exactly `name`+`description`, `name == dir` (`init`). | — |
| `.claude-plugin/plugin.json` | Manifest: name `rigging`, version `0.1.0`, license MIT, keywords `[ci, github-actions, workflow]`. | — |
| `tests/` | pytest suite + `tests/golden/*.yml`. Added to `pytest.ini` `testpaths` and `pythonpath` (both become multi-value, keeping keel's entries). | — |

### Data flow

```
signals (skill gathers) ─▶ detect_stacks ─▶ propose_config ─▶ .rigging.json (committed, confirmed)
                                                                     │
                                                    load_config ─────┘
                                                         │
                                                    build_plan ─▶ CiPlan ─▶ render ─▶ ci.yml (no-clobber write)
```

## The config file: `.rigging.json`

Committed, camelCase, read by `config.load_config` (returns `Config | None`,
raises `ConfigError` on anything invalid — mirrors `.keel.json`).

- `name` — optional string, default `"ci"`. It is both the workflow `name:` and
  the output filename stem `.github/workflows/<name>.yml`. **Must match
  `^[A-Za-z0-9_-]+$`** so it cannot escape the workflows directory.
- `stacks` — **required** object, ≥1 entry. Each key must be a known registry id
  (`python` | `node`); unknown ids raise `ConfigError` listing the allowed ids.
  Each value is an optional object with optional `versions` — a non-empty array
  of strings, each matching a safe charset `^[A-Za-z0-9][A-Za-z0-9._+-]*$`
  (closes YAML-structure injection via versions); omitted → the stack's registry
  default. **Object key order is preserved and fixes job order.**

Deliberately **no** `schemaVersion`, `triggers`, `concurrency`, `runsOn`,
`packageManager`, or install/test-command keys: triggers are hardcoded
`on: [push, pull_request]`, runner hardcoded `ubuntu-latest`, and `run:` bodies
come only from registry literals (never from config strings). All deferred.

Example: `{"name": "ci", "stacks": {"python": {"versions": ["3.9", "3.12"]}, "node": {}}}`
Shipyard's own committed dogfood source: `{"stacks": {"python": {"versions": ["3.9", "3.12"]}}}`.

## Stacks (increment 1)

- **python** — detected when `pyproject.toml`, `setup.py`, `setup.cfg`, or
  `requirements.txt` exists at repo root. Setup via `actions/setup-python@v5`,
  matrix var `python`, default versions `("3.12",)`. Literal run steps:
  `pip install pytest`, then `python -m pytest`. (pip + pytest; poetry/pdm nuance
  deferred.)
- **node** — detected when `package.json` exists at repo root. Setup via
  `actions/setup-node@v5`, matrix var `node`, default versions `("20",)`. Literal
  run steps: `npm ci`, then `npm test`. (pnpm/yarn inference deferred.)

Both use only first-party actions (`actions/checkout@v4`, `setup-python`,
`setup-node`) to keep the increment-1 action set supply-chain-minimal. A polyglot
repo detected as both yields two jobs, exercising the multi-job path.

## Security — injection-safe by construction

The exact lesson from keel:init's Critical finding, applied preventively.

1. **Structural guarantee.** `run:` scripts are composed **only** from literal
   `Step.run` strings declared in `stacks.py`. `render()` has no code path that
   interpolates any `${{ ... }}` expression into a `run:` block. The only
   expression rigging emits anywhere is `${{ matrix.<var> }}` inside a `with:`
   input, whose values are author-controlled, charset-restricted version strings
   from `.rigging.json` — never `github.*` context. Increment 1 references **zero**
   `github.*` context. Generated workflows carry top-level `permissions: contents: read`.
2. **Data-layer test** (`tests/test_injection.py`) — the direct analog of keel's
   AST purity test, enforcing the invariant in-band against future contributors:
   - every `Step.run` line in `REGISTRY` contains no `${{` (a future stack
     contribution cannot smuggle an expression in);
   - every rendered `run:` block, across all single-stack plans and the polyglot
     plan (via `render.iter_run_blocks`), contains no `${{`;
   - every `${{ ... }}` in rendered output matches exactly
     `^\$\{\{\s*matrix\.[a-z0-9_]+\s*\}\}$`;
   - the substring `github.` appears in no rendered workflow;
   - a hostile `versions` value (whitespace/newline/`}}`) and a `name` with `../`
     or a slash each raise `ConfigError`.

The env-binding pattern (bind untrusted `github.*` to a step's `env:` as a quoted
value, reference as a shell `$VAR` — keel's own changelog.yml pattern) is
documented but not needed until a stack consumes github context; deferred with
its own test.

## Testing

Every module is pure and independently testable. Suite: `test_purity.py` (AST
harness copied from keel; `PURE_MODULES = (config, stacks, detect, plan, render,
scaffold)`), `test_config.py`, `test_stacks.py`, `test_detect.py`, `test_plan.py`,
`test_render.py` (golden byte-identity for python/node/polyglot; the `"3.10"`
float-coercion quoting case; determinism), `test_injection.py` (the five security
assertions), `test_scaffold.py` (round-trip for every stack subset; nested
`.github/workflows/<name>.yml` present/absent), `test_dogfood.py`
(`render(load_config(REPO))` == committed `ci.yml` byte-for-byte, and asserts the
workflow invokes pytest), `test_smoke.py` (version, plugin.json, marketplace.json
lists rigging, SKILL.md frontmatter).

## Dogfood

rigging regenerates shipyard's own `.github/workflows/ci.yml`. Shipyard commits a
`.rigging.json` of `{"stacks": {"python": {"versions": ["3.9", "3.12"]}}}`; the
committed `ci.yml` is replaced by rigging's generated output (reconciling the
current hand-written one so **live == generated by construction**), and
`test_dogfood.py` pins the byte-identity. The live GitHub run of that file — which
already runs pytest on the 3.9/3.12 matrix — is standing proof the hand-rolled
emitter produces valid YAML (stdlib has no YAML parser; golden fixtures + the
real run cover validity).

Note: the regenerated `ci.yml` uses the increment-1 hardcoded trigger
`on: [push, pull_request]`, replacing the current `on: push [main, develop] +
pull_request`. This runs the suite on all pushes; acceptable and simpler, and the
`develop` branch filter was already vestigial (shipyard is trunk topology).

## Distribution

rigging is added to `.claude-plugin/marketplace.json` (`source ./plugins/rigging`,
category `workflow`), so the existing `/plugin marketplace add` delivers it
alongside keel.

## Scope

**In scope (increment 1):** the pure `config → detect → plan → render` engine,
the python + node data registry, `.rigging.json`, the `rigging:init` skill,
injection-safety by construction + its data-layer test, the dogfood drift guard,
and marketplace registration. Version `0.1.0`.

**Deferred to later increments:**
- Additional stacks (go, php/laravel, rust, ruby, java) — each is one pure-data
  `StackSpec`; some need third-party setup actions (a supply-chain decision).
- Job types beyond test: lint, format, type-check, build, release/deploy.
- Custom install/test commands in config — excluded so `run:` bodies stay
  registry-literal; a later increment adds them with an explicit shell-quoting test.
- Dependency caching (`setup-*` `cache:` input).
- Configurable triggers, branch filters, OS matrix, concurrency, finer permissions.
- The env-binding pattern for a stack that legitimately needs `github.*` context.
- Reading `.keel.json` (read-only) to align CI trigger branches to keel's
  production/integration branches.
- Hooks: a `PreToolUse` guard warning when a hand edit puts `${{ github.* }}`
  inside a `run:` step (reusing `render.iter_run_blocks`), and a SessionStart
  orient/drift hook — scoped to increment 2 once regeneration exists.
- Extra skills: `rigging:regenerate`, `rigging:doctor`, `rigging:add-stack`.
- Non-GitHub CI providers; merging/managing pre-existing foreign workflows
  (strict no-clobber only).
