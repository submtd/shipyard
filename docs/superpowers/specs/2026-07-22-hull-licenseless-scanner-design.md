# hull: a scanner with no license gate

**Issue:** #27 · **Date:** 2026-07-22 · **Status:** approved, not yet implemented

## Why

0.6.0 taught `hull:init` to refuse rather than scaffold a workflow that cannot
pass. In an organization-owned repo with no gitleaks license, that refusal is
correct — but look at the resting state it leaves: **the repo gets no secret
scanning at all.**

`hull.scanners.REGISTRY` has exactly one entry, so the remedy the blocker
message itself offers — "or choose a scanner with no license gate" — is advice
with nothing behind it. This closes that gap by making the alternative real.

The framing from #24 still applies, one level up: refusing to scaffold beats
scaffolding something broken, but *offering a working alternative* beats both.

## What is being added

### 1. A `trufflehog` entry in the scanner registry

    trufflesecurity/trufflehog@27b0417c16317ca9a472a9a8092acce143b49c55  # v3.95.9

| field | value | why |
|---|---|---|
| `checkout_fetch_depth` | `"0"` | TruffleHog's documented requirement; full history |
| `env` | `{}` | nothing to pass — the renderer omits a falsy `env` block |
| `permissions` | `("contents: read",)` | narrower than gitleaks |
| `license_env` | `None` | the entire point |
| `scan_with` | `{"extra_args": "--results=verified,unknown"}` | see below |

TruffleHog needs only `contents: read` because it reads base and head from the
GitHub event payload rather than enumerating a PR's commits through the API —
the API call is precisely why gitleaks additionally needs `pull-requests:
read`. So the licenseless option is also the least-privileged one. That is a
happy accident, not a design goal, but it is worth stating: it means choosing
trufflehog costs the repo nothing in scope.

**`--results=verified,unknown`** is TruffleHog's own documented
recommendation. `verified` means the credential was live-tested and works;
`unknown` means TruffleHog has no verifier for that shape and could not test
it. Reporting both was chosen over `verified` alone because a secret the tool
*cannot* verify is exactly the kind it should not stay quiet about — in a
private org repo, internal and custom token formats are often most of them.
`unverified` is deliberately excluded: reporting everything trains a team to
ignore the check, which is the failure mode the org blocker exists to prevent.

### 2. One new field: `ScannerSpec.scan_with`

The only structural change in the design. TruffleHog needs a `with:` block on
the scan step and gitleaks never did.

This is smaller than it looks. `Step` already carries `with_`, and
`render._step_lines` already emits it — `plan._build_job` simply never had
anything to pass. So the change is one optional field plus one line in
`_build_job`, not new rendering machinery.

`scan_with=None` for gitleaks keeps its rendered output byte-identical, which
the existing goldens assert.

### 3. The blocker message names the alternative

`check_preconditions` needs **no logic change**. It already keys the org
blocker off the scanner's `license_env` rather than off the owner type alone,
and `test_organization_with_a_licenseless_scanner_is_clear` already passes
today using a monkeypatched registry. That test stops needing the monkeypatch,
which is the tell that the guard was written for this world in advance.

Only the message string changes: today it ends "or choose a scanner with no
license gate", naming nothing real. It will name `trufflehog`.

### 4. A new advisory (not a blocker)

TruffleHog's action exits 1 when `BASE == HEAD`, printing
`::error::BASE and HEAD commits are the same.`

This belongs in the **advisory** channel beside the existing fork-PR caveat,
not the blocker channel, and the distinction is the same one #24 established:

- gitleaks' org gate is **systematic** — given an org-owned repo and no
  license, it fails every run, always. That is a blocker.
- `BASE == HEAD` is an **edge case** under hull's triggers. A branch's first
  push is explicitly handled by the action (it sets `BASE=""` when
  `github.event.before` is all zeros), and normal pushes and pull requests
  have distinct base and head. It is worth stating out loud so a rare red run
  is not mistaken for a hull bug — which is exactly what the advisory channel
  is for.

## What is NOT changing

- **`scanner` still defaults to `gitleaks`.** Changing the default would give
  every existing repo a different scanner on a re-run of `init`.
- **`hull:init` still refuses and stops** at the org blocker rather than
  offering an interactive switch. The message tells the user to re-run
  choosing `trufflehog`; they come back having decided. This keeps
  `check_preconditions` pure and preserves the refuse-and-stop rule 0.6.0
  established.
- **`_valid_scanner` needs no change.** It already validates against
  `SCANNER_IDS`, which is derived from the registry. `.hull.json`'s `scanner`
  key simply becomes meaningful for the first time, having had exactly one
  legal value until now.
- **shipyard's own `security.yml` stays on gitleaks.** This is a
  personal-account repo where gitleaks works; switching it would churn a
  dogfooded artifact for no reason.
- **Nothing here helps fork PRs.** GitHub withholds secrets from fork runs by
  design. A licenseless scanner sidesteps that too, since it needs no secret —
  a real benefit for a repo with `contributions` of `"fork"` or `"both"`, but
  a side effect rather than the goal.

## Testing

- **A third golden**, `security-trufflehog.yml`, pinning the new rendered
  output byte-for-byte. The two existing goldens must not move; that is what
  proves gitleaks output is untouched.
- **The injection suite covers the new scanner.** Critically, that `github.`
  still never appears anywhere in rendered output. This was the design's main
  risk: TruffleHog's action *can* be wired with explicit `base`/`head` inputs,
  which would require `${{ github.event... }}` expressions and break that
  invariant outright. The basic form auto-detects from the event payload and
  needs no such wiring — which is why the design uses it.
- **Registry-wide tests now cover two scanners rather than one**, including
  the existing least-privilege assertion and the "registry never stores a
  license value" assertion. Several tests that loop over `REGISTRY` gain their
  first real second case.
- `test_organization_with_a_licenseless_scanner_is_clear` and
  `test_advisory_absent_for_a_scanner_with_no_license_gate` drop their
  `monkeypatch` staging and use the real entry.

## Risks

- **The pin is a release SHA of the `trufflehog` repo itself**, not a
  dedicated action repo — the action lives at that repo's root. Dependabot
  bumps it like any other pinned action, and `scripts/sync_action_pins.py`
  propagates the bump back into the registry. No new mechanism.
- **AGPL 3.0.** TruffleHog OSS is AGPL; it runs as a CI step against the
  repo, not linked into anything shipped, so this is not a licensing concern
  for consumers. Worth stating in the skill so nobody has to work it out.
