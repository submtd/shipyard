# Changelog

All notable changes to Shipyard plugins are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added

- Repo-level `tests/` (wired in through `.ballast.json`, so `ballast`
  renders the runner config for it like any other suite) covering what no
  single plugin owns: every `marketplace.json` entry points at a real
  plugin directory, every plugin directory is registered, names agree with
  the `plugin.json` they point at, and each `plugin.json` version matches
  its package `__version__`. Previously each plugin only asserted that
  *it* was listed, so a marketplace entry with no directory shipped green.
- `keel`'s smoke test now covers what its five juniors already did --
  `plugin.json`, marketplace registration, frontmatter for all eleven
  skills, module importability -- plus the two things only `keel` has:
  `hooks.json` wiring, and a check that `orient.py`'s advertised skill
  list matches the skills actually on disk. It was three lines asserting
  only `__version__`, on the oldest and most-installed plugin in the
  suite.
- `test_purity.py` in all six plugins now asserts that its hand-maintained
  `PURE_MODULES` list covers every module in the package. A new module was
  previously guarded by nobody -- adding one that imports `subprocess`
  passed purity silently in all six.
- `bosun`'s `propose_config` key order is now pinned. `build_plan` and
  `render` were both order-defended, but the function that writes the
  *other* committed artifact (`.bosun.json`) was stable only by accident:
  every assertion compared dicts with `==`, which ignores key order.
- `hull:init` now tells the user to run a one-time `gitleaks detect` over
  existing history at adoption. The rendered workflow scans the event's
  commit range, so the run triggered by the commit that adds
  `security.yml` scans only that commit -- a repo with a secret committed
  last year gets a green check and has never been scanned.

### Changed

- `keel`: under `trunk` topology, `pr-edge` now accepts any branch into
  production, not only `feature/*` and `hotfix/*` -- trunk-based development
  is not prefix-strict the way gitflow is. The `changelog` gate still applies
  to all trunk work branches (previously it only applied to `feature/*`/
  `hotfix/*`, silently exempting anything else).

### Fixed

- `.gitattributes` now normalizes line endings repo-wide (`* text=auto
  eol=lf`). Five of the six plugin suites compare committed files
  byte-for-byte, but only `ballast`'s artifacts were covered, so a Windows
  checkout with `core.autocrlf=true` failed the rest.
- `ballast`'s "every plugin is in testpaths" guard now derives the plugin
  list from disk instead of hardcoding six names -- the hardcoded list was
  itself a way for a seventh plugin to escape the check.
- `CHANGELOG.md` had two `### Added` sections inside `## [Unreleased]`,
  which is malformed per Keep a Changelog and which neither the gate nor
  any test noticed. Merged.

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
- `keel`, the first Shipyard plugin: a rule engine that models a project's
  git lifecycle as `(action, base, head, headIsFork, capability)`, with
  no notion of "role."
- An advisory `PreToolUse` hook that evaluates `git`/`gh` commands against
  the rule engine and warns or blocks before the command runs.
- A `SessionStart` orientation that reports topology, protected branches,
  review policy, and current branch, once per session.
- Ten lifecycle skills: `start-work`, `sync`, `finish-work`,
  `respond-to-review`, `review`, `land`, `release`, `ship`, `protect`,
  and `doctor`. (`keel:init` landed later, listed above.)
- `.keel.json` project configuration, with `trunk` and `gitflow`
  topologies, configurable branch prefixes, contribution model, review
  policy, merge strategy, and changelog requirement.
- A test suite covering the rule engine, both I/O modules, and the guard.
- `plugin.json` no longer double-registers `hooks/hooks.json`, which Claude
  Code auto-loads by convention; the redundant reference failed on install
  with a duplicate-hooks error.
