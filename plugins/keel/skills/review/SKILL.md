---
name: review
description: Use when reviewing a pull request - reads the full diff, evaluates it against the project's standards, and posts a review.
---

# Reviewing a pull request

## 1. Read it properly

    gh pr view <number>
    gh pr diff <number>

Read the whole diff, not a summary of it. Check out the branch and run the
tests if the change is non-trivial.

## 2. Evaluate

If `superpowers:requesting-code-review` is available, use it for the analysis.

Otherwise assess, in this order:

1. **Correctness** - does it do what it claims? What input breaks it?
2. **Tests** - is the new behaviour covered? Would the tests fail if the
   implementation were wrong?
3. **Scope** - does the diff contain anything the PR does not claim to do?
4. **Changelog** - is the Unreleased entry accurate and user-facing? (Skip
   this check for release and back-merge PRs - keel doesn't require one there
   either, since the content was already reviewed on the way into
   integration.)

## 3. Post the review

Be specific. "This breaks when `items` is empty" is useful; "consider edge
cases" is not.

    gh pr review <number> --request-changes --body "..."
    gh pr review <number> --approve --body "..."
    gh pr review <number> --comment --body "..."

If you are the PR's author, GitHub will not let you approve. Post a `--comment`
review instead. With `reviewPolicy: review` that satisfies keel's gate; with
`reviewPolicy: approval` it does not, and someone else must approve.
`CHANGES_REQUESTED` blocks the PR regardless of policy, so only use
`--request-changes` when you mean it.

## 4. Report

Tell the user the verdict and whether it is ready for `keel:land`.
