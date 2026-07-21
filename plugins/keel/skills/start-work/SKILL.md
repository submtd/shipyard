---
name: start-work
description: Use when beginning any new change - creates a correctly-named branch from an up-to-date base, choosing fork or same-repo based on the repo's config and your permissions.
---

# Starting work

## 1. Read the config

Read the config at the repo root. You need `topology`, `branches`,
`prefixes`, and `contributions`. If `.keel.json` is absent, this repo is not
keel-managed - say so and stop.
Load it through keel's own loader rather than reading the raw JSON:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from keel.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

This matters because `keel:init` writes only the keys it detected --
`topology`, `branches`, `contributions`, `reviewPolicy`, `requireChangelog`.
`prefixes` and `mergeStrategy` are normally **absent** from the file, and
the loader is what supplies their defaults (`feature/`, `release/`,
`hotfix/`; `squash` into integration, `merge` into production). Read the raw
file and you will see nothing for those fields and have to guess -- and a
guess that disagrees with the loader produces a `merge-strategy` or
`pr-edge` block you cannot explain.


## 2. Decide the branch kind

Ask the user which applies if it is not obvious from their request:

- **feature** - normal work. Base branch is `integration` (or `production` under
  `trunk` topology).
- **hotfix** - an urgent fix to production. Base branch is `production`.

## 3. Decide fork vs same-repo

Run `gh repo view --json viewerPermission -q .viewerPermission`.

- `contributions` is `fork`, or you have `READ`/`TRIAGE` only -> work on a fork.
  Check for a fork with `gh repo fork --clone=false` (idempotent), ensure an
  `upstream` remote points at the canonical repo. Your working remote is
  `origin` (your fork); the canonical repo is `upstream`.
- Otherwise -> work directly in this clone. Your working remote is `origin`
  (the canonical repo itself).

Remember which remote is which - `keel:sync` later needs to fetch the
canonical repo's base branch, and that's `upstream` on a fork but `origin`
otherwise.

## 4. Create the branch

Fetch first so you branch from current code (use the canonical remote from
step 3 - `upstream` on a fork, `origin` otherwise):

    git fetch <remote> <base>
    git checkout -b <prefix><slug> <remote>/<base>

Derive `<slug>` from the user's description: lowercase, hyphenated, no more than
about five words.

## 5. Confirm

Tell the user the branch name, what it was based on, and that `CHANGELOG.md`
will need an Unreleased entry - committed, not just edited - before the PR
(unless `requireChangelog` is false).
