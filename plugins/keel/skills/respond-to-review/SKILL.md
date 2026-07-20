---
name: respond-to-review
description: Use when a pull request has review comments to address - reads the feedback, evaluates it, makes the changes, and replies.
---

# Responding to review feedback

## 1. Read the feedback

    gh pr view <number> --json reviews,comments
    gh pr diff <number>

## 2. Evaluate before implementing

If `superpowers:receiving-code-review` is available, use it.

Otherwise, for each comment decide: is it correct? Reviewers are sometimes
wrong, and agreeing with a wrong suggestion makes the code worse. Where you
disagree, say so with a reason rather than complying silently.

Group the comments into: **will fix**, **will not fix (with reason)**, and
**needs clarification**.

## 3. Confirm the plan

Show the user that grouping before you change anything. This is the step that
prevents a round of churn.

## 4. Make the changes

One commit per coherent group of fixes. Do not force-push over the reviewed
history - the reviewer needs to see what changed since their pass. A plain
`git push` (no `--force`) is fine and expected here.

## 5. Update the changelog if behaviour changed

If review feedback altered user-facing behaviour, the `Unreleased` entry needs
to match - and that edit must be committed (keel's changelog gate compares
against `HEAD`, not the working tree), not just left staged.

## 6. Reply and re-request

Reply to each thread saying what you did or why you did not. Then:

    gh pr review <number> --comment --body "..."
    gh pr ready <number>   # if it was a draft

A `COMMENTED` review from you does not satisfy keel's own review gate on this
PR - that gate needs the *reviewer's* sign-off (`APPROVED`, or `COMMENTED`
under `reviewPolicy: review`). This step is about closing the loop with the
reviewer, not about clearing keel's gate yourself.
