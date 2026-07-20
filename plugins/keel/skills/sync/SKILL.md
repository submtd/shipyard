---
name: sync
description: Use when a branch or fork has fallen behind its base, or before opening a PR after a delay - brings the branch up to date and resolves conflicts.
---

# Syncing a stale branch

## 1. Work out what is stale

Read `.keel.json`. Work out the base branch from the current branch's prefix:
`integration` for a feature branch, `production` for a hotfix (or, under
`trunk` topology, `production` in both cases). Work out which remote holds the
canonical repo: `upstream` if you're on a fork (per `keel:start-work`),
`origin` otherwise. Call that remote `<remote>` below.

    git fetch --all --prune
    git log --oneline HEAD..<remote>/<base> | head -20

If that is empty, the branch is current - say so and stop.

## 2. If this is a fork, fetch upstream's base directly - do not push it

    git fetch upstream <base>

Rebase or merge (step 3) against `upstream/<base>` directly. Do **not** try to
"refresh" your fork's own copy of `<base>` by pushing to it
(`git push origin <base>`) - keel's guard blocks any push whose destination
branch is named `production` or `integration`, and it checks the branch name
in the refspec, not which remote or repo owns it. That push will be denied
even though it targets your own fork. There's no need for it anyway: always
fetch `upstream/<base>` fresh rather than keeping a local mirror in sync.

## 3. Update the working branch

Rebase when the branch has not been reviewed yet - it keeps history readable:

    git checkout <branch>
    git rebase <remote>/<base>

**Merge instead of rebasing if the PR is already under review.** Rewriting
history mid-review destroys the reviewer's ability to see what changed:

    git merge <remote>/<base>

## 4. Resolve conflicts

Resolve each one, run the tests, then continue. If a conflict is in
`CHANGELOG.md`, keep both entries - they are usually independent.

## 5. Push

Push only the working branch - never `<base>` itself (see step 2).

After a rebase you will need `--force-with-lease` (never plain `--force`):

    git push --force-with-lease

After a merge, a normal push works.
