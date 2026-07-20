---
name: protect
description: Use to configure GitHub branch protection so the workflow is actually enforced server-side, rather than only advised by the hook - set up rulesets, require reviews, or lock down force-pushes.
---

# Configuring real enforcement

keel's hook is advisory - it runs only inside Claude Code and only catches
honest mistakes made through it. It is not a security boundary: it cannot stop
a push made outside Claude Code, from another tool, or from someone who never
installed the plugin. **This skill sets up the enforcement that actually
holds, server-side, for everyone.**

## 1. Check you can

    gh repo view --json viewerPermission -q .viewerPermission

You need `ADMIN`. If you do not have it, tell the user what to ask their
administrator for and stop.

## 2. Confirm before changing anything

Branch protection is outward-facing and affects every contributor, not just
this session - and it is not a quick undo once other people start relying on
it. **Before making any `gh api` call**, show the user the exact rule you are
about to apply, filled in with real values from `.keel.json` (branch name,
required approving review count, status check contexts) - not a template.
Get explicit confirmation. If they want changes, adjust and show it again
before proceeding.

## 3. Protect the production branch

Requires a PR, passing checks, and (usually) an approving review. Resolve
`<count>` from the `reviewPolicy` table below before running this.

Note `-F` (not `-f`) on the numeric and boolean fields: `-f` sends every value
as a JSON string, so `-f ...count=1` would send `"1"` where GitHub expects an
integer and the call would fail.

    gh api -X PUT repos/{owner}/{repo}/branches/<production>/protection \
      -H "Accept: application/vnd.github+json" \
      -F "required_pull_request_reviews[required_approving_review_count]=<count>" \
      -F "enforce_admins=false" \
      -F "required_status_checks[strict]=true" \
      -f "required_status_checks[contexts][]=test" \
      -F "restrictions=null"

The required approving review count depends on `reviewPolicy`:

- `approval` - set it to `1`. A real approval is required and GitHub can
  enforce that natively.
- `review` - set it to `0`. This policy exists precisely because GitHub
  forbids self-approval; requiring 1 here would lock a solo maintainer out of
  their own repository. Note the limitation honestly: GitHub's native review
  requirement only understands `APPROVED`, not `COMMENTED`, so there is no
  server-side way to require "at least a comment." Under `review`, the
  comment-review convention is enforced by keel's hook and by team practice,
  not by branch protection - `enforce_admins=false` is what keeps the door
  open for the maintainer to merge their own PR after commenting on it.
- `none` - omit `required_pull_request_reviews` entirely, or set the count to
  `0`.

## 4. Protect the integration branch

Same call against `<integration>`, unless topology is `trunk` (in which case
`integration` equals `production` and there is nothing separate to protect).

## 5. Add the changelog check

The hook's changelog rule only binds inside Claude Code. To make it real, the
repo needs a CI job that fails when a feature or hotfix PR does not add an
`Unreleased` entry (release and back-merge PRs are exempt, same as the hook).
Offer to write `.github/workflows/changelog.yml` if one does not exist, and
add its job name to `required_status_checks[contexts]` above.

## 6. Report

List what is now enforced server-side versus what remains advisory. Be
explicit that anything not in the former list can still be bypassed - by a
repo admin, by a tool other than Claude Code, or (for `review` policy's
comment convention) by anyone with write access, since GitHub cannot enforce
that part natively.
