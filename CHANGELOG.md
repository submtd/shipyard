# Changelog

All notable changes to Shipyard plugins are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed

- Every GitHub Actions ref is now pinned to a full commit SHA with a
  trailing `# v4`-style comment, replacing the floating major-version tags
  (`actions/checkout@v4`, `gitleaks/gitleaks-action@v2`, …). A major tag is
  repointable at will by the action's owner, so it was never a pin -- yet
  README, CHANGELOG and hull's own design spec all called it one, and
  hull's `test_gitleaks_action_ref_is_pinned` accepted it. That mattered
  most in `hull`, the plugin whose entire job is supply-chain security, and
  in `gitleaks-action`, which runs with `GITHUB_TOKEN` in its environment.
  Covers the three workflows, the `keel:init` template, and the `rigging`
  and `hull` registries that generate them for downstream repos. The
  documentation's claim is now true rather than aspirational, and
  `bosun`'s `github-actions` Dependabot entry keeps the pins current.

### Fixed

- `rigging` and `hull` renderers now emit `Step.name`, which both declared
  and neither rendered -- a registry entry written as `Step(name=...)`
  silently lost it, with no error and no test. Duplicated latent bug,
  present in both because the renderer was copy-pasted before either used
  the field.

### Added

- `bosun`, Shipyard's sixth and final core plugin: renders an
  injection-free `.github/dependabot.yml` from a committed `.bosun.json`
  -- github-actions always-on plus detected pip/npm. Dogfooded net-new on
  shipyard, keeping the suite's pinned action refs current.
- `hull`, Shipyard's fifth plugin: renders an injection-safe gitleaks
  secret-scan `.github/workflows/security.yml` from a committed
  `.hull.json`. Dogfooded net-new on shipyard's own repo.
- `ballast`, Shipyard's fourth plugin: renders `pytest.ini` from a committed
  `.ballast.json` -- import-mode, testpaths, pythonpath -- so pytest collects
  the right tests. Python-only in this increment. Dogfooded on shipyard's own
  bespoke `pytest.ini`.
- `stow`, Shipyard's third plugin: manages `.gitignore` sections per
  detected stack via a managed-block splice -- idempotent, updatable in
  place, and it never clobbers user-custom lines. Ships `base`/`python`/
  `node` sections. Dogfooded on shipyard's own `.gitignore`.
- `rigging`, Shipyard's second plugin: CI pipeline authoring. Detects a
  repo's stack (`python`, `node`) and scaffolds an injection-safe GitHub
  Actions test workflow with absolute no-clobber. Dogfooded to generate
  shipyard's own `ci.yml`.
- `keel:init` — scaffolds keel's lifecycle artifacts into a repo (`.keel.json`
  with detected topology, a Keep-a-Changelog skeleton, PR/issue templates,
  CODEOWNERS, the changelog CI gate, and an optional license). Absolute
  no-clobber; a top-up mode for already-managed repos. Lifecycle only — no
  language tooling.
- CI `changelog` job that enforces keel's changelog rule server-side. The
  script is self-contained (stdlib only, no `keel` import) so the same
  script keel:init scaffolds into a repo can run there unmodified; a
  drift-guard test keeps it byte-identical to the shipped template. It
  mirrors the advisory hook's policy (release/back-merge exemptions;
  unknown never blocks). Wired into `main`'s required status checks via
  branch protection.

### Changed

- `keel`: under `trunk` topology, `pr-edge` now accepts any branch into
  production, not only `feature/*` and `hotfix/*` -- trunk-based development
  is not prefix-strict the way gitflow is. The `changelog` gate still applies
  to all trunk work branches (previously it only applied to `feature/*`/
  `hotfix/*`, silently exempting anything else).

### Fixed

- `plugin.json` no longer double-registers `hooks/hooks.json`, which Claude
  Code auto-loads by convention; the redundant reference failed on install
  with a duplicate-hooks error.

### Added

- `keel`, the first Shipyard plugin: a rule engine that models a project's
  git lifecycle as `(action, base, head, headIsFork, capability)`, with
  no notion of "role."
- An advisory `PreToolUse` hook that evaluates `git`/`gh` commands against
  the rule engine and warns or blocks before the command runs.
- A `SessionStart` orientation that reports topology, protected branches,
  review policy, and current branch, once per session.
- Ten lifecycle skills: `start-work`, `sync`, `finish-work`,
  `respond-to-review`, `review`, `land`, `release`, `ship`, `protect`,
  and `doctor`.
- `.keel.json` project configuration, with `trunk` and `gitflow`
  topologies, configurable branch prefixes, contribution model, review
  policy, merge strategy, and changelog requirement.
- A test suite covering the rule engine, both I/O modules, and the guard.
