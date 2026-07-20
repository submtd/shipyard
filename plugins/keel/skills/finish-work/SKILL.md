---
name: finish-work
description: Use when a change is complete and ready to become a pull request - runs checks, updates the changelog, and opens the PR against the correct base.
---

# Finishing a change

## 1. Verify it works

Run the project's tests and linter. If you cannot tell what they are, ask.
**Do not proceed on a failing suite.** If tests fail, stop and report - fixing
them is the work now.

If `superpowers:requesting-code-review` is available, use it for a self-review
pass before continuing. If not, review your own diff with `git diff` and look
for debug output, commented-out code, and unrelated changes.

## 2. Update CHANGELOG.md

Add an entry under `## Unreleased`, in the user's voice - what changed for
someone using this project, not which functions you touched. A nested heading
such as `### Added` under Unreleased is fine and counts.

keel's gate checks that the Unreleased section *gained content* compared to
`HEAD` - the committed state, not your working tree. An edit that is only
staged or only on disk does not satisfy it; it must be part of the commit(s)
you push in step 4.

If `CHANGELOG.md` does not exist at all, either create one with an Unreleased
section or confirm with the user that `requireChangelog: false` is set in
`.keel.json` - otherwise the PR will be blocked outright.

## 3. Consider CLAUDE.md

Ask the user: does this change alter anything documented in `CLAUDE.md` -
commands, architecture, conventions? If so, update it together with them.

Do **not** edit `CLAUDE.md` just to have edited it, and do not treat this as a
mandatory step to satisfy some check - there is none. Most changes should not
touch it. The point is to ask the question, not to force an edit.

## 4. Commit and push

Write a conventional-commit message. Push the branch (to `origin` - your fork
if you're on one, the canonical repo otherwise). Pushing your own feature or
hotfix branch is never protected, so this needs no special handling.

## 5. Open the PR

Determine the base from `.keel.json`: `integration` for feature branches,
`production` for hotfix and release branches (under `trunk`, everything targets
`production`).

    gh pr create --base <base> --title "..." --body "..."

Write a body that says what changed and why, and how to verify it.

## 6. Report

Give the user the PR URL and say what happens next: it needs a review before it
can land (`keel:review`, then `keel:land`).
