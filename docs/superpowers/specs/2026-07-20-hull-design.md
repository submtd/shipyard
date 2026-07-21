# hull — design spec (increment 1)

**Suite:** Shipyard
**Plugin:** hull (fifth member; after keel, rigging, stow, ballast)
**Increment:** 1 of hull
**Date:** 2026-07-20

## What hull is

hull is the security-scanning sibling. Increment 1's unique, non-overlapping
slice is **detect-committed-secrets-in-CI**: it authors one injection-safe GitHub
Actions workflow, `.github/workflows/security.yml`, that runs a pinned gitleaks
action on push and pull_request, rendered deterministically from a tiny
`.hull.json`. Secret scanning is the highest-value, most universally-applicable,
most YAGNI security concern, and gives an honest dogfood on any repo.

hull is essentially "rigging for security workflows" — it reuses rigging's proven
render + injection-safety machinery, along a scanner-family axis instead of a
per-language stack axis.

## The CI-workflow boundary with rigging

Resolved by **filename ownership**, settled by real repo precedent: **keel already
authors `.github/workflows/changelog.yml` beside rigging's `ci.yml`.** So "rigging
owns CI authoring" means rigging owns the *test/build pipeline* (`ci.yml`), not a
monopoly on `.github/workflows/`. The codebase-proven reading is
one-workflow-per-owner with disjoint filenames: rigging = `ci.yml`, keel =
`changelog.yml`, hull = `security.yml`; no plugin co-writes a file another owns.
hull authors and owns `security.yml` and never touches `ci.yml`. It reuses
rigging's injection-safe *pattern* by copy (rigging's renderer is not a shared
dependency), exactly as stow and ballast each own their own renderer. The only
collision path — a user naming the hull workflow `ci` — is blocked by the default
`security` + classify no-clobber + exclusive-create, and the skill warns.

## Architecture

Mirrors rigging: a stdlib-only pure engine (AST-purity-guarded), Python 3.9+, all
I/O in the `hull:init` skill. **No `stacks.py`/`detect.py`** — secret scanning is
language-independent, so hull intentionally omits the per-language registry
(forcing one on a whole-repo scanner would be cargo-culting). The scanner registry
is hull's equivalent data seam; stacks/detect earn their place only when
dependency-audit arrives (inc 2+).

| Path | Responsibility | Pure |
|------|----------------|------|
| `hull/__init__.py` | `__version__ = "0.1.0"` | ✓ |
| `hull/scanners.py` | Pure-data scanner registry (the seam; analog of rigging/stacks.py along the SCANNER axis). Frozen `ScannerSpec` for gitleaks: pinned action ref `gitleaks/gitleaks-action@v2`, checkout `fetch-depth "0"` (full-history scan), env `{GITHUB_TOKEN: "${{ secrets.GITHUB_TOKEN }}"}`. `REGISTRY`, `SCANNER_IDS`. The single home for every pinned third-party ref and the one whitelisted expression. No registry `run` step contains `${{`. | ✓ |
| `hull/config.py` | `load_config(root) -> Optional[Config(name, scanner)]`; absent → None; invalid → `ConfigError` naming the field. `name` via `NAME_RE.fullmatch` (default `"security"`); `scanner` in `scanners.SCANNER_IDS` (default `"gitleaks"`). Mirrors rigging/config.py. | ✓ |
| `hull/plan.py` | `build_plan(cfg) -> ScanPlan(name, jobs)`. One `Job` (id = scanner id, `runs-on ubuntu-latest`, **NO matrix** — stack-agnostic), steps = pinned checkout (fetch-depth 0) + the scanner's `uses` step with its env. Least-privilege `permissions: contents: read`. | ✓ |
| `hull/render.py` | `render(plan) -> str` deterministic GitHub Actions YAML. Ports rigging's `_quote` (every scalar double-quoted) and `iter_run_blocks` (for the injection test). Emits `on: [push, pull_request]` and `permissions: contents: read`. Same plan in → byte-identical out. | ✓ |
| `hull/scaffold.py` | Pure init helpers (rigging/scaffold.py minus stack detection): `propose_config(signals) -> dict` (validated, `ValueError` naming a bad field, guaranteed to load); `SECURITY_FILES(name) -> [".hull.json", ".github/workflows/<name>.yml"]`; `classify_files`. | ✓ |
| `skills/init/SKILL.md` | `hull:init`. Frontmatter exactly `name`+`description`, `name == "init"`. | — |
| `.claude-plugin/plugin.json` | name `hull`, version `0.1.0`, keywords `[security, secrets, gitleaks, github-actions]`. | — |
| `tests/` | pytest suite + `tests/golden/`. **No `tests/__init__.py`.** | — |

## The config file: `.hull.json`

Committed, camelCase, validated by `config.load_config`. Two optional validated
fields:

- `name` — string, default `"security"`, `NAME_RE.fullmatch` (fullmatch, not
  `match`+`$`, so a trailing newline or a hostile expression string is rejected
  before render). Drives BOTH the workflow filename `.github/workflows/<name>.yml`
  AND the workflow's internal `name:`, so they agree by construction.
- `scanner` — string, default `"gitleaks"`, must be in `scanners.SCANNER_IDS`
  (only `"gitleaks"` in inc 1). The cheap extensibility axis + validation seam.

No `stacks` key. Example: `{"name": "security", "scanner": "gitleaks"}`

## What it scaffolds

Exactly two files: (1) `.hull.json` (exclusive-create). (2)
`.github/workflows/security.yml` — the rendered workflow: gitleaks
(`gitleaks/gitleaks-action@v2`) on push + pull_request, `actions/checkout@v4`
`fetch-depth: 0`, top-level `permissions: contents: read`, `GITHUB_TOKEN` passed
only as an `env:` value on the scanner's `uses` step (never in a `run:` command).
The job fails the PR when a committed secret is detected. **No** `.gitleaks.toml`
(gitleaks ships a default ruleset), SECURITY.md, CodeQL, dependency audit, or
scheduled sweep in inc 1 — all deferred.

## Injection safety (by construction — rigging's discipline, hull's whitelist)

A workflow is emitted, so injection-safety is mandatory. The single expression
hull emits is `${{ secrets.GITHUB_TOKEN }}`, appearing ONLY as an `env:` value on
the gitleaks `uses:` step (keel's own `changelog.yml` pattern — secrets via `env:`,
never interpolated into a `run:`). Inc 1 has zero `run` steps consuming it and zero
`github.*` refs. `permissions: contents: read` (least privilege).

`test_injection.py` mirrors rigging's five assertions with hull's whitelist:
1. **Data layer** — no `ScannerSpec` run step in the registry contains `${{`.
2. **Rendered layer** — `iter_run_blocks` finds no `${{` in any run block.
3. **Load-bearing** — every `${{ ... }}` in the output must fullmatch
   `^\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}$` (never `github.*`, never weakened).
4. **Incidental** — `github.` never appears in default output.
5. **End-to-end** — a hostile `name` (`${{ github.token }}`, `x}}`, `a; rm -rf`)
   is rejected by `load_config` (NAME_RE.fullmatch) BEFORE render can run.

The render module has no code path to emit any other expression, so the property
holds by construction.

## Dogfood

Net-new: shipyard has no `SECURITY.md`, no `security.yml`, no gitleaks config
today, so hull dogfoods by ADDING `.hull.json` + `.github/workflows/security.yml`
(not editing existing files). `test_dogfood.py` asserts: `load_config(REPO)` is not
None; `render(build_plan(load_config(REPO))) == (REPO/".github/workflows/security.yml").read_text()`
byte-for-byte (the drift guard); the workflow references the pinned gitleaks action.
The plugin suite that authors secret-scanning becomes secret-scanned itself,
full-history, on every push and PR — and it passes clean on a repo with no
committed secrets.

**Required cross-plugin integration (ballast now owns `pytest.ini`):** register
hull in `.claude-plugin/marketplace.json`; add `plugins/hull/tests` to
`.ballast.json` `testPaths` and `plugins/hull` to `pythonPath`, then **re-render
`pytest.ini` via ballast** (keeping ballast's own dogfood green); and **extend
ballast's `test_dogfood` per-plugin-testpath assertion** (it currently enumerates
the four existing plugin dirs) to include `plugins/hull/tests`.

## Distribution

Registered in `.claude-plugin/marketplace.json` (`source ./plugins/hull`, category
`workflow`), version `0.1.0`.

## Scope

**In scope (inc 1):** the pure `config → plan → render` engine, the gitleaks
scanner registry, `.hull.json`, injection-safe `security.yml` emission + its test,
the `hull:init` skill, the net-new dogfood + cross-plugin integration, marketplace
registration. Version `0.1.0`.

**Deferred:**
- SECURITY.md vulnerability-disclosure policy (keel-style static/no-clobber, inc 2).
- `.gitleaks.toml` custom ruleset / allowlist (render-from-data, inc 2).
- SAST/CodeQL workflow and dependency-VULNERABILITY audit (pip-audit/npm audit) —
  future hull increments where `stacks.py`/`detect.py` finally earn their place and
  python+node re-enter. (Dependency *updates* are bosun's, not hull's.)
- Additional scanners (trufflehog) via the `SCANNER_IDS` seam; scheduled sweeps;
  SARIF upload; PR-comment posting; SHA-pinning the action; private-org
  `GITLEAKS_LICENSE` wiring; a hand-edit-warning hook; merge/repair of an existing
  config (inc 1 is keep-theirs / no-clobber only); any `hull:scan`/`hull:doctor`
  skill (hull authors text; scanners run in CI).
