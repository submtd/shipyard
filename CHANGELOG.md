# Changelog

All notable changes to Shipyard plugins are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

All six plugins are versioned in lockstep: they ship from one marketplace,
are developed together, and the whole suite is what gets installed. A single
version number is what keeps the six near-identical architectures honest
about being one thing.

Everything before 0.3.0 was pre-release. The `plugin.json` version numbers
that existed then (`keel` 0.2.0, the rest 0.1.0) never corresponded to a
release section here, so they are not reconstructed below; 0.3.0 is the
first release this changelog describes. The number is 0.3.0 rather than
0.1.0 so that it is an increase for every plugin including `keel`, which
was already installed at 0.2.0 -- a lower number would read as a downgrade
and could stop an installed copy from updating.

## [Unreleased]

## [0.8.0] - 2026-07-22

### Added

- **`rigging` jobs can run a database alongside their tests.** `.rigging.json`'s
  per-stack config gained `services` — `postgres`, `mysql`, or `redis` — as
  `{"postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}`. rigging owns
  the image tag, port, credentials, and the **health check** (so the job waits
  for readiness instead of racing the container and flaking), and composes the
  connection URL from its own credentials into the job-level env var the repo
  names. Images are pinned by major tag, not digest — an ephemeral test fixture
  on a private network has a different threat model from an Action that runs
  with the workflow token. This is the third and final increment of #26: a repo
  needing a live Postgres can now use rigging end to end.

### Changed

- Bumping the suite version no longer breaks the test suite. The per-plugin
  smoke and stacks tests no longer hardcode the version string — they assert it
  is well-formed semver — and a new `test_marketplace.py` check enforces
  lockstep (all six plugins report the same version) without naming a value.
  A release now edits only the twelve files that genuinely carry the version;
  the fifteen meaningless release-time failures are gone, and lockstep — a
  stated property of the suite — is enforced for the first time (#29).

## [0.7.0] - 2026-07-22

### Added

- **A secret scanner that needs no license.** `.hull.json`'s `scanner` now
  accepts `"trufflehog"` alongside `"gitleaks"`, pinned to
  `trufflesecurity/trufflehog@27b0417c` (v3.95.9). It needs no license key,
  no secret of any kind, and only `contents: read` -- narrower than gitleaks,
  which additionally needs `pull-requests: read` to enumerate a pull
  request's commits through the API.

  This closes a gap 0.6.0 opened. That release taught `hull:init` to refuse
  rather than scaffold a workflow that could not pass, which was right, but
  it left an organization-owned repo with **no secret scanning at all** --
  and the blocker's own suggested remedy, "choose a scanner with no license
  gate", named nothing, because the registry had one entry. It names
  `trufflehog` now. The default is unchanged: `gitleaks` for everyone who
  is not blocked.

  Reports `verified` and `unknown` findings, not `unverified`. A secret the
  tool cannot verify is exactly the kind it should not stay quiet about;
  reporting *everything* trains a team to ignore the check, which is the
  failure mode the organization blocker exists to prevent.

- **`rigging` drives pnpm, yarn, and bun, not just npm.** `.rigging.json`
  gained `stacks.node.packageManager`, and `rigging:init` detects the right
  value rather than asking. The node job's install and test steps now come
  from a package-manager registry instead of being hardcoded to `npm ci` /
  `npm test`, so an npm repo's rendered workflow is byte-identical while a
  pnpm repo finally gets one that works.

  Yarn 1 and Yarn 2+ are separate entries (`yarn1`, `yarn-berry`) because
  their install flags are mutually incompatible — `--frozen-lockfile` is an
  error on berry and `--immutable` is an error on classic — and `yarn.lock`
  does not say which. When nothing declares the major, `rigging:init` refuses
  and says so, rather than guessing and rendering an install step that cannot
  work.

  Two lockfiles at the repo root is likewise a refusal, not a precedence
  rule: it means the project is mid-migration or carrying a stale file, and
  rigging will not pick for you.

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

### Fixed

- **`rigging:init` no longer refuses every pnpm, yarn, and bun repo.** 0.6.0
  taught it to refuse rather than hand those repos an `npm ci` workflow that
  could never pass. That was right, and it left them with no CI at all. The
  refusal table has been inverted: the same lockfiles that meant "cannot
  drive this" now say which manager to drive.

- **`rigging`'s config scaffolding rejects a malformed package-manager value
  cleanly.** An unhashable `packageManager` signal (a list where a string was
  expected) raised a bare `TypeError` from an internal membership test instead
  of the `ValueError` that names the offending field. It now names the field,
  like every other bad signal -- a latent gap surfaced by a new suite-wide
  test that every plugin's `init` can only ever propose a config the same
  plugin will accept.

## [0.6.0] - 2026-07-22

Minor rather than patch: two of these fixes change what `init` does in repos
where it previously produced files, and an existing user can hit either on a
re-run. Both refusals are described below.

Three adoption blockers reported from a real migration onto the suite
(issue #24): an org-owned pnpm + turbo TypeScript monorepo on gitflow, taking
fork contributions -- four configurations shipyard's own dogfooding cannot
exercise, because shipyard is a personal-account, npm-free, trunk repo.

All three were the same shape, and it is worth naming: a renderer with no
slot for something the rendered artifact genuinely required, and no escape
hatch, so the failure could not be fixed from the consuming repo. Generated
output being authoritative and byte-identity-tested is this suite's strongest
property; the flip side is that when a renderer cannot express what a repo
needs, the only honest move is to say so at scaffold time. **An `init` that
refuses to scaffold is worth more than one that scaffolds something broken.**

Two caveats worth stating rather than burying:

- `hull:init` now **refuses to scaffold** in an organization-owned repo with
  no license secret configured. That is a setup which used to "work" -- it
  produced files -- and now stops with a diagnosis. It produced a workflow
  that could never go green, so the refusal is the point, but it is a
  behaviour change an existing user can hit on a re-run.
- `rigging:init` likewise refuses when it finds a JavaScript toolchain it
  cannot drive. A pnpm/yarn/bun repo that previously got a workflow now gets
  none -- correctly, since the one it got died on `npm ci` every run.

### Added

- **`bosun` can target a branch other than the repository default.**
  `.bosun.json` gained an optional top-level `targetBranch`, rendered as
  `target-branch` on every update entry. Absent still means "use the
  repository default branch", so output for every existing config is
  byte-identical. `bosun:init` reads the answer out of `.keel.json` rather
  than asking cold, via the new `scaffold.keel_integration_branch` -- which
  returns None under trunk, because there the integration branch *is* the
  default branch and omitting the key is already right.
- **`hull` can pass a scanner license through to the action.** `.hull.json`
  gained an optional `licenseSecret` -- the NAME of an Actions secret, never
  key material -- rendered as `GITLEAKS_LICENSE: "${{ secrets.<NAME> }}"` on
  the scan step. Validated against a deliberately strict
  `^[A-Za-z_][A-Za-z0-9_]*$`: it is the one config string that lands inside
  an Actions expression rather than merely inside a quoted scalar, so a value
  that passes cannot close that expression, open another, or break out of the
  scalar. Which env var a license goes in is a property of the scanner, so it
  lives in the registry (`ScannerSpec.license_env`); setting `licenseSecret`
  for a scanner that has no license gate is a `ConfigError`, not a silently
  discarded setting.

### Fixed

- **`bosun` opened dependency PRs against production in every gitflow repo.**
  With no `target-branch` rendered, Dependabot falls back to the repository
  default branch -- which under gitflow is `main`. So bosun's output bypassed
  `develop`, bypassed the changelog gate `keel` enforces, and left integration
  behind until someone back-merged. Two plugins in one suite contradicting
  each other, on the topology `keel` defaults to.
- **`hull` scaffolded a workflow that could not pass in an org-owned repo.**
  The pinned `gitleaks-action` v3 exits 1 before scanning anything when the
  owner is a GitHub Organization and `GITLEAKS_LICENSE` is unset -- public or
  private alike -- and `.hull.json` had nowhere to put one. `hull:init` now
  looks up the owner type and refuses, showing the cause and both remedies,
  before anything is written. A failed lookup (no remote, offline,
  unauthenticated `gh`) is explicitly *not* a blocker: refusing because a
  network call failed would break hull on brand-new repos, which is where it
  matters most.
- **`rigging` handed every pnpm, yarn, and bun repo an `npm ci` workflow.**
  `detect_files=("package.json",)` matches *every* JavaScript repo, and the
  node stack's steps are `npm ci`/`npm test`, which fail outright without a
  `package-lock.json`. `rigging:init` now refuses to scaffold a stack it
  cannot drive, naming the marker it found and the package manager it
  implies. Detection is deliberately unchanged -- node is still reported, and
  the reason travels beside it, because silently dropping the stack is the
  same class of bug wearing a quieter coat. A repo where python is also
  detected still gets its python workflow, with the omission explained.

### Documentation

- `hull:init` now states the fork-PR limitation it always had: GitHub
  withholds repository and organization secrets from `pull_request` runs
  whose head is a fork, by design, so `GITLEAKS_LICENSE` arrives empty and
  the scan fails on fork PRs even once a license is configured. Reported as a
  non-blocking advisory, on a separate return channel from the blockers, so
  it is never confused for a reason to stop. It matters because `keel`
  supports `contributions` of `"fork"` and `"both"`.
- `rigging:init` and `bosun:init` both had "not here yet" lists that were
  quietly out of date about what they could express. Both now name the real
  gaps: for rigging, pnpm/yarn/bun steps, custom test commands, and service
  containers -- the last of which is why a repo needing a live Postgres still
  cannot use rigging today.

## [0.5.1] - 2026-07-21

Patch: every change is a fix to behaviour that was already meant to work.
Two caveats worth stating rather than burying:

- `hull`'s rendered `security.yml` changes (it now requests
  `pull-requests: read`), so an existing install needs regenerating -- via
  `hull:init` or by re-rendering -- to stop failing its pull-request scans.
- `propose_config` now rejects unknown signal keys. Any caller passing an
  extra key was silently having it dropped; it will now raise instead. That
  is the point of the change, but it is a call that used to "work".

Five findings from an end-to-end run of the whole lifecycle in a fresh
**private** repo under **gitflow** -- two configurations shipyard's own
dogfooding cannot exercise, because shipyard is public and trunk.

### Fixed

- **keel was a silent no-op on gitflow's default adoption path.** `keel:init`
  scaffolds `.keel.json` on the current branch (normally `production`);
  `keel:start-work` then branches from `integration`, which does not have it.
  `load_config` returned None and the guard returned without evaluating
  anything -- so every rule was skipped, silently, on exactly the branches
  keel exists to watch. The guard now distinguishes "this repo never adopted
  keel" (say nothing) from "this repo uses keel and this branch lacks the
  config" (say so loudly), the way a malformed config already did. It warns
  rather than blocks: without the config there is no policy to enforce, and
  inventing one would be worse. `keel:init` and `keel:start-work` both gained
  explicit steps so the backstop is not the plan.
- **`hull`'s rendered workflow failed every pull-request scan on private
  repos.** `permissions: contents: read` does not grant
  `GET /repos/{o}/{r}/pulls/{n}/commits`, which gitleaks-action v3 calls to
  enumerate a PR's commits, so every `pull_request` run died with 403
  "Resource not accessible by integration" while every `push` run passed.
  Permissions are now declared per scanner, and gitleaks asks for
  `pull-requests: read`. Read scopes only, enforced by test.
- **All six `propose_config` functions silently ignored unknown signals.** A
  typo'd `producton` meant the scaffold quietly took the `main` default
  instead of the repo's real production branch. The config *loaders* were
  hardened against exactly this in 0.3.0; the layer above them had the
  opposite behaviour, and it is worse there because a dropped signal leaves
  nothing on disk to inspect afterwards.
- `stow.desired_sections(None)` raised a bare `AttributeError` from two
  frames deep when `.stow.json` was absent -- reachable straight from the
  skill's own one-liner. It now names the file and the fix.

### Documentation

- `rigging` and `hull` both told you to set `pushBranches` from the *default*
  branch. Under gitflow most merges land on `integration`, so that left the
  team's main integration branch with no push CI and no scan.

## [0.5.0] - 2026-07-21

Minor: additions only. One caveat worth stating plainly -- ballast's new
`addOpts` denylist will make an existing `.ballast.json` that sets `--pdb`,
`--lf` or a sibling start failing to load. That is the point of the change,
but it is a config that used to work and now does not, so it is called out
here rather than left to be discovered.

### Added

- A repo-wide skill-integrity guard (`plugins/keel/tests/test_skill_integrity.py`)
  covering every skill in all six plugins: frontmatter parses and carries a
  `name` and `description`, the `name` matches its directory, cross-skill
  references resolve, and every plugin is listed in the marketplace. Skills
  are prompt files with no compiler behind them, so a typo'd `name` or a
  reference to a renamed skill previously failed only at use.
- `ballast` rejects CI-hostile `addOpts`. A committed `pytest.ini` is
  inherited by every run in every environment, and two families of flag do
  real damage there: interactive debuggers (`--pdb`, `--trace`, `--pdbcls`)
  block on stdin and hang CI until it times out, and cache-dependent
  selection (`--lf`, `--ff`, `--sw` and their long forms) makes *which tests
  run* depend on a previous local run's `.pytest_cache`, silently narrowing
  the suite. `-s`/`--capture=no` and `-x`/`--exitfirst` stay allowed --
  defensible standing preferences, not hostile.

### Documentation

- A decision record for `fathom`, the seventh plugin from the original
  blueprint: not built, and the roster closes at six.
- README rewritten around the closed six-plugin roster: the opening
  paragraph is a table rather than a six-clause sentence, the Status section
  no longer repeats it six times, and the claim that `fathom` was "the only
  remaining sibling on the roadmap" is gone -- it contradicted the decision
  record. Documents `pushBranches` and the pytest bound.

## [0.4.0] - 2026-07-21

Closes the findings left open by 0.3.0's code review. Minor rather than
major despite the breaking change to rendered output: pre-1.0, and the
break is confined to regenerating two workflow files.

### Added

- `rigging` and `hull` both accept an optional `pushBranches` key in
  `.rigging.json` / `.hull.json`, defaulting to `["main"]`. Both `init`
  skills now check the repo's real default branch before proposing a config,
  because a repo on `master` that took the default would get no push CI at
  all with nothing to say so.

### Changed

- **Breaking (rendered output).** `rigging` and `hull` render `on: push`
  restricted to `pushBranches` instead of `on: [push, pull_request]`. A pull
  request raised from a branch in the same repo previously ran the whole
  matrix twice -- once for the push, once for the PR. Re-run the `init`
  skills, or regenerate, to pick this up.
- `rigging`'s python stack installs `'pytest>=8,<9'` rather than bare
  `pytest`, so a pytest major release cannot turn CI red in a repo whose own
  code never changed.
- `bosun` accepts the `quarterly`, `semiannually` and `yearly` schedule
  intervals. The enum stopped at `monthly`, so bosun rejected `.bosun.json`
  files GitHub would have accepted. `cron` remains unsupported: it needs a
  companion `schedule.cronjob` key that the config schema and renderer do
  not yet model, and admitting it alone would render a file GitHub rejects.
- `keel`'s scaffolded `CODEOWNERS` template ships with no active rule. It
  previously shipped a live `*  @REPLACE-WITH-OWNER` line; GitHub resolves
  every owner and rejects the whole file as invalid when one does not exist,
  so once `keel:protect` required code-owner review, every PR in the
  scaffolded repo became unmergeable.

### Fixed

- `keel`'s `target_cwd` silently failed the guard open in three ways: a
  relative `cd` (`cd packages/api && git commit`, the normal monorepo shape)
  was returned unanchored and resolved against the hook's own working
  directory; a `~` was never expanded; and `--git-dir=<path>`, git's own
  equals form, was not recognised at all. Each produced a directory that
  does not exist, so `repo_root()` returned `None` and the hook returned
  without evaluating a single rule -- no block, no message, no signal that
  anything had been skipped. `--git-dir` now also resolves to the work tree
  rather than to the `.git` directory, which is not a directory git can run
  `rev-parse --show-toplevel` in.
- `keel` read `gh pr merge`'s strategy with a membership test over every
  token, so a flag *value* that looked like a strategy flag became the
  strategy: `gh pr merge 1 --body '-s' --merge` parsed as `squash`. Since
  the merge-strategy rule blocks outright on a mismatch, a correct command
  earned a hard DENY naming a strategy it never requested.
- Stack detection in `rigging`, `ballast`, `stow` and `bosun` used
  `.exists()` rather than `.is_file()`, so a *directory* named
  `package.json` or `pyproject.toml` -- a vendored tree, an unpacked
  artifact -- detected the whole stack and scaffolded it off a path holding
  no configuration.

## [0.3.0] - 2026-07-21

First released version. The suite existed before this and was in use, but
was not versioned against a changelog; this release is the point where that
starts. Its content is the outcome of a full code review of the whole
repository, so it is weighted toward correctness and safety fixes rather
than new capability.

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

- `scripts/sync_action_pins.py`, which makes Dependabot PRs landable.
  `ci.yml` and `security.yml` are rendered from the `rigging`/`hull`
  registries, but Dependabot edits the rendered file and leaves the
  registry alone — so its PRs fail the byte-identity dogfood tests and can
  never go green unaided. The script carries a bump from the artifacts back
  into the registries and regenerates everything. Documented in the README,
  and covered by `tests/test_sync_action_pins.py`, including the two ways
  it got this wrong while being written (swallowing the closing quote of a
  pinned `uses=` string, which left the registry unparseable; and letting
  one action's version tag overwrite another's in a shared file).

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
- `keel` now passes an explicit `--repo`/`-R` through to `gh`.
  `Action.repo` was parsed, stored, asserted in a test, and then read by
  nothing, so `gh pr merge 5 --repo other/org-repo` was judged against the
  *local* checkout's PR #5 -- a different pull request, with a different
  base and review state. The review and merge-strategy gates therefore
  returned a confidently wrong verdict rather than an honest unknown. The
  repository is now part of the fact cache key too, so one repo's answer
  can't be served for another.
- `keel`'s skills now load the config through `keel.config.load_config`
  instead of reading `.keel.json` directly. `keel:init` writes only the
  keys it detects, so `prefixes` and `mergeStrategy` are normally absent
  from the file -- `start-work`, `land`, `sync` and `release` were telling
  Claude to read fields that aren't there, leaving it to guess, and a guess
  that disagrees with the loader's defaults produces a `merge-strategy` or
  `pr-edge` block nobody can explain.
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
- `keel`: under `trunk` topology, `pr-edge` now accepts any branch into
  production, not only `feature/*` and `hotfix/*` -- trunk-based development
  is not prefix-strict the way gitflow is. The `changelog` gate still applies
  to all trunk work branches (previously it only applied to `feature/*`/
  `hotfix/*`, silently exempting anything else).

- Every GitHub Actions ref upgraded to its current major and re-pinned:
  `actions/checkout` v4 -> v7, `actions/setup-python` v5 -> v7,
  `actions/setup-node` v5 -> v7, `gitleaks/gitleaks-action` v2 -> v3. The
  0.3.0 pins were faithful to what the repo had, which meant they were
  immutable *and* several majors stale. Release notes were read for each:
  all four are Node 20 -> Node 24 runtime moves plus ESM migrations, and
  none of the behavioural changes (checkout v7 blocking fork checkout under
  `pull_request_target`, setup-python v7 dropping `pip-install`,
  setup-node v6 limiting auto-caching to npm) touch anything these
  workflows use. The gitleaks bump is time-sensitive rather than optional:
  GitHub removes Node 20 from hosted runners on 16 September 2026, after
  which `gitleaks-action@v2` stops running at all.

### Fixed

- `plugin.json` no longer double-registers `hooks/hooks.json`, which Claude
  Code auto-loads by convention; the redundant reference failed on install
  with a duplicate-hooks error.
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
- `rigging` and `hull` renderers now emit `Step.name`, which both declared
  and neither rendered -- a registry entry written as `Step(name=...)`
  silently lost it, with no error and no test. Duplicated latent bug,
  present in both because the renderer was copy-pasted before either used
  the field.
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
- `keel:land`'s branch-deletion rule was written for gitflow and was wrong
  under trunk. It said "do not delete the branch on a merge into
  `production`", whose stated reason -- release branches are sometimes
  needed again -- is about the *head*, not the base. Under trunk
  `production` is the base for every PR, so read literally the rule made no
  branch ever deletable and finished work branches would accumulate
  forever. It now keys off the head branch: keep `release/*` and back-merge
  heads, delete finished work branches. Found by following the skill on
  this repo's own PR #14.
- Tests no longer restate action SHAs as literals. Seven did, so a
  legitimate upgrade meant editing seven files in lockstep — which is how
  pins go stale. They now derive from the registries, leaving exactly one
  place per action where a SHA is written. `hull`'s checkout pin was
  inlined in `plan.py` where `rigging`'s was already a named constant; it
  is now `CHECKOUT_USES`/`CHECKOUT_VERSION`, closing another copy-paste
  divergence between the two.
