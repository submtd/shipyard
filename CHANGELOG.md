# Changelog

All notable changes to Shipyard plugins are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Fixed

- `stow` no longer risks emptying a repo's `.gitignore`. The write went
  through a bare `Path.write_text`, which truncates the file *before* it
  encodes -- so on a machine whose preferred codec isn't UTF-8, the
  advisory line's em dash raised `UnicodeEncodeError` against an
  already-empty file and the user's hand-written ignore rules were gone.
  Writes now go through a new `stow.fileio`: explicit UTF-8, staged into a
  sibling temp file and swapped with `os.replace`, so a failed or
  interrupted write leaves the original intact. Symlinked `.gitignore`
  files are written through rather than replaced.
- `stow.blocks.find_blocks` now normalizes line endings itself instead of
  requiring callers to. The marker regexes are `\Z`-anchored, so on a CRLF
  file every marker line ended in `\r`, matched nothing, and a genuinely
  corrupt `.gitignore` was reported as having no malformed markers -- the
  skill's verification step was the caller that got that vacuous pass.
- `keel`'s guard was inert for every multi-line Bash command. `_segments`
  listed `"\n"` as a command separator, but shlex in whitespace-split mode
  never emits a newline token, so a whole multi-line script collapsed into
  one segment and every command after the first was silently discarded --
  `git status\ngit push origin main` classified as nothing at all and the
  push to a protected branch went unremarked. Since multi-line scripts are
  the Bash tool's normal shape, this was the common case rather than an
  edge case. Newline is now a lexer punctuation character, which keeps
  multi-line quoted arguments (a wrapped commit message) intact where a
  plain `split("\n")` would cut them in half.
- `keel` no longer parses trailing shell comments as arguments.
  `git push origin feature/x # deploy to main` read `main` as a refspec and
  produced a hard DENY citing a protected branch the command never touched.
- `keel` now blocks `git push --all` and `git push --mirror`. Both carry no
  refspec, so the protected-write rule fell back to checking only the
  current branch -- from a feature branch that check passed while the
  command pushed production and integration straight to the remote.
- `keel` now resolves `git push origin HEAD` (and `@`) to the current
  branch before the protected-branch check. `HEAD` was compared literally
  against the protected set, never matched, and a direct push to production
  from production was allowed. An unresolvable branch warns rather than
  allowing.
- The CI changelog gate could be switched off by the very PR it was
  gating. `load_cfg` read `.keel.json` from the working tree, which in CI
  is the PR's own head checkout, so a branch that included
  `requireChangelog: false` exempted itself. The config is now read from
  the base ref, which only already-merged (already-reviewed) code can
  change. A repo with no config at the base still falls back to the
  working tree -- that's the PR adopting keel, and there is no
  already-enabled gate to bypass.
- The changelog gate treated "gained content" as "differs from base", so a
  PR that only *deleted* an Unreleased entry passed -- and was told its
  changelog had gained content. It now requires at least one non-blank
  Unreleased line the base did not have. Rewording an entry still counts.
- The `changelog` workflow now declares `permissions: contents: read`,
  matching `ci.yml` and `security.yml`. Without it the job inherited the
  repository's default `GITHUB_TOKEN` scope, which is write-capable unless
  the repo says otherwise. Fixed in the `keel:init` template too, so the
  gap stops propagating into every repo keel scaffolds.
- `ballast` could render a `pytest.ini` that stopped pytest from starting.
  pytest shlex-splits `addopts`, `testpaths` and `pythonpath`, but
  `PATH_RE`/`FLAG_RE` were plain `\S+` -- they excluded whitespace but not
  quotes, so a value like `-k'foo` rendered straight through and pytest
  died with `ValueError: No closing quotation` from inside its own config
  layer, before collection. Both charsets now exclude quotes, backslash,
  backtick and `$`. A new render test tokenizes every rendered value line
  the way pytest will, which the text-comparing golden and dogfood tests
  could not see.
- `ballast` now rejects unknown keys in `.ballast.json` instead of silently
  discarding them, naming the offender. The rendered file spells these
  lowercase (`testpaths`, `pythonpath`, `addopts`), so mirroring the
  rendered names instead of the camelCase config names was the natural
  mistake -- and the symptom (pytest scanning the whole tree) surfaces
  nowhere near the cause.
- `ballast.render` now raises on a multi-stack config instead of rendering
  the first stack and silently dropping the rest. Unreachable today, but
  `config.py` and `scaffold.py` are both generic over `STACK_IDS`, so
  registering a second stack would have turned this into silent data loss;
  the docstring claimed the opposite.
- `ballast:init`'s verification step no longer pins a hardcoded test count
  (`708 tests`, `four plugin test dirs`) that a following agent would
  compare against and report a false failure. It now checks the invariant:
  every configured `testPaths` entry exists and collection is non-empty.
### Changed

- All six plugins now reject unknown keys in their config files instead of
  silently ignoring them, naming the offending key and listing what is
  allowed. This applies to nested objects too (`keel`'s `branches`,
  `prefixes` and `mergeStrategy`; per-stack and per-ecosystem objects
  elsewhere). Previously a one-character typo was invisible: `versinos`
  reverted `rigging`'s whole CI matrix to the registry default, `intrval`
  silently gave `bosun` weekly when the user asked for daily, and a
  `permissions` key in `.hull.json` looked like it configured the
  workflow's token scope while doing nothing. `stow` stack values take no
  options at all, so any key inside one is now an error rather than a
  pretence.

  This is a behaviour change for any config that currently carries an
  unrecognised key -- such a file now fails to load rather than loading
  with that key dropped. The message names the key, and the fix is to
  remove or correct it. Note the CI changelog gate keeps its own
  deliberately tolerant reader: CI must not crash on config.

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
