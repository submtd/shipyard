---
name: land
description: Use when an approved pull request should be merged - checks the gates and merges with the strategy the repo's config requires.
---

# Landing a pull request

## 1. Check it is ready

    gh pr view <number> --json baseRefName,headRefName,reviewDecision,reviews,mergeable

Confirm:
- there is a review, and no outstanding `CHANGES_REQUESTED` - unless this is a
  release or back-merge PR (head is `release/*` or the production branch),
  which keel exempts from the review gate entirely
- `mergeable` is not `CONFLICTING` - if it is, the author needs `keel:sync`
- CI is passing

## 2. Use the configured strategy

Read `mergeStrategy` from `.keel.json` (`toIntegration`, `toProduction` -
default `squash` and `merge`, but either can be set to `squash`, `merge`, or
`rebase`). Match the PR's base branch to the configured strategy and use that
flag - don't assume squash-into-integration/merge-into-production if the repo
has set something else:

    gh pr merge <number> --squash --delete-branch
    gh pr merge <number> --merge
    gh pr merge <number> --rebase

The wrong strategy is blocked outright (`[merge-strategy]`), so if you're
unsure, check the config rather than guess.

Do not delete the branch on a merge into `production` - release branches are
sometimes needed again. Deleting the branch on a merge into `integration` is
fine and typical.

## 3. Report

Say what merged, into what, and what the next step is - usually
`keel:release` once enough has accumulated on `integration`.
