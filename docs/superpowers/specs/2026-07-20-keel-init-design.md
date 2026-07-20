# keel:init — design

**Date:** 2026-07-20
**Status:** Approved
**Increment:** 2 of keel (Shipyard suite)
**Depends on:** keel v0.1.1 (the git-lifecycle increment)

## Summary

`keel:init` stamps keel's workflow into a repository: it writes the lifecycle
artifacts a keel-managed repo needs, detecting sensible defaults and confirming
them, and never destroying anything already present.

It is a **skill backed by tested helpers** — the interview and inspection are
judgment (skill territory), while the two correctness-critical operations
(proposing a valid config, classifying existing files) are pure, tested Python.

## Scope: lifecycle only

keel owns the git *lifecycle*, not language tooling. `init` writes only
workflow artifacts. It does **not** detect the project's stack, and does **not**
write a language-specific `.gitignore` or `.editorconfig` — those belong to a
future stack-aware sibling plugin, not keel. Drawing the line here keeps keel's
thesis intact: the same reason CI *pipeline authoring* was deferred to `rigging`.

## What it writes

| File | Content |
|---|---|
| `.keel.json` | topology + policy, from detection the user confirms |
| `CHANGELOG.md` | Keep-a-Changelog skeleton with an empty `## [Unreleased]` — the exact shape keel's own parser expects, including nested `### Added` support |
| `.github/PULL_REQUEST_TEMPLATE.md` | encodes the changelog / CLAUDE.md checklist keel enforces |
| `.github/ISSUE_TEMPLATE/bug_report.md` | bug template |
| `.github/ISSUE_TEMPLATE/feature_request.md` | feature template |
| `.github/workflows/changelog.yml` | the server-side changelog gate |
| `scripts/check_changelog.py` | the gate's implementation — **self-contained** (stdlib only, no `keel` import) so it runs in any repo, since `keel` is not installed in a scaffolded target |
| `CODEOWNERS` | scaffold with a comment explaining the format; user fills owners |
| `LICENSE` | only if the user picks one; skipped otherwise |

The `changelog.yml` and `check_changelog.py` are **copied verbatim** from the
versions proven on the shipyard repo itself — one source of truth, not
regenerated per-repo. This is the artifact `keel:protect` step 5 already offers
to write; `init` ships it up front.

**Portability constraint:** `check_changelog.py` must be **self-contained** —
stdlib only, no `keel` import. A scaffolded target repo does not have the keel
package installed, so a script that did `import keel` would fail in exactly the
repos `init` targets. It therefore inlines the small amount of logic it needs
(parse `.keel.json` for topology/prefixes/`requireChangelog`, apply the
release/back-merge exemption, diff the CHANGELOG `Unreleased` section against the
base). This is a deliberate, tested duplication of a slice of `keel.gitio`/
`keel.rules`. shipyard's own `scripts/check_changelog.py` is made self-contained
too, so the shipped template stays byte-identical to the copy this repo runs
(enforced by a drift-guard test).

## Behavior

### Config detection, not interrogation

`init` inspects before it asks, and only asks about what it cannot infer:

- **topology** — a `develop` branch exists → propose `gitflow`; only `main`
  (or the default branch) → propose `trunk`.
- **contributions** — `gh repo view` capability plus whether the repo takes
  outside contributions → propose `fork` / `branch` / `both`.
- **reviewPolicy**, **requireChangelog** — sensible defaults (`review`, `true`),
  stated and adjustable.

It then shows the proposed `.keel.json` in full and confirms before writing.
It never silently guesses, and never asks a question it could answer by looking.

### No-clobber is absolute

For every candidate file, `init` classifies existence first:

- **Absent** → write it.
- **Present** → never overwrite. Show a short diff/summary and offer: keep
  theirs, merge (only for `.keel.json` and `CHANGELOG.md`, where a merge is
  well-defined), or skip. A `LICENSE` or `CHANGELOG.md` the user already wrote
  is theirs.

### Already keel-managed → top-up mode

If a valid `.keel.json` already loads, `init` switches from "scaffold" to
"top up": it reports what is already present and offers only the missing
pieces. Running `init` a second time is safe and uneventful — the property a
scaffolder must have.

### Verification built in

After scaffolding, `init` proves what it wrote actually works: it loads the
`.keel.json` through `load_config`, and runs the generated `check_changelog.py`
against the current state. It reports what it created, what it skipped, and the
verification result. If a stack-specific `.gitignore`/`.editorconfig` is
absent, it says so and names the (future) sibling that owns them, rather than
writing them.

## Architecture

### Tested helpers — `plugins/keel/keel/scaffold.py`

Pure, no I/O beyond reading; both unit-tested.

- `propose_config(signals: dict) -> dict`
  Maps detected signals (`has_develop: bool`, `capability: Tri`,
  `contributions_hint: str | None`) to a proposed `.keel.json` dict. Tested
  against the signal→topology table so detection cannot silently drift.

- `classify_files(root: Path, candidates: list[str]) -> dict[str, str]`
  Returns each candidate as `"absent"` or `"present"`, so the no-clobber
  decision is deterministic and testable rather than ad-hoc `ls` in the skill.

### Round-trip guarantee

A test feeds every `propose_config` output through `config.load_config` and
asserts it loads without raising. `init` can therefore never produce a
`.keel.json` that keel itself would reject — the one place correctness is
non-negotiable, so the one place with a hard test.

### The skill — `plugins/keel/skills/init/SKILL.md`

Drives the flow: detect signals → `propose_config` → confirm → `classify_files`
→ write the absent ones (prompting on the present ones) → verify → report.
Frontmatter is `name` + `description` only, matching the other ten skills.

## Testing

- `test_scaffold.py`: the signal→config table, the round-trip guarantee, and
  `classify_files` against a real temp repo (absent, present, mixed).
- No new test infrastructure; everything runs under the existing pytest suite
  and the CI matrix (3.9 / 3.12).

## Out of scope (tracked, not built here)

- Language-specific `.gitignore` / `.editorconfig` and any stack detection —
  a future stack-aware sibling plugin.
- CI *pipeline* authoring beyond the changelog gate — `rigging`.
- Rewriting existing files' content beyond the defined merge cases.

## Open questions

None blocking implementation.
