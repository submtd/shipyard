# bosun increment 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build bosun v0.1.0 — a stdlib-only pure engine that renders `.github/dependabot.yml` from a committed `.bosun.json` (hybrid ecosystem model: `github-actions` always-on + detected pip/npm), plus a `bosun:init` skill, dogfooded net-new on shipyard (github-actions only).

**Architecture:** Mirror rigging/hull: pure `config → detect → plan → render` engine driven by an ecosystem registry. `render` is a policy-free function of the committed config (always-on policy lives in detect/scaffold), so the byte-identity dogfood holds. NO injection machinery (dependabot.yml is declarative; `directory` fixed at `/`); a declarative-only guard (`${{`/`run:` never appear) replaces hull's injection test.

**Tech Stack:** Python 3.9+, stdlib only. pytest.

## Global Constraints

- **Runtime deps: stdlib only.** Python 3.9+ (`from __future__ import annotations`; no `match`).
- **The engine is pure.** `ecosystems.py`, `config.py`, `detect.py`, `plan.py`, `render.py`, `scaffold.py` MUST NOT import `subprocess`/`os`/networking. An AST `test_purity.py` enforces this.
- **`.bosun.json` keys are camelCase.** `config.load_config(root) -> Optional[Config]` returns `None` when absent, raises `ConfigError` on any invalid-but-present file.
- **No injection surface.** `render` output must never contain `${{` or a `run:` line (declarative-only, asserted). `directory` is fixed at `"/"` in the plan (not a config field). Charset/enum validators use `fullmatch`/membership.
- Skill frontmatter uses **only** `name` and `description`; `name` MUST equal the dir (`init`).
- **No `plugins/bosun/tests/__init__.py`** (repo-wide guard forbids `plugins/*/tests/__init__.py`).
- Work on branch `feature/bosun` (already created off `main`). Do NOT switch branches. Commit with `git -c user.name="Steve Harmeyer" -c user.email="harmeyersteve@gmail.com"`.
- New plugin → version **0.1.0**.

---

## File Structure

```
plugins/bosun/
├── bosun/  __init__.py ecosystems.py config.py detect.py plan.py render.py scaffold.py   [all pure]
├── skills/init/SKILL.md
├── .claude-plugin/plugin.json
└── tests/  (NO __init__.py)  golden/ + test_{smoke,ecosystems,detect,config,plan,render,scaffold,purity,dogfood}.py
```

Also modified: `.claude-plugin/marketplace.json`; the **ballast lockstep** (`.ballast.json`, `pytest.ini`, `plugins/ballast/tests/golden/monorepo.ini`, `plugins/ballast/tests/test_render.py` inline fixture, `plugins/ballast/tests/test_dogfood.py`); `CHANGELOG.md`, `README.md`. New: `.bosun.json`, `.github/dependabot.yml`.

---

### Task 1: Skeleton, registry, marketplace, and the ballast pytest lockstep

**Files:** Create `plugins/bosun/bosun/__init__.py`, `plugins/bosun/.claude-plugin/plugin.json`, `plugins/bosun/bosun/ecosystems.py`; Modify `.claude-plugin/marketplace.json`, `.ballast.json`, `pytest.ini`, `plugins/ballast/tests/golden/monorepo.ini`, `plugins/ballast/tests/test_render.py`; Test `plugins/bosun/tests/test_ecosystems.py`, `plugins/bosun/tests/test_smoke.py`.

**Interfaces — Produces:**
- `bosun.__version__ == "0.1.0"`.
- `ecosystems.EcosystemSpec` — frozen: `id: str`, `package_ecosystem: str`, `detect_files: tuple[str,...]`, `always_on: bool`.
- `ecosystems.REGISTRY` (insertion order): `githubActions → EcosystemSpec("githubActions","github-actions",(),True)`; `python → EcosystemSpec("python","pip",("pyproject.toml","setup.py","setup.cfg","requirements.txt"),False)`; `node → EcosystemSpec("node","npm",("package.json",),False)`.
- `ecosystems.ECOSYSTEM_IDS = tuple(REGISTRY)`; `ecosystems.INTERVALS = ("daily","weekly","monthly")`.

`plugin.json`: `{"name":"bosun","displayName":"bosun","version":"0.1.0","description":"Authors a Dependabot config (.github/dependabot.yml) to keep a repo's dependencies updated.","license":"MIT","keywords":["dependencies","dependabot","github-actions","updates"]}`.

**BALLAST LOCKSTEP (do it here so bosun tests collect):** ballast owns `pytest.ini`.
1. `.ballast.json`: append `plugins/bosun/tests` to `stacks.python.testPaths` (last) and `plugins/bosun` to `pythonPath` (last).
2. Re-render `pytest.ini` via ballast: `python3 -c "import sys; sys.path.insert(0,'plugins/ballast'); from ballast.config import load_config; from ballast.render import render; from pathlib import Path; open('pytest.ini','w').write(render(load_config(Path('.'))))"`.
3. Update `plugins/ballast/tests/golden/monorepo.ini` to add the two bosun lines (it must stay byte-identical to the new `pytest.ini` — ballast's `test_monorepo_golden_matches_shipyards_committed_pytest_ini` enforces this).
4. Update the inline monorepo config fixture in `plugins/ballast/tests/test_render.py` to include `plugins/bosun/tests` + `plugins/bosun`.
(Task 7 does the 5th lockstep edit: ballast's `test_dogfood` per-plugin assertion. Confirm ballast's full suite is green after these edits.)

- [ ] **Step 1: Write failing tests** — `test_ecosystems.py`: `REGISTRY` keys `("githubActions","python","node")`; each spec's fields exact; `githubActions.always_on and githubActions.detect_files==()`; `python`/`node` `always_on==False` with the shared markers; `ECOSYSTEM_IDS==tuple(REGISTRY)`; `INTERVALS==("daily","weekly","monthly")`; frozen. `test_smoke.py`: version 0.1.0; plugin.json name/version; marketplace lists bosun.
- [ ] **Step 2: Run to verify fail.**
- [ ] **Step 3: Implement** skeleton + plugin.json + marketplace + ecosystems.py + the ballast lockstep (1–4).
- [ ] **Step 4: Run** test_ecosystems+test_smoke green, then FULL suite `python3 -m pytest -q` (keel 296 + rigging 130 + stow 163 + ballast 129 [must stay green after the lockstep] + hull 90 + new bosun; no shadowing). Confirm ballast's monorepo-golden + render tests are green.
- [ ] **Step 5: Commit** `feat(bosun): skeleton, ecosystem registry, marketplace, ballast pytest lockstep`.

---

### Tasks 2+3: `config.py` + `detect.py` (bundle into one commit)

**Files:** Create `plugins/bosun/bosun/config.py`, `plugins/bosun/bosun/detect.py`; Test `plugins/bosun/tests/test_config.py`, `plugins/bosun/tests/test_detect.py`.

**config.py interfaces:** `ConfigError`; frozen `EcosystemConfig{interval: str}`; frozen `Config{ecosystems: dict[str, EcosystemConfig]}`; `load_config(root) -> Optional[Config]`. Rules: absent → None; unreadable/invalid JSON/non-object → ConfigError. `ecosystems` required non-empty object; each key in `ECOSYSTEM_IDS` (unknown → ConfigError naming it + allowed ids); each value `null`/object → `EcosystemConfig`; `interval` optional (default `"weekly"`) must be in `INTERVALS` else ConfigError naming `interval`. Preserve key order.

**detect.py interfaces:** `detect_ecosystems(root) -> tuple[str,...]` — registry-order ids of `always_on=False` specs whose `detect_files` exist at root; pathlib only; **github-actions never surfaced**.

- [ ] **Step 1: Write failing tests** — config: absent→None; `{"ecosystems":{"githubActions":{}}}` loads (interval default "weekly"); `{"ecosystems":{"python":{"interval":"monthly"}}}`; unknown id `{"ecosystems":{"ruby":{}}}` → ConfigError naming it + allowed ids; empty `ecosystems` / non-object root / non-object entry / interval "hourly" → ConfigError; daily/weekly/monthly all accepted; key order preserved. detect: each python marker → `("python",)`; package.json → `("node",)`; both → `("python","node")`; empty → `()`; github-actions never in the result.
- [ ] **Step 2–4:** verify fail → implement (mirror rigging/config.py + detect.py; use `fullmatch` where any regex is used, though membership is the gate) → green + full suite.
- [ ] **Step 5: Commit** `feat(bosun): .bosun.json loader and ecosystem detection`.

---

### Task 4: `plan.py`

**Files:** Create `plugins/bosun/bosun/plan.py`; Test `plugins/bosun/tests/test_plan.py`.

**Interfaces:** frozen `Update{package_ecosystem: str, directory: str, interval: str}`; frozen `DependabotPlan{version: int, updates: tuple[Update,...]}`. `build_plan(cfg) -> DependabotPlan` — `version=2`; one `Update(ecosystems.REGISTRY[id].package_ecosystem, "/", ecfg.interval)` per `id` in `cfg.ecosystems`, emitted in **REGISTRY order** (not config key order).

- [ ] **Step 1: Write failing tests** — a config with `{node, python, githubActions}` (reversed) → updates in REGISTRY order (github-actions, pip, npm); each Update's `package_ecosystem` from the registry, `directory=="/"`, `interval` from config; `version==2`; `updates` is a tuple; deterministic.
- [ ] **Step 2–4:** verify fail → implement → green + full suite.
- [ ] **Step 5: Commit** `feat(bosun): build a Dependabot plan from config`.

---

### Task 5: `render.py` + golden + declarative-only guard

**Files:** Create `plugins/bosun/bosun/render.py`, `plugins/bosun/tests/golden/{shipyard,multi,defaults}.yml`; Test `plugins/bosun/tests/test_render.py`.

**Interfaces:** `render.render(plan: DependabotPlan) -> str`. Emit `version: 2` (bare integer), then `updates:` with one entry per Update:
```
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
```
- `version: 2` bare. Each string VALUE double-quoted (port rigging/hull `_quote`). Exactly one trailing newline. Deterministic.

- [ ] **Step 1: Hand-author goldens** — `golden/shipyard.yml` (github-actions only, interval weekly), `golden/multi.yml` (github-actions + pip + npm), `golden/defaults.yml` (a single ecosystem with the default interval). Write `test_render.py`: `render(build_plan(load_config(<fixture>)))` == each golden byte-for-byte; determinism; output starts `version: 2` bare; string scalars quoted; one trailing newline; **declarative-only guard: `"${{" not in output` AND no line is a `run:` step (`"run:" not in output`)** — this replaces hull's injection test.
- [ ] **Step 2: Verify fail.** **Step 3: Implement** render.py (match goldens). **Step 4:** green + full suite.
- [ ] **Step 5: Commit** `feat(bosun): deterministic dependabot.yml emitter with golden fixtures`.

---

### Task 6: `scaffold.py` + purity test

**Files:** Create `plugins/bosun/bosun/scaffold.py`; Test `plugins/bosun/tests/test_scaffold.py`, `plugins/bosun/tests/test_purity.py`.

**Interfaces:**
- `scaffold.DEPENDABOT_FILES() -> [".bosun.json", ".github/dependabot.yml"]`.
- `scaffold.classify_files(root, candidates) -> dict`.
- `scaffold.propose_config(signals) -> dict` — ALWAYS includes `githubActions`, plus each id in `signals["ecosystems"]` (the detected stacks); optional per-ecosystem `interval`. Validates each id against `ECOSYSTEM_IDS` and `interval` against `INTERVALS`; raises `ValueError` naming the bad field; guaranteed to round-trip through `config.load_config`.

- [ ] **Step 1: Write failing tests** — `test_scaffold.py`: `propose_config({"ecosystems":[]})` → `{"ecosystems":{"githubActions":{}}}` (always-on) that round-trips through `load_config`; `propose_config({"ecosystems":["python"]})` includes both githubActions and python; unknown id / bad interval → `ValueError` naming the field; `DEPENDABOT_FILES()` value; `classify_files` present/absent incl the nested `.github/dependabot.yml`. `test_purity.py`: AST harness, `PURE_MODULES=("ecosystems","config","detect","plan","render","scaffold")`, hooks-dir-absent-safe.
- [ ] **Step 2: Verify fail.** **Step 3: Implement.** **Step 4: Prove purity bites** (temp `import subprocess` → fail → revert). **Step 5:** green + full suite.
- [ ] **Step 6: Commit** `feat(bosun): scaffold helpers + engine-purity AST test`.

---

### Task 7: the `bosun:init` skill

**Files:** Create `plugins/bosun/skills/init/SKILL.md`. Mirror `rigging:init` (it has detection). Frontmatter EXACTLY `name: init` + `description`.

Flow: 1. `cd` to git root. 2. 3-way `.bosun.json` check (absent → fresh; loads → already-configured, render only, don't re-propose; ConfigError → report verbatim + stop). 3. Fresh: `detect_ecosystems` (python/node) via `${CLAUDE_PLUGIN_ROOT}` one-liner; ALWAYS add `githubActions`; `propose_config`; show `.bosun.json`; confirm; exclusive-create it. 4. `classify_files(DEPENDABOT_FILES())`: if `.github/dependabot.yml` absent, `os.makedirs(".github", exist_ok=True)` then `render(build_plan(load_config(".")))` and exclusive-create; if present, no-clobber stop (report + skip). 5. Verify: reload config; re-render == disk; assert no `${{` and no `run:` in output. Report; surface the **Dependabot-enablement caveat** (committing the file activates Dependabot version-update PRs that need review); note the settled boundary (dependency VULN scanning is a future hull increment, not bosun); point at the sibling init skills.

- [ ] **Step 1:** Write SKILL.md. **Step 2:** validate frontmatter (`ok init`). **Step 3:** smoke-test the one-liners against a scratch repo with the real bosun package (CLAUDE_PLUGIN_ROOT=plugins/bosun), incl no-clobber + the declarative-only verify. **Step 4:** full suite green. **Step 5:** Commit `feat(bosun): bosun:init skill`.

---

### Task 8: Dogfood, extend ballast guard, docs

**Files:** Create `.bosun.json`, `.github/dependabot.yml`; Modify `plugins/ballast/tests/test_dogfood.py`, `CHANGELOG.md`, `README.md`; Test `plugins/bosun/tests/test_dogfood.py`.

- [ ] **Step 1: Adopt bosun on shipyard.** Write repo-root `.bosun.json = {"ecosystems": {"githubActions": {}}}` (pretty-printed, trailing newline). Render the committed config: `python3 -c "import sys, os; sys.path.insert(0,'plugins/bosun'); from bosun.config import load_config; from bosun.plan import build_plan; from bosun.render import render; from pathlib import Path; os.makedirs('.github', exist_ok=True); open('.github/dependabot.yml','w').write(render(build_plan(load_config(Path('.')))))"`. Read it back: `version: 2`, one github-actions entry, directory "/", interval weekly, no `${{`/`run:`.
- [ ] **Step 2: hull-style `test_dogfood.py`** — `REPO=parents[3]`; `load_config(REPO)` not None; `render(build_plan(load_config(REPO))) == (REPO/".github/dependabot.yml").read_text()` byte-for-byte; github-actions entry present; no `${{`/`run:`; and `golden/shipyard.yml == committed .github/dependabot.yml` (tie golden to dogfood).
- [ ] **Step 3: Extend ballast's per-plugin guard (lockstep edit 5).** Add `"plugins/bosun/tests"` to `plugins/ballast/tests/test_dogfood.py`'s `test_rendered_testpaths_include_every_plugin` hardcoded list.
- [ ] **Step 4: Docs** — CHANGELOG `## [Unreleased]` `### Added` bullet for bosun v0.1.0 (renders an injection-free `.github/dependabot.yml` from `.bosun.json`; github-actions always-on + detected pip/npm; dogfooded net-new on shipyard, keeping the suite's pinned action refs current). README: add bosun to the suite intro + status (shipped, plugin #6 — the suite is complete).
- [ ] **Step 5: Run** full suite green; changelog gate `python3 scripts/check_changelog.py main "$(git branch --show-current)"` → exit 0; confirm no `plugins/bosun/tests/__init__.py`; confirm `git diff pytest.ini` empty (Task 1 set it). Report counts.
- [ ] **Step 6: Commit** `feat(bosun): dogfood shipyard's dependabot.yml, extend ballast guard, docs`.

---

## Self-Review

**Spec coverage.** Registry → T1; the ballast lockstep → T1 (edits 1–4) + T8 (edit 5); config+detect (hybrid detection, github-actions never detected) → T2+3; plan (REGISTRY order, directory "/") → T4; the emitter + declarative-only guard → T5; scaffold (always-on githubActions) + purity → T6; the skill (no-clobber, declarative verify, Dependabot caveat) → T7; net-new dogfood → T8. No injection machinery (declarative + directory fixed) → stated. No `tests/__init__.py` → Global Constraints.

**Placeholder scan.** No TBD/TODO. Goldens authored in T5 Step 1; the dogfood `.bosun.json` is concrete in T8.

**Type consistency.** `EcosystemSpec`/`REGISTRY`/`ECOSYSTEM_IDS`/`INTERVALS` (T1) → T2–T8. `Config{ecosystems}`/`EcosystemConfig{interval}` (T2) → T4/T6/T8. `build_plan`/`Update`/`DependabotPlan` (T4) → T5/T8. `render` (T5), `propose_config`/`classify_files`/`DEPENDABOT_FILES` (T6) → T7/T8. The always-on policy lives in `detect`/`scaffold` (T2/T6), never in `render` (T5) — so the dogfood byte-identity holds.
