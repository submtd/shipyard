---
name: ship
description: Use after a release pull request has merged (or, under trunk topology, when it's time to cut a release from production) - tags the release, publishes notes, and back-merges into the integration branch.
---

# Shipping a release

## 1. Confirm there is something to tag

Under gitflow, confirm the release PR merged:

    gh pr list --state merged --base <production> --limit 5

Stop if it has not merged yet - `keel:release` comes first.

Under `trunk` topology there is no release PR to check - just confirm
`CHANGELOG.md` on `production` has the `Unreleased` section rolled into a
versioned one (see `keel:release` step 1) before tagging.

## 2. Tag the merge commit

    git checkout <production>
    git pull origin <production>
    git tag -a v<version> -m "v<version>"
    git push origin v<version>

Push the tag by name alone. keel exempts tag refs from the protected-branch
rule, but only the tag refs themselves - `git push origin <production> --tags`
still pushes the branch ref in the same command and is still blocked.

## 3. Publish the release

    gh release create v<version> --title "v<version>" --notes "..."

Use the changelog section for this version as the notes.

## 4. Back-merge into integration

Skip this entirely under `trunk` topology - there is no integration branch,
and `production` and `integration` are the same branch there.

    git checkout <integration>
    git pull origin <integration>
    gh pr create --base <integration> --head <production> \
      --title "chore: back-merge v<version>" --body "..."

The tag commit must reach `integration` or the next release will show phantom
differences. keel exempts this PR from the changelog and review gates (head
kind `production`), but not from the merge-strategy gate - land it with
`keel:land` using whatever strategy is configured for PRs into `integration`
(default `squash`).

## 5. Report

Give the user the release URL and confirm the back-merge PR is open (or, under
trunk, that there's no back-merge needed).
