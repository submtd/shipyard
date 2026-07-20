# keel — design

**Date:** 2026-07-20
**Status:** Approved
**Suite:** Shipyard
**Supersedes:** `dbd-net/project-template` (GitHub template repo)

## Summary

`keel` is a Claude Code plugin that owns a project's git lifecycle: how work starts, how it
lands, and how it ships. It replaces the `dbd-net/project-template` GitHub template repo.

It is the first member of **Shipyard**, a suite of Claude Code plugins for project tooling.

## Why replace the template repo

The existing template is a GitHub "Use this template" repo carrying `.claude/` hooks and
skills. Two structural problems:

1. **Templates never update.** A repo created from the template in January cannot receive a
   February bugfix. Every derived repo forks the enforcement logic permanently.
2. **The enforcement mechanism ships inside the repo it enforces**, so it can be edited to
   disable itself. The `PreToolUse` hook matches only `Bash`, leaving `Edit`/`Write` free to
   modify `guard.py` or `settings.json`.

A plugin fixes both: logic lives outside the repo and updates centrally.

## Review findings that drive this design

A full review of the existing template produced these, verified by executing the code:

**Security / correctness**
- `git push origin main --tags` is allowed for **every role**. The tag exemption is evaluated
  before role dispatch, and `--tags` is detected anywhere in the arg list regardless of refspec.
- `soloMaintainer` is a committed flag, and `detect_role` checks it *before* `origin ==
  canonical`. Anyone forking a solo-mode repo inherits union permissions on their fork.
- A maintainer merging a same-repo `feature → develop` PR bypasses both squash and review.
  The solo design doc explicitly identifies this gap and fixes it for `solo` only; the
  maintainer path still uses `isCrossRepository`. A test enshrines the hole as intended.
- Malformed `workflow.json` silently disables the entire guard (swallowed exception → `{}` →
  role `uninitialized` → allow-all).
- Context is gathered from the hook's cwd, so `cd /other && git commit` and `git -C /other
  commit` are evaluated against the wrong repo.

**Classification**
- ~20 confirmed evasions: `bash -c`, `eval`, subshells, backticks/`$()`, `xargs`,
  `/usr/bin/git`, `timeout`/`sudo` wrappers, git aliases, `gh api -X PUT .../merge`, and every
  unclassified mutating verb (`reset --hard`, `branch -f`, `update-ref`, `cherry-pick`).
- False positives: `git commit -m "fix; git push origin main"` splits mid-quote and classifies
  a phantom push. Heredoc bodies classify as real commands.

**Design**
- `solo` was retrofitted as a third role that is the union of the other two.
- `versionScheme`, `commands.test`, `commands.lint` are read by zero code.
- Hard-blocks all git writes unless Superpowers is detected — an unversioned third-party
  dependency gating every commit — via a full recursive glob of the plugins tree on **every
  Bash call**.
- Five separate untimed `gh pr view` subprocess calls per merge evaluation.
- No coherent fail policy: approval fails closed, missing base ref fails open, bad JSON fails
  open silently.
- Ships four pytest files with no runner, no pytest config, and no CI. `commands.test` blank.
- No `.github/` at all. `.gitignore` is two lines.
- Missing skills for the most-repeated actions: responding to review feedback, syncing a stale
  branch, and any hotfix path (structurally impossible today — `main` is protected for every
  role and only `releasePrefix` is whitelisted).

## Architecture

### Enforcement: hybrid

The guard attempts to police a Turing-complete shell with regex. That is unwinnable, and the
existing `CLAUDE.md` already concedes plain-shell bypasses it. Rather than escalate that arms
race, enforcement splits into two layers with honest, distinct jobs:

| Layer | Job | Guarantee |
|---|---|---|
| GitHub branch protection + required checks | The real boundary | Unbypassable; applies to humans and CI too |
| `keel` PreToolUse hook | Advisory tripwire | Catches honest mistakes ~30s earlier than CI |

**The hook is explicitly not a security control.** It exists to catch a developer about to
commit on `main`, not to stop someone determined to evade it.

This reframing is load-bearing: because airtightness is not a goal, we drop bash AST parsing,
the deny-by-default subcommand allowlist, and the entire adversarial-classification problem.
What matters is that the hook's *messages* are correct, not that its coverage is total.

### Roles belong to actions, not people

The existing design derives a `role` string by comparing `origin`'s slug to `canonicalRepo`.
That single inference causes nearly every bug above: the case-sensitivity demotion, the
"clone canonical + fork as second remote" misclassification, and the fork-inherits-solo hole.
"Solo" then had to be invented as a third role — the union of the other two — because one
person occupies both positions.

**The role concept is deleted.** Committing on a feature branch is contributor-shaped work
whether or not you can also merge; merging a PR is maintainer-shaped work whether or not you
wrote it. Rules key on:

```
(action, base, head, headIsFork, capability)
```

Consequences:

- **Fork and branch models stop being modes.** A fork PR has `headIsFork: true`; a same-repo
  PR does not. One rule table, both first-class, no retrofit.
- **Capability comes from GitHub** (`gh api repos/:o/:r` → `permissions`), not remote-URL
  guessing. Slug case-sensitivity and remote-layout inference disappear rather than get patched.
- **`soloMaintainer` disappears.** No flag to inherit; the fork-inheritance hole is closed
  structurally.

GitHub forbids self-approval, so "requires an approving review" is unsatisfiable for a solo
maintainer. The existing code fudges this by accepting `COMMENTED` when the magic flag is set.
`keel` makes it explicit config (`reviewPolicy`), which also correctly serves a two-person team
— where approval *is* possible and *should* be required, and which today has no way to say so.

## Configuration

`.keel.json` at repo root, committed. Nothing security-relevant lives here — capability comes
from GitHub — so a fork inheriting this file is harmless.

```json
{
  "topology": "gitflow",
  "branches":  { "production": "main", "integration": "develop" },
  "prefixes":  { "feature": "feature/", "release": "release/", "hotfix": "hotfix/" },
  "contributions": "both",
  "reviewPolicy": "review",
  "mergeStrategy": { "toIntegration": "squash", "toProduction": "merge" },
  "requireChangelog": true
}
```

- `topology`: `gitflow` | `trunk`. Trunk collapses integration into production and drops
  release branches; the same rule table applies with fewer valid edges.
- `contributions`: `fork` | `branch` | `both`.
- `reviewPolicy`: `approval` (needs `APPROVED`) | `review` (`APPROVED` or `COMMENTED` —
  solo-compatible) | `none`.

Malformed config **warns loudly and disables the hook explicitly**, rather than silently
degrading to allow-all.

## The rule engine

### Facts

Every fact is tri-state: `true` / `false` / `unknown`.

- **capability** — one `gh api repos/:o/:r` call, cached in `.git/`, with a timeout.
- **PR base / head / isCrossRepository / reviews** — one `gh pr view --json ...` call
  (replacing five separate untimed calls), with a timeout, cached per PR number.
- **changelog-changed**, **destination refs**, **target repo root**.

### Fail policy

**`unknown` → warn, never block.** Stated once and applied uniformly. Because the hook is
advisory, this is principled rather than the incoherent mix the review found.

### Rules

1. **Protected-branch write.** Destination resolved from the **push refspec**, not the current
   branch — this is what closes `git push origin HEAD:main`. Tag pushes are exempt only when
   *every* pushed ref is a tag, and the exemption sits **inside** the rule rather than before
   role dispatch, closing `git push origin main --tags`.

2. **Valid PR edges.**
   - `feature/* → integration`
   - `release/* → production`
   - `hotfix/* → production` *(new — structurally impossible today)*
   - `production → integration` (back-merge)

   Under `trunk`, `feature/* → production` and release edges drop out.

3. **Changelog gate.** Required on feature and hotfix PRs; skipped on release and back-merge
   PRs. Implemented as "the Unreleased section gained content," not "the file was touched" — a
   whitespace edit no longer satisfies it.

4. **Merge strategy.** Squash into integration; merge commit into production.

5. **Review gate.** Driven entirely by `reviewPolicy` and applied **identically to fork and
   same-repo PRs**. This closes the maintainer same-repo hole.

6. **Capability.** Merging expects push/maintain. Advisory only.

### Dropped rule: CLAUDE.md must change on every PR

The gate is satisfiable by whitespace and breaks outside a flat repo layout, but the deeper
problem is that it is wrong: most PRs should not touch CLAUDE.md, so the rule trains people to
make empty edits to clear it. Replaced with a prompt inside `finish-work`: "does this change
affect anything documented in CLAUDE.md?"

### Server-side mirror

`keel:protect` configures rules 1, 4 and 5 as GitHub branch protection plus a required
changelog check. This is what makes them real; the hook only surfaces the same verdict earlier.

## Skills

**Contributor loop**
- `start-work` — detects feature vs hotfix and fork vs branch from config + capability, so
  hotfix needs no separate skill.
- `finish-work` — tests/lint, self-review, changelog, CLAUDE.md prompt, PR.
- `respond-to-review` *(new)* — the most repeated contributor action; currently 100% manual.
- `sync` *(new)* — stale branch/fork recovery, which the guard is silent about today.

**Landing**
- `review`, `land` — kept separate despite overlap, because a genuine asynchronous human gap
  sits between them.

**Release**
- `release` — branch, roll Unreleased, PR.
- `ship` — tag, notes, back-merge. Separate for the same reason: the PR must merge in between.

**Meta**
- `protect` — server-side configuration.
- `doctor` *(new)* — "why was I blocked / what is my current state." The hook is the primary UX
  surface and had no troubleshooting path.
- `init` — increment 2.

Skills declare `allowed-tools`. Superpowers is a **soft dependency**: `keel` works standalone,
and delegates to `superpowers:*` for review/TDD/planning when present. It never blocks on it.

## Runtime

- Single `gh` call per concern, with `timeout=`, cached.
- Superpowers detection removed entirely (was a full recursive glob per Bash call).
- Top-level `try/except` in both hooks; a crash warns rather than vanishing.
- Context resolved against the command's actual target repo (`cd`, `git -C`), not the hook cwd.
- `SessionStart` gains a `startup` matcher so orientation stops re-firing on resume and compact.
- Orientation reports topology, current branch, capability, and what is currently allowed.

## Testing and CI

- Table-driven tests over the rule table: both topologies, both contribution models, all three
  `reviewPolicy` values.
- Stubbed `gh` for every PR helper (0% covered today).
- Explicit `unknown`-path coverage.
- Refspec and tag-push parsing, including `push origin main --tags` and `push origin HEAD:main`.
- `.github/workflows/ci.yml` actually runs them — closing the loop where the current repo ships
  four test files with no runner, no config, and no CI.

## Distribution

`submtd/shipyard` as a Claude Code plugin marketplace repo, with `keel` as its first plugin.
Siblings land in the same marketplace, so one `/plugin marketplace add` delivers the suite.

## Scope

**In scope for `keel`:** the git lifecycle — starting work, landing it, shipping it — plus
`init` scaffolding in increment 2.

**Out of scope**, deferred to sibling plugins: CI pipeline authoring (`rigging`), dependency
management (`bosun` / `manifest`), debugging and profiling (`fathom`), test tooling
(`ballast`), security scanning (`hull`).

## Increments

Each gets its own spec → plan → implementation cycle.

1. **Git lifecycle** — rule engine, advisory hook, lifecycle skills, `protect`, `doctor`,
   orientation, tests + CI. *(this spec)*
2. **Scaffolding** — `keel:init`: `.keel.json`, `.github/` templates, CODEOWNERS, LICENSE, a
   real `.gitignore`, `.editorconfig`.

## Open questions

None blocking increment 1.
