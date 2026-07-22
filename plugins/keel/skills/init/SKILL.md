---
name: init
description: Use to set up keel in a repository - scaffolds .keel.json, a changelog, PR and issue templates, CODEOWNERS, the changelog CI gate, and optionally a license, detecting sensible defaults and never overwriting existing files.
---

# Initialising keel in a repo

This scaffolds the **lifecycle** layer only. It does not write a language
`.gitignore`/`.editorconfig` or any stack tooling — that is not keel's job.

## 1. Read the current state

Confirm you are at the repo root (`git rev-parse --show-toplevel`). Then detect:

- Does a `develop` branch exist? `git show-ref --verify --quiet refs/heads/develop || git ls-remote --exit-code --heads origin develop` — either hit means yes.
- The target's actual default (production) branch: `git symbolic-ref --quiet --short refs/remotes/origin/HEAD` (strip the `origin/` prefix from the result); if that's empty, fall back to
  `gh repo view --json defaultBranchRef -q .defaultBranchRef.name`; if neither resolves, default to `main`. Do not assume `main` before trying both — plenty of repos default to `master` or something else.
- Your permission: `gh repo view --json viewerPermission -q .viewerPermission` (may be empty outside a GitHub remote — that's fine).
- Is this repo already keel-managed? Check whether `.keel.json` exists and, if so, whether it loads:
  `python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from keel.config import load_config; from pathlib import Path; print(load_config(Path('.')))"`
  (`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `keel` package sits at its top level.)

That last check has three possible outcomes, and they are not the same thing:

- **No `.keel.json`** — proceed with normal scaffold mode (sections 2-5).
- **`.keel.json` exists and loads** — switch to top-up mode (section 6).
- **`.keel.json` exists but raises `ConfigError`** — it's present but invalid
  (unparseable JSON, wrong types, or a value outside an allowed enum). Do NOT
  switch to top-up mode, and do NOT treat this like a normal absent-file case
  either — see the present-but-invalid handling in section 4, and skip
  straight there for this file once you've finished the rest of this section.

## 2. Propose the config

Build a signals dict from what you detected and ask the user only for what you
cannot infer:

- `has_develop` — from detection.
- `production` — the default branch resolved in section 1. Pass it through
  explicitly; `propose_config` otherwise hardcodes `"main"`, which is wrong
  for any repo whose default branch is `master` or something else.
- `contributions` — `fork`, `branch`, or `both`. Default `both`; if the repo
  clearly takes no outside contributions, suggest `branch`.
- `review_policy` — `approval` (needs an approving review), `review` (a comment
  suffices — right for solo maintainers, since GitHub forbids self-approval),
  or `none`. Default `review`.
- `require_changelog` — default `true`.

Under gitflow (`has_develop` true), `integration` defaults to `develop` inside
`propose_config` — only override it if the user tells you their integration
branch has a different name.

Call `keel.scaffold.propose_config(signals)` to get the `.keel.json` dict, show
it to the user in full — including the resolved `production` branch, so they
can catch a wrong guess before it's written — and confirm. Adjust and re-show
if they want changes.

## 3. Classify what's already there

Call `keel.scaffold.classify_files(root, keel.scaffold.LIFECYCLE_FILES)`. This
tells you, deterministically, which artifacts are absent (safe to write) and
which are present (must not be clobbered). This only reflects file
*existence* — `.keel.json`'s validity was already established in section 1
(absent / loads / present-but-invalid); classify_files just confirms it's there.

Several of these artifacts aren't pinned to a single path — GitHub itself
recognizes more than one location for them — and writing keel's copy at its
preferred path while a foreign one sits at a different recognized path would
shadow or compete with it. Before treating any of the following as absent,
also classify their alternate locations (pass the extra candidate paths into
`classify_files`, or call it again for them), and treat the artifact as
**present** — skip writing it, and report why — if it exists at ANY
recognized location:

- `.github/PULL_REQUEST_TEMPLATE.md` — also check `PULL_REQUEST_TEMPLATE.md`
  (repo root) and `docs/PULL_REQUEST_TEMPLATE.md`. `.github/` is the preferred
  location; either alternate counts as present.
- `CODEOWNERS` — also check `.github/CODEOWNERS` and `docs/CODEOWNERS`, in
  addition to the root path already in `LIFECYCLE_FILES`. GitHub recognizes
  `.github/`, root, and `docs/`, first found wins; any hit counts as present.
- `.github/ISSUE_TEMPLATE/bug_report.md` and `feature_request.md` — also check
  a legacy root `ISSUE_TEMPLATE.md`. Its presence is equivalent to the whole
  `.github/ISSUE_TEMPLATE/` directory already existing — don't write the
  structured templates on top of it.

Also note, going into section 4, which of `.github/workflows/changelog.yml`
and `scripts/check_changelog.py` are present versus absent — they're a linked
pair there, not two independent files.

## 4. Write the absent artifacts

For each **absent** file, write it:

- `.keel.json` — the confirmed dict, pretty-printed. Skip this entirely if
  section 1 found `.keel.json` present-but-invalid — that's not an absent
  file, it's handled below instead.
- `CHANGELOG.md`, `CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`
  — copy from `${CLAUDE_PLUGIN_ROOT}/templates/`. Per section 3, treat any of
  these as present (don't write) if it — or one of its GitHub-recognized
  alternate locations — already exists; never write the `.github/` variant
  when the thing that's actually present lives at an alternate location.
- `.github/workflows/changelog.yml` ← `templates/changelog.yml`, and
  `scripts/check_changelog.py` ← `templates/check_changelog.py`. Treat these
  two as a linked pair, not independent files — the workflow invokes the
  script with a fixed 2-arg CLI, so one without the other is a broken gate:
  - **Both absent** — write both, as normal.
  - **Both present** — leave both alone (present-file handling below).
  - **Exactly one present** — do NOT silently write the other half. Warn the
    user that the file you'd scaffold depends on the pre-existing (possibly
    foreign) one's CLI contract: a foreign `scripts/check_changelog.py` may
    not accept keel's `<base> <head>` arguments, and a foreign workflow may
    not invoke keel's script the way it expects. Write the missing half only
    on the user's explicit confirmation that they want it wired up anyway.
- `LICENSE` — only if the user picks one. Ask which; if they decline, skip it.
  (Fetch standard license text however you normally would, or ask the user to
  paste it. Do not invent license text.)

For each **present** file, do NOT overwrite. Tell the user it exists and offer:
keep theirs, or — for `CHANGELOG.md` and a **present-and-valid** `.keel.json`
only — merge (add the missing keys / add an empty `## [Unreleased]` above the
top entry if absent). Never touch a present `LICENSE`, template, workflow, or
script.

If section 1 found `.keel.json` present but invalid (raises `ConfigError`),
merge is off the table — there's no reliable structure to merge into. Offer
only: **keep theirs** (and flag clearly in the final report that keel is
inactive until the file is fixed, and that section 5's verification is
skipped as a result), or an **explicit user-directed replace** — show them
the full proposed dict from section 2 and overwrite `.keel.json` only if they
explicitly ask you to. Never fall back to an implicit merge for this case.

## 5. Verify and report

Prove what you wrote works:

- `python3 -c "... load_config(Path('.')) ..."` — must print a Config, not
  raise. Skip this if `.keel.json` is present-but-invalid and the user chose
  to keep it (section 4) — say in the report that verification was skipped
  for that reason, not that it passed.
- Confirm the changelog gate is wired by calling it with an **exempt**
  invocation, not a real work-branch check: `python3 scripts/check_changelog.py
  <production> <production>` — the default branch resolved in section 1,
  passed as BOTH arguments. A production head is always exempt from the gate
  (in either topology), so this must exit 0 and print an "... is exempt from
  the changelog gate" line; that proves the script runs and is wired
  correctly, independent of whether the current branch has a changelog entry
  yet. Do NOT run it as `<base> <current-branch>` to "check" it — on a work
  branch that hasn't added a changelog entry yet, that legitimately prints
  `::error::` and exits 1. That's the gate doing its job, not init failing;
  it's just not a usable verification signal, so don't use it as one here.

**Under gitflow, get `.keel.json` onto the integration branch too.** This is
the single most important thing in this section, and skipping it silently
disables everything you just set up:

- `keel:start-work` branches from `integration` (`develop`), not from the
  branch you are standing on now.
- If the scaffold only exists on `production`, every feature branch is cut
  from a `develop` that has no `.keel.json` — so `load_config` finds nothing
  and **no rule is evaluated on any feature branch**, which is precisely
  where the guard is meant to work.

So after committing here, make sure the config reaches `integration` before
anyone runs `keel:start-work` — merge this branch into it (through a PR if
`integration` is already protected), or scaffold on `integration` in the
first place. Say explicitly in your report which branches now carry the
config. The guard will flag this if it is missed (`[keel] This repo uses
keel, but .keel.json is not on this branch...`), but that is a backstop, not
the plan.

Report: what you created, what you skipped (and why), the confirmed config,
which branches carry it, and the verification result. Note that `.gitignore`/`.editorconfig` were **not**
written — those belong to a stack-aware tool, not keel.

Point the user at `keel:protect` to make the workflow real server-side, and at
`keel:start-work` to begin their first change.

## 6. Top-up mode (already keel-managed)

Do not re-scaffold. Classify as in section 3 — including the alternate-location
checks and the workflow/script pairing note — and offer only the **absent**
pieces, writing each exactly as in section 4 (including the pairing
confirmation when exactly one of the workflow/script is present). Leave the
existing `.keel.json` alone unless the user asks to change it. Report what was
added and what was already present.
