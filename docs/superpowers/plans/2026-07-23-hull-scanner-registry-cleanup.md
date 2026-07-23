# hull scanner-registry cleanup (#30) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close #30 — remove four latent inconsistencies from hull's scanner registry and its tooling, with zero change to any rendered workflow.

**Architecture:** Four independent fixes to `hull` and its maintainer tooling. Two touch the engine (`scanners.py`, `plan.py`) and are guarded by new tests plus byte-identical goldens; one edits the stdlib maintainer script `sync_action_pins.py`; one is README documentation. No signal keys, no rendered output, and no engine imports change.

**Tech Stack:** Python 3 stdlib only, pytest. `hull` engine = `config.load_config` → `plan.build_plan` → `render.render` over a `scanners.REGISTRY` data registry.

## Global Constraints

- **No rendered output changes.** The three hull goldens — `plugins/hull/tests/golden/security.yml`, `security-license.yml`, `security-trufflehog.yml` — MUST stay byte-for-byte identical. `git diff -- plugins/hull/tests/golden/` is empty at the end of every task. This is the acceptance check for Tasks 1 and 2.
- **Engine purity.** No `os`/`subprocess`/networking added under `plugins/hull/hull/`. `plugins/hull/tests/test_purity.py` stays green with no allowlist edit.
- **Round-trip contract (#33).** No change to `SIGNAL_KEYS`, `propose_config`, or `load_config`. Task 2 adds a registry field with a default and edits scaffold advisory/blocker text only.
- **Per-scanner facts live in `ScannerSpec`.** After Task 2, the string `"trufflehog"` MUST NOT appear anywhere in `plugins/hull/hull/scaffold.py` — every per-scanner fact is read from the registry or derived from it.
- **Registry constants, never user input.** The advisory text and derived remedy are registry-sourced strings; nothing user-supplied reaches them.
- **Suite green and strictly growing.** Baseline is **1436 passing**. Tasks 1 and 2 each add tests; Tasks 3 and 4 add none. Final count > 1436.

---

## File Structure

- `plugins/hull/hull/plan.py` — Task 1: copy `scan_with` before handing it to the step (mirrors the existing `dict(spec.env)` copy).
- `plugins/hull/tests/test_plan.py` — Task 1: new mutation-guard test mirroring `test_build_plan_does_not_mutate_the_registry_spec_env`.
- `plugins/hull/hull/scanners.py` — Task 2: new `advisory` field on `ScannerSpec`; trufflehog entry carries the BASE==HEAD advisory string.
- `plugins/hull/hull/scaffold.py` — Task 2: derive the org-blocker remedy from license-free scanners; replace the `scanner == "trufflehog"` advisory gate with `REGISTRY[scanner].advisory`.
- `plugins/hull/tests/test_scaffold.py` — Task 2: tests for the advisory field, the preserved advisory behavior, the derived remedy, and the no-literal-in-source guarantee.
- `scripts/sync_action_pins.py` — Task 3: regenerate all three hull goldens from a filename→config map, with a loud guard for an unmapped golden.
- `README.md` — Task 4: trufflehog row in the action-pin table + a manual-bump note.

Order is registry-and-engine first (Tasks 1–2), then the script that regenerates goldens (Task 3), then docs (Task 4).

---

## Task 1: Copy `scan_with` like `env` (issue item 4)

**Files:**
- Modify: `plugins/hull/hull/plan.py:75` (the `with_=spec.scan_with` argument in `_build_job`)
- Test: `plugins/hull/tests/test_plan.py` (add one test after `test_build_plan_does_not_mutate_the_registry_spec_env`, ~line 153)

**Interfaces:**
- Consumes: `hull.scanners.REGISTRY` (a `dict[str, ScannerSpec]`); `ScannerSpec.scan_with` is `Optional[dict]` (trufflehog: `{"extra_args": "--results=verified,unknown"}`; gitleaks: `None`). `hull.plan.build_plan(cfg) -> ScanPlan`; `plan.jobs[0].steps[1].with_` is the scan step's `with:` mapping.
- Produces: nothing new consumed downstream — the step's `with_` value is now a fresh `dict` (or `None`) instead of a reference to the registry object.

Context: `_scan_env` already does `env = dict(spec.env)` for exactly this reason (see its docstring and `test_build_plan_does_not_mutate_the_registry_spec_env` at `test_plan.py:145`). `scan_with` is the asymmetric one — passed by reference — and the issue's item 4 is that a caller mutating the resulting step's `with_` would corrupt `REGISTRY["trufflehog"].scan_with` process-wide.

- [ ] **Step 1: Write the failing test**

Add to `plugins/hull/tests/test_plan.py` (it already imports `build_plan`, `Config`, and `REGISTRY` — confirm the imports at the top of the file cover `from hull.scanners import REGISTRY`; the existing env-guard test at line 145 uses `REGISTRY` directly, so they do):

```python
def test_build_plan_does_not_mutate_the_registry_spec_scan_with():
    """The plan copies the registry's scan_with before handing it to the step,
    exactly as it copies env -- mutating the shared spec would corrupt the
    registry entry for every later plan built in the same process. trufflehog
    is the scanner that actually declares a scan_with."""
    before = dict(REGISTRY["trufflehog"].scan_with)
    plan = build_plan(Config(name="security", scanner="trufflehog"))
    # Mutating the rendered step's with_ must not reach back into the registry.
    plan.jobs[0].steps[1].with_["extra_args"] = "MUTATED"
    assert REGISTRY["trufflehog"].scan_with == before
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_plan.py::test_build_plan_does_not_mutate_the_registry_spec_scan_with -v`
Expected: FAIL — `REGISTRY["trufflehog"].scan_with` now contains `"MUTATED"`, so the assertion fails (the step's `with_` is the same object as the registry's `scan_with`).

- [ ] **Step 3: Implement the copy**

In `plugins/hull/hull/plan.py`, change the `scan_step` construction in `_build_job` (currently line 73-76):

```python
    scan_step = scanners.Step(uses=spec.action_ref,
                              env=_scan_env(spec, license_secret),
                              with_=dict(spec.scan_with) if spec.scan_with else None,
                              uses_version=spec.action_ref_version)
```

The `if spec.scan_with else None` preserves the exact existing behavior for gitleaks (`scan_with=None` → `with_=None`, which the renderer omits). For trufflehog, `dict(...)` is a value-identical copy, so the rendered `with:` block is unchanged.

- [ ] **Step 4: Run the new test and the golden tests to verify pass + no render change**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/ -q && git diff --stat -- plugins/hull/tests/golden/`
Expected: all hull tests PASS (including the new one and the existing `test_trufflehog_matches_golden_byte_for_byte`); `git diff --stat` on the golden dir prints nothing (no rendered change).

- [ ] **Step 5: Commit**

```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
git add plugins/hull/hull/plan.py plugins/hull/tests/test_plan.py
git commit -m "fix(hull): copy scan_with before rendering, like env (#30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2: Move the advisory and the license-free remedy into the registry (issue item 3)

**Files:**
- Modify: `plugins/hull/hull/scanners.py` (add `advisory` field to `ScannerSpec`; set it on the trufflehog entry)
- Modify: `plugins/hull/hull/scaffold.py:246-292` (derive remedy from license-free scanners; replace the `scanner == "trufflehog"` advisory gate)
- Test: `plugins/hull/tests/test_scaffold.py` (new tests)

**Interfaces:**
- Consumes: `hull.scanners.REGISTRY[scanner]` and `.license_env` (`Optional[str]`, `None` for trufflehog); `check_preconditions(signals) -> Preconditions(blockers: tuple[str,...], advisories: tuple[str,...])`.
- Produces: `ScannerSpec.advisory: Optional[str] = None` — a scanner-specific non-fatal caveat surfaced at init, read by `check_preconditions`.

Context: `scaffold.py` currently hardcodes `"trufflehog"` in two places — the org blocker's remedy text (line 258, inside an f-string) and the advisory gate `if scanner == "trufflehog":` (line 283). The existing test `test_at_least_one_registered_scanner_needs_no_license` guarantees at least one registry entry has `license_env is None`, which is what makes the derived remedy always non-empty when the blocker fires (the blocker only fires for a scanner whose `license_env is not None`).

### Part A — add the `advisory` field and move the string

- [ ] **Step 1: Write the failing test**

Add to `plugins/hull/tests/test_scaffold.py` (check its existing imports; it should already import from `hull.scaffold`. Add `from hull.scanners import REGISTRY` if not present):

```python
def test_trufflehog_carries_its_advisory_in_the_registry():
    """The BASE==HEAD advisory is a fact about the trufflehog tool, so it lives
    in the registry beside the pin -- not gated by name in scaffold.py."""
    assert REGISTRY["trufflehog"].advisory is not None
    assert "BASE and HEAD" in REGISTRY["trufflehog"].advisory
    assert REGISTRY["gitleaks"].advisory is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py::test_trufflehog_carries_its_advisory_in_the_registry -v`
Expected: FAIL — `ScannerSpec` has no `advisory` attribute (`AttributeError`).

- [ ] **Step 3: Add the field and set it on trufflehog**

In `plugins/hull/hull/scanners.py`, add a new field to `ScannerSpec` after `scan_with` (keep it last, with a default, so construction stays positional-safe):

```python
    #: A scanner-specific non-fatal advisory surfaced at hull:init, or None.
    #: A fact about the tool, so it lives here beside the pin rather than as a
    #: `scanner == "..."` gate in scaffold.py -- registering a scanner with a
    #: quirk worth stating gets an advisory channel automatically, where the
    #: old name-gate gave a third scanner none. A registry constant, never
    #: user input; surfaced by scaffold.check_preconditions.
    advisory: Optional[str] = None
```

Then, on the `"trufflehog"` entry, add the advisory string moved verbatim from `scaffold.py` (the current text at scaffold.py lines 285-291), placed after `scan_with=...`:

```python
        advisory=(
            "The trufflehog action exits 1 with \"BASE and HEAD commits are "
            "the same\" when the range it is asked to scan is empty. hull's "
            "triggers make that rare -- a branch's first push is handled by "
            "the action itself, and an ordinary push or pull request has a "
            "distinct base and head -- but if you do see that message, it is "
            "the action declining to scan nothing, not a finding and not a "
            "hull bug."
        ),
```

Copy the string text EXACTLY from the current `scaffold.py` so wording does not drift. The `gitleaks` entry needs no change (field defaults to `None`).

- [ ] **Step 4: Run the field test to verify it passes**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py::test_trufflehog_carries_its_advisory_in_the_registry -v`
Expected: PASS.

### Part B — read the advisory from the registry in `check_preconditions`

- [ ] **Step 5: Write the behavior-preservation test**

Add to `plugins/hull/tests/test_scaffold.py`:

```python
def test_trufflehog_scanner_still_surfaces_the_base_head_advisory():
    """Refactor preserves behavior: choosing trufflehog still yields the
    BASE==HEAD advisory at init, now sourced from the registry."""
    pre = check_preconditions({"name": "security", "scanner": "trufflehog"})
    assert any("BASE and HEAD" in a for a in pre.advisories)
```

(Confirm `check_preconditions` is imported at the top of `test_scaffold.py`; the existing precondition tests use it, so it is.)

- [ ] **Step 6: Run it — passes already via the OLD gate, so it is a guard not a driver**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py::test_trufflehog_scanner_still_surfaces_the_base_head_advisory -v`
Expected: PASS (the old `scanner == "trufflehog"` gate still produces it). This test exists to stay green THROUGH the next edit — it catches a refactor that drops the advisory.

- [ ] **Step 7: Replace the name-gate with the registry read**

In `plugins/hull/hull/scaffold.py`, replace the block at lines 277-292 (the comment plus `if scanner == "trufflehog":` and the appended advisory string) with:

```python
    # Scanner-specific and deliberately an advisory, not a blocker: a fact
    # about the tool, carried in the registry beside its pin (ScannerSpec.
    # advisory) rather than gated here by name, so a newly registered scanner
    # with a caveat gets this channel automatically.
    if REGISTRY[scanner].advisory is not None:
        advisories.append(REGISTRY[scanner].advisory)
```

- [ ] **Step 8: Run the advisory tests to verify they still pass**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py -k "advisory" -v`
Expected: both advisory tests PASS.

### Part C — derive the org-blocker remedy from license-free scanners

- [ ] **Step 9: Write the derived-remedy test**

Add to `plugins/hull/tests/test_scaffold.py`:

```python
def test_org_blocker_remedy_names_a_license_free_scanner_from_the_registry():
    """The org blocker offers the license-free alternative by DERIVING it from
    the registry (scanners whose license_env is None), not by hardcoding the
    name. Today that derives to trufflehog."""
    pre = check_preconditions({
        "name": "security", "scanner": "gitleaks", "ownerType": "Organization",
    })
    assert pre.blockers, "expected an organization blocker for gitleaks w/o license"
    blocker = pre.blockers[0]
    license_free = [sid for sid, spec in REGISTRY.items() if spec.license_env is None]
    assert license_free  # guaranteed by test_at_least_one_registered_scanner_needs_no_license
    assert all(sid in blocker for sid in license_free)


def test_scaffold_source_holds_no_hardcoded_scanner_name():
    """The whole point of item 3: no per-scanner fact is hardcoded in
    scaffold.py. After the refactor the module never names 'trufflehog' -- the
    advisory comes from the registry and the remedy is derived from it."""
    import hull.scaffold as scaffold_mod
    from pathlib import Path
    source = Path(scaffold_mod.__file__).read_text(encoding="utf-8")
    assert "trufflehog" not in source
```

- [ ] **Step 10: Run to verify they fail**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py -k "remedy or hardcoded" -v`
Expected: `test_scaffold_source_holds_no_hardcoded_scanner_name` FAILS (`"trufflehog"` still appears in the remedy f-string at line 258). The remedy test may already pass (the literal `"trufflehog"` happens to be in the string), but it must keep passing after derivation — so it is the guard and the source-scan is the driver.

- [ ] **Step 11: Derive the remedy**

In `plugins/hull/hull/scaffold.py`, in `check_preconditions`, just before the org-blocker `if` (currently line 246), compute the license-free list:

```python
    license_free = sorted(
        sid for sid, spec in REGISTRY.items() if spec.license_env is None
    )
```

Then rewrite the tail of the blocker message (currently line 257-259, the `-- or re-run hull:init choosing the "trufflehog" scanner, ...` clause) to name `license_free` instead of the literal. Replace the final clause of the appended blocker string with:

```python
            f"{license_env}\") so hull renders it into the scan step -- or "
            f"re-run hull:init choosing a scanner that needs no license "
            f"({', '.join(license_free)}), which needs no secret and fewer "
            f"token permissions."
```

`license_free` is `["trufflehog"]` today, so the rendered sentence reads "choosing a scanner that needs no license (trufflehog), which needs no secret and fewer token permissions." It reads naturally for the one-element case (the only case today) and stays correct if a second license-free scanner is registered.

- [ ] **Step 12: Run the whole scaffold test file**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/test_scaffold.py -q`
Expected: all PASS, including `test_scaffold_source_holds_no_hardcoded_scanner_name` (the word `"trufflehog"` is now gone from `scaffold.py`) and `test_org_blocker_remedy_names_a_license_free_scanner_from_the_registry`.

- [ ] **Step 13: Confirm no rendered change and full hull suite green**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest plugins/hull/tests/ -q && git diff --stat -- plugins/hull/tests/golden/`
Expected: all hull tests PASS; `git diff --stat` on the golden dir prints nothing (the advisory is init-time text, never rendered).

- [ ] **Step 14: Commit**

```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
git add plugins/hull/hull/scanners.py plugins/hull/hull/scaffold.py plugins/hull/tests/test_scaffold.py
git commit -m "refactor(hull): registry-source the advisory and license-free remedy (#30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3: Regenerate all three hull goldens in `sync_action_pins.py` (issue item 2)

**Files:**
- Modify: `scripts/sync_action_pins.py` — the embedded regen script inside `regenerate()` (the `open(".../security.yml", "w")...` hull write, ~line 232-233)

**Interfaces:**
- Consumes: the embedded script already imports `Config as HC`, `build_plan as hplan`, `render as hrender` from `hull` (see `regenerate()`), and constructs hull configs directly (`HC(name="security", scanner="gitleaks")`) with NO `load_config`.
- Produces: nothing importable — this is maintainer tooling; its output is the regenerated golden files.

Context: `regenerate()` currently rewrites only `plugins/hull/tests/golden/security.yml`. All three hull goldens embed the `actions/checkout` SHA, so the next checkout bump rewrites the registry and `security.yml`, then fails `test_license_plan_matches_golden_byte_for_byte` and `test_trufflehog_matches_golden_byte_for_byte`. The fix derives the target list from the golden directory (so a new golden cannot be silently missed) while keeping an explicit filename→config map (so each is rendered from the right config). This task adds no committed pytest test — `sync_action_pins.py` has none today and it is maintainer tooling; verification is running it end-to-end and confirming the goldens are unchanged when no pin moved, plus a one-off manual check that the guard fires.

- [ ] **Step 1: Read the current hull write and confirm the exact config field names**

Read `scripts/sync_action_pins.py` around the hull golden write (the line `open("plugins/hull/tests/golden/security.yml", "w").write(hrender(hplan(HC(name="security", scanner="gitleaks"))))`), and confirm hull's `Config` field for the license secret by reading `plugins/hull/hull/config.py` (it is `license_secret: Optional[str] = None`) and the `security-license.yml` golden test in `plugins/hull/tests/` (to see how it constructs the licensed config). Use the field names you find, not guesses.

- [ ] **Step 2: Replace the single hull write with a mapped, directory-guarded regen**

In `scripts/sync_action_pins.py`, inside the embedded `script` string in `regenerate()`, replace the single hull golden line with:

```python
hull_goldens = {
    "security.yml":            HC(name="security", scanner="gitleaks"),
    "security-license.yml":    HC(name="security", scanner="gitleaks",
                                  license_secret="GITLEAKS_LICENSE"),
    "security-trufflehog.yml": HC(name="security", scanner="trufflehog"),
}
# The directory is the source of truth for WHAT must be regenerated; the map
# is the source of truth for HOW to render each. A golden on disk with no
# mapping would be silently left stale after a pin bump -- the exact bug #30
# item 2 fixes -- so reconcile the two and fail loudly on a gap.
_hull_golden_dir = Path("plugins/hull/tests/golden")
_on_disk = {p.name for p in _hull_golden_dir.glob("*.yml")}
_missing = _on_disk - set(hull_goldens)
assert not _missing, f"hull goldens with no regen mapping: {sorted(_missing)}"
for fn, cfg in hull_goldens.items():
    (_hull_golden_dir / fn).write_text(hrender(hplan(cfg)), encoding="utf-8")
```

`Path` is already imported in the embedded script (it does `from pathlib import Path`). Confirm the licensed-config keyword argument name against what Step 1 found; if hull's field differs from `license_secret`, use the real name.

- [ ] **Step 3: Run the script and confirm the goldens are byte-identical (no pin moved)**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 scripts/sync_action_pins.py && git diff --stat -- plugins/hull/tests/golden/`
Expected: the script prints its normal summary and exits 0; `git diff --stat` on the golden dir prints **nothing** — no pin changed, so all three goldens re-render identically. If any golden changes, STOP: the map produces a different config than the committed golden and must be corrected.

- [ ] **Step 4: Manually verify the guard fires (do not commit the stray file)**

Run:
```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
touch plugins/hull/tests/golden/security-stray.yml
python3 scripts/sync_action_pins.py; echo "exit=$?"
rm plugins/hull/tests/golden/security-stray.yml
```
Expected: the run FAILS with a non-zero exit and a message naming `security-stray.yml` as a golden with no regen mapping (the `assert` fires through `subprocess.run(..., check=True)`). Then the file is removed so the tree is clean.

- [ ] **Step 5: Run the full suite to confirm nothing regressed**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest -q && git status --short`
Expected: full suite PASS (still > 1436); `git status --short` shows only the modified `scripts/sync_action_pins.py` (no stray golden, no golden changes).

- [ ] **Step 6: Commit**

```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
git add scripts/sync_action_pins.py
git commit -m "fix(scripts): regenerate all three hull goldens, guard unmapped ones (#30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4: Document trufflehog's manual bump path (issue item 1)

**Files:**
- Modify: `README.md:301-320` (action-pin table + the Dependabot note beneath it)

**Interfaces:** none — documentation only.

Context: `.github/dependabot.yml` scans `github-actions` in `/`, which only sees action refs in *this repo's* committed workflows. `trufflesecurity/trufflehog` appears in none (shipyard's own `security.yml` uses gitleaks by design), so Dependabot never bumps it. The README's pin table has no trufflehog row and the note does not mention the gap, so a maintainer chasing a stale pin has nothing pointing them at `scanners.py`. This task adds no test (documentation); acceptance is the two edits present and accurate.

- [ ] **Step 1: Add the trufflehog row to the action-pin table**

In `README.md`, in the table at lines 301-305, add a row after the `gitleaks/gitleaks-action` row:

```markdown
| `actions/checkout` | `plugins/rigging/rigging/plan.py`, `plugins/hull/hull/plan.py` |
| `actions/setup-python`, `actions/setup-node` | `plugins/rigging/rigging/stacks.py` |
| `gitleaks/gitleaks-action` | `plugins/hull/hull/scanners.py` |
| `trufflesecurity/trufflehog` | `plugins/hull/hull/scanners.py` |
```

- [ ] **Step 2: Add the manual-bump note beneath the Dependabot paragraph**

In `README.md`, after the existing fenced `git checkout dependabot/... / sync_action_pins.py / ...` block (ends ~line 320) and before the changelog-gate paragraph (~line 322), insert a new paragraph:

```markdown
One pin is the exception: `trufflesecurity/trufflehog`. Dependabot only bumps
refs that appear in a workflow committed to *this* repo, and shipyard's own
`security.yml` uses `gitleaks` — so trufflehog is shipped to consumers but
never dogfooded here, and Dependabot never proposes a bump for it. When a new
trufflehog release ships, edit `action_ref` and `action_ref_version` on the
`"trufflehog"` entry in `plugins/hull/hull/scanners.py` by hand, then run
`scripts/sync_action_pins.py` to regenerate the goldens.
```

- [ ] **Step 3: Verify the edits read correctly**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && sed -n '299,332p' README.md`
Expected: the table shows four rows ending with the trufflehog row; the new manual-bump paragraph appears after the fenced sync block and names `plugins/hull/hull/scanners.py` and `scripts/sync_action_pins.py`.

- [ ] **Step 4: Run the docs/marketplace-adjacent tests (cheap safety net) and commit**

Run: `cd /Users/steveharmeyer/Development/submtd/shipyard && python3 -m pytest -q`
Expected: full suite PASS (README is not asserted by any test, but this confirms nothing else moved).

```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
git add README.md
git commit -m "docs: name trufflehog's manual pin-bump path (#30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Changelog (final step before finishing the branch)

After Task 4, add one `Unreleased` entry to `CHANGELOG.md` under a `### Fixed` heading (create the heading under `## [Unreleased]` if absent), covering all four items as one maintainer-facing fix. keel's changelog gate requires an accurate user/maintainer-facing entry:

```markdown
### Fixed

- **hull's scanner registry no longer leaks per-scanner facts into the
  scaffolder, and its goldens all regenerate.** The BASE==HEAD advisory and
  the license-free remedy the organization blocker offers are now derived from
  `ScannerSpec` instead of naming `trufflehog` in `scaffold.py`, so a
  third scanner gets an advisory channel and is offered as a remedy
  automatically; `sync_action_pins.py` regenerates all three hull goldens (not
  just one) with a loud guard for an unmapped golden; the scan step copies its
  `with:` inputs before rendering, matching how it already copies `env`; and
  the README names trufflehog's manual bump path, since Dependabot cannot see a
  pin that appears in no committed workflow (#30).
```

Commit:
```bash
cd /Users/steveharmeyer/Development/submtd/shipyard
git add CHANGELOG.md
git commit -m "docs(changelog): note the hull scanner-registry cleanup (#30)

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Acceptance for the whole branch

- Full suite green, count strictly greater than the 1436 baseline (Tasks 1 and 2 add tests; 3 and 4 add none).
- `git diff` against the three hull goldens is empty across the whole branch (no rendered change).
- `plugins/hull/tests/test_purity.py` green with no allowlist edit.
- The round-trip property test (`test_*roundtrip*` / `test_propose_config_*`) green — no signal-key change.
- The word `"trufflehog"` does not appear in `plugins/hull/hull/scaffold.py`.
- `scripts/sync_action_pins.py` regenerates all three hull goldens and fails loudly on an unmapped one.
