---
name: doctor
description: Use when keel blocked or warned about something unexpectedly, or to understand the current repo's lifecycle state - explains what keel sees, what each rule name means, and why it decided what it did.
---

# keel doctor

## 1. Gather the state

    git rev-parse --show-toplevel
    git symbolic-ref --short HEAD
    git remote -v
    gh repo view --json viewerPermission -q .viewerPermission
    cat .keel.json
    gh auth status

## 2. Report what keel sees

- config: topology, protected branches (production/integration), review
  policy, merge strategies, whether a changelog is required
- current branch, and which kind keel classifies it as (production,
  integration, feature, release, hotfix, or other)
- your permission level, and whether `gh` is authenticated

## 3. Explain the block

If keel denied something, the message carried a rule name in brackets. If
more than one rule fired, the first bracketed name is the primary reason;
anything after `Also: [rule] ...` fired too but wasn't the blocking cause -
worth fixing, but not why the command stopped. What each name means:

- **`protected-write`** - the commit or push targets a protected branch
  (matched by name - `production` or `integration` from `.keel.json`). For a
  push, keel reads the *destination* refspec, so `git push origin HEAD:main`
  counts as targeting `main` even from a feature branch. Use
  `keel:start-work` instead of committing or pushing directly.

  **Known limitation:** this check matches on branch *name*, not on which
  repo or remote owns it. keel cannot tell your fork's own `main` apart from
  the canonical repo's `main` - both are just a branch named `main`. So
  pushing to `main` on a fork you fully control is denied too, even though
  nobody else's history is at risk. This is by design, not a bug to work
  around: `keel:sync` is written to never need that push (it fetches the
  canonical remote's base fresh instead of refreshing a local mirror), so if
  you hit this unexpectedly, the fix is usually to stop trying to keep your
  fork's protected branch updated at all, not to bypass the check.

- **`pr-edge`** - the PR's head and base are not a valid pair for this
  topology. Under gitflow: feature -> integration, release -> production,
  hotfix -> production, and production -> integration (the back-merge). Under
  `trunk`: only feature/hotfix -> production - there is no release branch.

- **`changelog`** - the `Unreleased` section of `CHANGELOG.md` did not gain
  content on this branch. This is checked against the *committed* state
  (`HEAD`), not the working tree or the index - an edit that's only staged or
  only on disk does not count, it has to be part of a commit. Release and
  back-merge PRs are exempt; they carry no new user-facing change of their
  own.

- **`merge-strategy`** - the PR was merged with the wrong flag for its base.
  Read `mergeStrategy` in `.keel.json`: whatever is configured for
  `toIntegration`/`toProduction` (defaults `squash`/`merge`) is what that base
  requires, not necessarily squash-into-integration/merge-into-production.

- **`review`** - blocked because either `CHANGES_REQUESTED` is outstanding
  (this always blocks, regardless of policy), or no qualifying review exists
  yet. What qualifies depends on `reviewPolicy`: `approval` needs an
  `APPROVED` review; `review` accepts `APPROVED` *or* `COMMENTED` - this is
  what makes solo maintainers workable, since GitHub won't let you approve
  your own PR; `none` doesn't gate on review at all. Release and back-merge
  PRs are exempt from this gate entirely (their content was already reviewed
  on the way into integration).

- **`capability`** - never blocks, only warns. keel thinks (from
  `viewerPermission`) that you may lack merge permission on this repo. It's a
  heads-up, not a gate - if you actually do have permission, ignore it.

## 4. Explain a warning

Most warnings mean keel could not determine something (a fact came back
unknown) and let the action proceed rather than guess - the usual cause is a
missing base ref; run `git fetch` and retry if you want the check to
actually run. The `capability` warning is the one exception: it is a
known-FALSE, not an unknown - keel asked GitHub and got a real answer
(`viewerPermission` is below write access), it just never blocks on that
answer alone.

## 5. Say what keel does not do

If the user is surprised keel allowed something, or that a block only
happened inside Claude Code: the hook is advisory. It runs only inside Claude
Code, does not parse shell constructs adversarially, and is not a security
boundary - anyone with push access can bypass it entirely by not using this
tool. `keel:protect` configures the enforcement that actually holds
server-side; point the user there if what they want is a guarantee rather
than a nudge.
