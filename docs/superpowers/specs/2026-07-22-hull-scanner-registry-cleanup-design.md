# hull scanner-registry cleanup (#30) — design

**Status:** approved for planning
**Issue:** [#30](https://github.com/submtd/shipyard/issues/30) — "hull: the
trufflehog pin has no automated bump path, and two scanner facts are hardcoded
outside the registry"

Four items deliberately deferred from the #27 review. None block other work;
all are the kind of latent inconsistency that bites a maintainer later. Each is
independent and separately testable — they share no code path — so this is one
plan with four self-contained tasks in no required order (though the tasks are
ordered registry-first so item 4's guard and item 3's field land before the
docs).

## Guiding invariants (unchanged by this work)

- **Engine purity.** The maintainer checker and docs live OUTSIDE
  `plugins/hull/hull/`; nothing here adds `os`/`subprocess`/networking under the
  engine, so `test_purity.py` stays green with no allowlist change. Item 2 edits
  `scripts/sync_action_pins.py`, which is already stdlib-only maintainer tooling
  outside the plugins.
- **Byte-identical goldens.** No rendered output changes. Item 3 moves *where*
  the trufflehog advisory string is authored (scaffold.py → the registry entry),
  not the string itself or anything rendered into a workflow. The three hull
  goldens (`security.yml`, `security-license.yml`, `security-trufflehog.yml`)
  stay byte-for-byte identical; this is the acceptance check for items 3 and 4.
- **Round-trip contract (#33).** Item 3 touches no signal keys and no
  `propose_config`/`load_config` path — only the scaffold advisory/blocker text
  and a new registry field with a default. `SIGNAL_KEYS` is untouched.

## Item 1 — the trufflehog pin's manual bump path (docs only)

**Problem.** `.github/dependabot.yml` scans `github-actions` in `/`, which only
sees action refs that appear in *this repo's own* workflow files.
`trufflesecurity/trufflehog` appears in none of them — by design, since
shipyard's own `security.yml` deliberately stays on gitleaks (personal-account
repo, no license gate to dodge). So Dependabot will never propose a bump for it,
and the pin ages silently. It is the first pin the suite ships to consumers
without dogfooding it, which is exactly what breaks the automated mechanism.

**Decision.** Document it; do not build automation for a single pin. A scheduled
CI checker or a maintainer-run script was considered and rejected as more
machinery than one pin warrants — the honest fix is to make the manual path
discoverable, not to hide the limitation behind partial automation.

**Change.** In `README.md`:

1. Add a row to the action-pin source-of-truth table:

   | Action | Pinned in |
   |---|---|
   | `trufflesecurity/trufflehog` | `plugins/hull/hull/scanners.py` |

   (placed after the existing `gitleaks/gitleaks-action` row, since both are
   hull scanners.)

2. Add a short note beneath the table, in the maintainer/Development section
   near where `sync_action_pins.py` is described:

   > Dependabot only bumps action refs that appear in a workflow committed to
   > *this* repo. Every pin above except `trufflesecurity/trufflehog` appears in
   > `.github/workflows/`, so Dependabot bumps it and `sync_action_pins.py`
   > propagates it into the registry. trufflehog does not — shipyard's own
   > `security.yml` uses gitleaks — so when a new trufflehog release ships, bump
   > `action_ref`/`action_ref_version` in `plugins/hull/hull/scanners.py` by
   > hand, then run `sync_action_pins.py` to regenerate the goldens.

**Test.** Documentation only; no automated test. Acceptance is the two README
edits present and accurate (the named file `scanners.py` genuinely holds the
pin; the named script genuinely regenerates goldens).

## Item 2 — `sync_action_pins.py` regenerates all hull goldens

**Problem.** `regenerate()` rewrites only `plugins/hull/tests/golden/security.yml`.
All three hull goldens embed the `actions/checkout` SHA, so the next checkout
bump rewrites the registry and `security.yml`, then fails
`test_license_plan_matches_golden_byte_for_byte` and
`test_trufflehog_matches_golden_byte_for_byte` with no script support. #27 added
a third stale-able golden without touching the script.

**Change.** In the embedded regen script inside `regenerate()`, replace the
single hull golden write with a filename→config mapping covering all three, and
write each:

```python
# hull imports already present in the script: Config as HC, build_plan as
# hplan, render as hrender. The existing single write is
#   hrender(hplan(HC(name="security", scanner="gitleaks")))
# -- a directly-constructed Config passed straight to build_plan, NO
# load_config. The map below keeps that exact shape.
hull_goldens = {
    "security.yml":            HC(name="security", scanner="gitleaks"),
    "security-license.yml":    HC(name="security", scanner="gitleaks",
                                  license_secret="GITLEAKS_LICENSE"),
    "security-trufflehog.yml": HC(name="security", scanner="trufflehog"),
}
# A golden on disk with no mapping here would be silently left stale after a
# pin bump -- the exact bug #30 item 2 fixes. Fail loudly instead.
from pathlib import Path as _P
on_disk = {p.name for p in _P("plugins/hull/tests/golden").glob("*.yml")}
missing = on_disk - set(hull_goldens)
assert not missing, f"hull goldens with no regen mapping: {sorted(missing)}"
for fn, cfg in hull_goldens.items():
    open("plugins/hull/tests/golden/" + fn, "w").write(hrender(hplan(cfg)))
```

The exact constructor arguments (`Config` field names for name/scanner/license
secret) must be taken verbatim from how the existing hull golden tests
construct configs — the plan task must read `plugins/hull/tests/` and the
current `sync_action_pins.py` hull write, and copy the real field names (the
license-secret argument name in particular: `license_secret=` above is the
expected snake_case field, but the plan confirms it against `hull/config.py`
and the `security-license.yml` golden test rather than assuming).

**Guard rationale.** Deriving the *target list* from the directory (per the
issue's suggestion) while keeping an explicit filename→config map is deliberate:
a pure `glob()` cannot know which config produces which golden, but a bare
hardcoded map silently skips a newly added golden. The `missing` assertion is
the reconciliation — the directory is the source of truth for *what must be
regenerated*, the map is the source of truth for *how*, and a gap between them
is a loud failure at regen time.

**Test.** `sync_action_pins.py` has no unit test today and this is maintainer
tooling; acceptance is running it end-to-end and confirming (a) all three hull
goldens are rewritten byte-identically when no pin changed (`git diff` empty),
and (b) the `missing` assertion fires if a stray `.yml` with no mapping is
dropped into the golden dir (verified once manually, not committed as a test).

## Item 3 — move two per-scanner facts into `ScannerSpec`

**Problem.** `scaffold.py` hardcodes `"trufflehog"` twice — as the named remedy
in the organization blocker, and as the gate for the BASE==HEAD advisory
(`if scanner == "trufflehog":`). Every *other* per-scanner fact (action pin,
permissions, license env, `with:` inputs) lives in `ScannerSpec`. Register a
third scanner and it gets no advisory mechanism and is never offered as a
remedy, with nothing failing to tell you.

**Change A — advisory field.** Add to `ScannerSpec`:

```python
#: A scanner-specific advisory (non-fatal caveat) surfaced at init, or None.
#: A fact about the tool, so it lives here beside the pin -- registering a
#: scanner with a quirk worth stating gets an advisory channel automatically,
#: where the old `if scanner == "trufflehog"` gate gave a third scanner none.
advisory: Optional[str] = None
```

Move the trufflehog BASE==HEAD advisory string verbatim from `scaffold.py` into
the trufflehog registry entry's `advisory=`. gitleaks leaves it unset. In
`check_preconditions`, replace the `if scanner == "trufflehog":` block with:

```python
if REGISTRY[scanner].advisory is not None:
    advisories.append(REGISTRY[scanner].advisory)
```

**Change B — derived remedy.** The org blocker currently ends by naming the
`"trufflehog"` scanner as the license-free alternative. Derive it instead:

```python
license_free = sorted(
    sid for sid, spec in REGISTRY.items() if spec.license_env is None
)
```

and phrase the remedy from `license_free` (today `["trufflehog"]`). The blocker
only fires for a scanner whose `license_env is not None`, and
`test_at_least_one_registered_scanner_needs_no_license` guarantees
`license_free` is non-empty, so the derived list is always non-empty when the
blocker fires. Exact wording is resolved in the plan; it must name the
license-free scanner(s) from the list rather than a literal, and read naturally
for the one-element case (the only case today).

**Tests.**
- Existing `security-trufflehog.yml` golden stays byte-identical (the advisory
  is init-time text, never rendered — but this confirms nothing rendered moved).
- A new test asserting `check_preconditions` with a trufflehog scanner still
  surfaces the BASE==HEAD advisory (behavior preserved through the refactor).
- A new test asserting the org blocker's remedy text contains the derived
  license-free scanner name (`"trufflehog"`) and that the string `"trufflehog"`
  does **not** appear as a literal in `scaffold.py` source outside a comment —
  i.e. the fact now comes from the registry. (Shape: read the module source,
  assert no literal `"trufflehog"` in executable lines; a targeted check, since
  the whole point is that the name is no longer hardcoded there.)
- The advisory-field test: `REGISTRY["trufflehog"].advisory` is set and
  `REGISTRY["gitleaks"].advisory is None`.

## Item 4 — copy `scan_with` like `env`

**Problem.** `plan._build_job` does `with_=spec.scan_with` (by reference) while
`_scan_env` does `dict(spec.env)` (copied), and
`test_build_plan_does_not_mutate_the_registry_spec_env` guards the env copy but
nothing guards `scan_with`. A caller mutating `plan.jobs[0].steps[1].with_`
would corrupt `REGISTRY["trufflehog"].scan_with` process-wide. Latent, not live
(no consumer mutates it; process is short-lived), but an asymmetry the existing
guard test makes read as an oversight.

**Change.** In `_build_job`:

```python
with_=dict(spec.scan_with) if spec.scan_with else None,
```

preserving the existing None-when-falsy behavior (gitleaks has
`scan_with=None`; the renderer omits a falsy `with:`).

**Test.** `test_build_plan_does_not_mutate_the_registry_spec_scan_with`,
mirroring the existing env guard: build a plan for the trufflehog scanner, mutate
the resulting step's `with_`, and assert `REGISTRY["trufflehog"].scan_with` is
unchanged. The trufflehog golden stays byte-identical (the copy is
value-identical to the reference).

## Acceptance for the whole branch

- Full suite green, count strictly greater than the pre-branch baseline (new
  tests in items 3 and 4; item 2 adds no committed test; item 1 none).
- `git diff` against the three hull goldens is empty (no rendered change).
- `test_purity.py` green with no allowlist edit.
- The round-trip property test green (no signal-key change).
