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
- Your permission: `gh repo view --json viewerPermission -q .viewerPermission` (may be empty outside a GitHub remote — that's fine).
- Is this repo already keel-managed? Check whether `.keel.json` exists and loads:
  `python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from keel.config import load_config; from pathlib import Path; print(load_config(Path('.')))"`
  (`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `keel` package sits at its top level.)

**If `.keel.json` already loads, switch to top-up mode (section 6).**

## 2. Propose the config

Build a signals dict from what you detected and ask the user only for what you
cannot infer:

- `has_develop` — from detection.
- `contributions` — `fork`, `branch`, or `both`. Default `both`; if the repo
  clearly takes no outside contributions, suggest `branch`.
- `review_policy` — `approval` (needs an approving review), `review` (a comment
  suffices — right for solo maintainers, since GitHub forbids self-approval),
  or `none`. Default `review`.
- `require_changelog` — default `true`.

Call `keel.scaffold.propose_config(signals)` to get the `.keel.json` dict, show
it to the user in full, and confirm. Adjust and re-show if they want changes.

## 3. Classify what's already there

Call `keel.scaffold.classify_files(root, keel.scaffold.LIFECYCLE_FILES)`. This
tells you, deterministically, which artifacts are absent (safe to write) and
which are present (must not be clobbered).

## 4. Write the absent artifacts

For each **absent** file, write it:

- `.keel.json` — the confirmed dict, pretty-printed.
- `CHANGELOG.md`, `CODEOWNERS`, `.github/PULL_REQUEST_TEMPLATE.md`,
  `.github/ISSUE_TEMPLATE/bug_report.md`, `.github/ISSUE_TEMPLATE/feature_request.md`
  — copy from `${CLAUDE_PLUGIN_ROOT}/templates/`.
- `.github/workflows/changelog.yml` ← `templates/changelog.yml`, and
  `scripts/check_changelog.py` ← `templates/check_changelog.py`.
- `LICENSE` — only if the user picks one. Ask which; if they decline, skip it.
  (Fetch standard license text however you normally would, or ask the user to
  paste it. Do not invent license text.)

For each **present** file, do NOT overwrite. Tell the user it exists and offer:
keep theirs, or — for `.keel.json` and `CHANGELOG.md` only — merge (add the
missing keys / add an empty `## [Unreleased]` above the top entry if absent).
Never touch a present `LICENSE`, template, or workflow.

## 5. Verify and report

Prove what you wrote works:

- `python3 -c "... load_config(Path('.')) ..."` — must print a Config, not raise.
- Run the changelog gate against the base branch to confirm it's wired:
  `python3 scripts/check_changelog.py <base> <current-branch>` (a warning about
  an unresolved base is fine here — it means the gate is callable).

Report: what you created, what you skipped (and why), the confirmed config, and
the verification result. Note that `.gitignore`/`.editorconfig` were **not**
written — those belong to a stack-aware tool, not keel.

Point the user at `keel:protect` to make the workflow real server-side, and at
`keel:start-work` to begin their first change.

## 6. Top-up mode (already keel-managed)

Do not re-scaffold. Run `classify_files` and offer only the **absent** pieces,
writing each exactly as in section 4. Leave the existing `.keel.json` alone
unless the user asks to change it. Report what was added and what was already
present.
