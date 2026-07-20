---
name: release
description: Use when preparing a release - picks the version, rolls the changelog, and opens the release pull request.
---

# Preparing a release

## 1. See what is unreleased

    git log --oneline <production>..<integration>

Read the `Unreleased` section of `CHANGELOG.md`.

**Under `trunk` topology, stop here and skip to `keel:ship`.** There is no
integration branch and no release branch or PR - `pr-edge` only allows
`feature|hotfix -> production` under trunk, so a release branch has nowhere
valid to land. Every change already reached `production` directly through its
own PR; a release under trunk is just picking a point on `production`'s
history, rolling the changelog there, and tagging it. The rest of this skill
(steps 2-5) is the gitflow/github-flow path, where a release branch batches
several integrated changes before they reach `production`.

## 2. Choose the version

Semantic versioning, judged from the changes:

- **patch** - fixes only. Proceed.
- **minor** - anything added. **Confirm with the user first.**
- **major** - anything removed or changed incompatibly. **Confirm with the
  user first, and say what breaks.**

Never pick minor or major without asking.

## 3. Create the release branch

    git fetch origin
    git checkout -b <releasePrefix><version> origin/<integration>

## 4. Roll the changelog

Rename `## Unreleased` to `## <version> - YYYY-MM-DD` and add a fresh empty
`## Unreleased` above it. Use the real current date. Commit it - the
changelog gate (where it applies) compares against `HEAD`, not the working
tree, though release PRs are exempt from that gate anyway (see step 5).

## 5. Open the PR

    gh pr create --base <production> --title "release: <version>" --body "..."

The body should be the changelog section for this version - it becomes the
release notes.

keel does not require a changelog entry or a review on release PRs (head kind
`release`); the content was already reviewed on the way into `integration`.

## 6. Report

Give the user the PR URL and tell them `keel:ship` comes after it merges
(land it first with `keel:land`, using the `production` merge strategy).
