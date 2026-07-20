# Shipyard

Shipyard is a suite of Claude Code plugins for project tooling. **`keel`** is
its first member: it owns a project's git lifecycle — how work starts, how it
lands, and how it ships.

## Why this exists

Most teams write their git conventions into a `CONTRIBUTING.md` that nobody
re-reads, and then discover violations in code review — or after a bad push.
The obvious fix is a GitHub template repo carrying the conventions and some
hooks. keel started as exactly that, and was rewritten as a plugin for two
reasons:

- **Template repos never update.** A repo created from a template in January
  cannot receive a February bugfix. Every derived repo forks the logic
  permanently.
- **A guard that ships inside the repo it guards can disable itself.** The
  predecessor's hook matched only `Bash`, so an `Edit` to its own source
  turned enforcement off.

A plugin fixes both: the logic lives outside your repo and updates centrally.
What stays in your repo is a small, committed `.keel.json` describing the
topology you want.

## What it looks like

Committing on a protected branch:

```
$ git commit -m "quick fix"

[keel/protected-write] 'main' is protected. Start a branch with
keel:start-work; changes reach it via PR. Run keel:doctor to see the full
picture.
```

Multiple problems in one command surface together, rather than one at a time:

```
$ git commit -m x && git push origin main

[keel/protected-write] 'main' is protected. Start a branch with
keel:start-work; changes reach it via PR. Also: [protected-write] This pushes
directly to protected branch 'main'. Open a PR instead (keel:finish-work). Run
keel:doctor to see the full picture.
```

And when keel can't determine something, it says so instead of guessing:

```
[keel/changelog] Could not compare against the base branch, so the CHANGELOG
check was skipped. Run 'git fetch' and retry if you want it enforced.
```

At session start it tells Claude what this repo's lifecycle actually is:

```
This repository uses keel for its git lifecycle.

- Topology: gitflow (feature/* -> PR -> develop -> release/* -> PR -> main)
- Protected: develop, main (changes reach them via PR)
- Review policy: review
- Current branch: feature/parser-fix
```

## Advisory, not enforced

Read this before anything else, because it is keel's central honesty
commitment.

keel's `PreToolUse` hook is **advisory**. It watches `git`/`gh` commands as
Claude Code runs them and warns or blocks before they execute — catching an
honest mistake (committing on `main`, opening a PR against the wrong branch,
merging with the wrong strategy) about **30 seconds earlier than CI would**.
That is genuinely useful, and it is *all* it is.

The real boundary is **GitHub branch protection and required checks**,
configured through the `keel:protect` skill. Branch protection is
unbypassable and applies equally to humans, CI, and Claude Code. The hook is
not a substitute for it — see
["What keel does not do"](#what-keel-does-not-do) below for exactly where the
line sits.

## Install

```
/plugin marketplace add submtd/shipyard
/plugin install keel@shipyard
```

## Configuration: `.keel.json`

Committed at the repo root. Nothing security-relevant lives here — capability
comes from GitHub, not this file — so a fork inheriting it is harmless. A
missing file disables keel entirely (no orientation, no guard); a malformed
one raises loudly rather than silently allowing everything.

| Field | Default | Allowed values |
|---|---|---|
| `topology` | `"gitflow"` | `"gitflow"`, `"trunk"` |
| `branches.production` | `"main"` | any branch name |
| `branches.integration` | `"develop"` | any branch name (ignored under `trunk`: it is forced to equal `branches.production`) |
| `prefixes.feature` | `"feature/"` | any string prefix |
| `prefixes.release` | `"release/"` | any string prefix |
| `prefixes.hotfix` | `"hotfix/"` | any string prefix |
| `contributions` | `"both"` | `"fork"`, `"branch"`, `"both"` (loaded, validated, and read by the `start-work` skill only -- no rule in the guard hook enforces it) |
| `reviewPolicy` | `"review"` | `"approval"` (requires `APPROVED`), `"review"` (`APPROVED` or `COMMENTED`), `"none"` |
| `mergeStrategy.toIntegration` | `"squash"` | `"squash"`, `"merge"`, `"rebase"` |
| `mergeStrategy.toProduction` | `"merge"` | `"squash"`, `"merge"`, `"rebase"` |
| `requireChangelog` | `true` | `true`, `false` |

Under `trunk` topology there is no integration branch and no release
branches: `feature/*` and `hotfix/*` both merge straight to production, and
`mergeStrategy.toIntegration` / `mergeStrategy.toProduction` still apply as
configured but the integration edge never fires.

This repository's own [`.keel.json`](.keel.json) uses `trunk`, since it has
no `develop` branch.

## The ten skills

In lifecycle order:

1. **`keel:start-work`** — begin a change: creates a correctly-named branch
   from an up-to-date base, choosing fork or branch based on config and your
   GitHub capability.
2. **`keel:sync`** — bring a stale branch or fork back up to date and resolve
   conflicts before continuing or opening a PR.
3. **`keel:finish-work`** — verify a change is ready: run checks, update the
   changelog, prompt for CLAUDE.md impact, and open the PR against the
   correct base.
4. **`keel:review`** — read a PR's full diff, evaluate it against project
   standards, and post a review.
5. **`keel:respond-to-review`** — read review feedback, evaluate it, make the
   changes, and reply.
6. **`keel:land`** — merge an approved PR with the strategy the repo's config
   requires, once the gates are satisfied.
7. **`keel:release`** — prepare a release: pick the version, roll the
   changelog, open the release PR.
8. **`keel:ship`** — after a release PR merges (or, under trunk, when it's
   time to cut a release from production): tag it, publish notes, back-merge
   into integration.
9. **`keel:protect`** — configure real, server-side enforcement: GitHub
   branch protection, required reviews, and force-push locks.
10. **`keel:doctor`** — explain what keel currently sees, what a rule name
    means, and why it decided what it did, when you were blocked or warned
    unexpectedly.

## The six rules

The guard evaluates every `git`/`gh` action against these. Rule names appear
in `[keel/<rule-name>]` messages.

- **`protected-write`** — triggers on a `commit` on, or a `push` whose
  destination refspec resolves to, a protected branch (production or
  integration). Tag-only pushes are exempt.
- **`pr-edge`** — triggers when a PR's head/base pair isn't a valid edge for
  the configured topology (e.g. `feature/* → integration`, `release/* →
  production`, `hotfix/* → production`, or the `production → integration`
  back-merge; under trunk, `feature/*` and `hotfix/* → production` only).
- **`changelog`** — triggers on a `feature`/`hotfix` PR whose CHANGELOG.md
  Unreleased section has gained no content (or doesn't exist), when
  `requireChangelog` is true. Release and back-merge PRs are exempt.
- **`merge-strategy`** — triggers when a PR merge's strategy doesn't match
  the one configured for its base (`mergeStrategy.toIntegration` /
  `mergeStrategy.toProduction`).
- **`review`** — triggers on a PR merge that has requested changes
  outstanding, or that lacks the review state `reviewPolicy` requires.
  Applied identically to fork and same-repo PRs.
- **`capability`** — triggers (as a warning only) when you appear to lack
  merge permission on the repository for a PR merge.

Every fact the rules read is tri-state (true/false/unknown), and unknown
**never** produces a block — only a warning. The hook would rather stay quiet
than block on ignorance.

## What keel does not do

- **It runs only inside Claude Code.** Plain `git`/`gh` typed into a terminal,
  or run by CI, bypasses it completely. keel has no presence outside a
  Claude Code session.
- **It does not parse shell constructs adversarially.** `bash -c`, `eval`,
  subshells, backticks/`$()`, and other command substitution are not
  inspected — deliberately. keel's predecessor tried, and a review of that
  code found roughly 20 verified ways to evade its checks while also
  producing false positives (e.g. splitting a quoted commit message and
  classifying a phantom push). Escalating that arms race isn't worth it: it
  buys false confidence without buying real coverage.
- **It is not a security control.** It cannot stop someone determined to
  evade it, and it is not meant to. Its job is to catch honest mistakes
  early, not to gate access.
- **Known limitation: the protected-branch rule keys on branch name, not
  repository identity.** `protected-write` blocks a push whose destination
  branch is named `main` (or whatever `branches.production` /
  `branches.integration` are), regardless of which repository that `main`
  belongs to. It cannot distinguish your fork's `main` from the canonical
  repo's `main` — so pushing to a protected-named branch is denied even on a
  fork you fully control. The `keel:sync` skill works around this by
  rebasing against `upstream/<base>` rather than pushing to a
  protected-named branch directly.

The real boundary is GitHub branch protection, configured via
`keel:protect`. keel's hook is the earlier, friendlier warning — not the
gate.

## How it's built

The decision layer is a pure function with no I/O, which is what makes the
rule table exhaustively testable:

```
plugins/keel/
├── keel/
│   ├── config.py    .keel.json -> Config          ┐
│   ├── actions.py   command string -> [Action]    │ pure: no subprocess,
│   ├── facts.py     tri-state facts               │ no I/O, no globals
│   ├── rules.py     (action, facts, config) -> Verdict
│   └── render.py    Verdict -> hook JSON          ┘
│   ├── gitio.py     all git subprocess calls      ┐ all I/O, every call
│   └── ghio.py      all gh subprocess calls       ┘ timed out
├── hooks/
│   ├── guard.py     PreToolUse entrypoint
│   ├── orient.py    SessionStart entrypoint
│   └── hooks.json   hook registration
├── skills/          the ten skills
└── tests/           163 tests
```

Rules key on `(action, base, head, headIsFork, capability)`. There is
deliberately **no role concept** — no contributor/maintainer/solo inference
from remote URLs. Fork and same-repo PRs are judged identically, which is
what keeps a maintainer's own same-repo PR from skipping the review gate.

Capability comes from GitHub (`gh repo view --json viewerPermission`), not
from guessing at remote URLs.

## Development

Stdlib only at runtime — no third-party dependencies. Tests need `pytest`.

```
pip install pytest
python3 -m pytest -q
```

CI runs the suite on Python 3.9 and 3.12.

## Status

`keel` is v0.1.0 and covers the git lifecycle. Planned next:

- **`keel:init`** — scaffold `.keel.json`, `.github/` templates, CODEOWNERS,
  and a changelog CI check into an existing repo.
- Sibling Shipyard plugins for the domains keel deliberately leaves alone:
  CI/CD pipeline authoring, dependency management, testing, and security
  scanning.

## License

MIT — see [LICENSE](LICENSE).
