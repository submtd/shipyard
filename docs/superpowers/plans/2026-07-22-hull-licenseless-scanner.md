# hull Licenseless Scanner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give hull a second scanner (`trufflehog`) that needs no license, so an organization-owned repo is not left with no secret scanning at all.

**Architecture:** hull's engine is a pure pipeline — `config.load_config` → `plan.build_plan` → `render.render` — driven by a data registry (`scanners.REGISTRY`). Adding a scanner is almost entirely a registry entry. The single structural change is a new optional `ScannerSpec.scan_with` field, because TruffleHog needs a `with:` block on its scan step and gitleaks never did.

**Tech Stack:** Python 3.9+, stdlib only, pytest. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-07-22-hull-licenseless-scanner-design.md`

## Global Constraints

- **Engine purity.** No `os`, `subprocess`, or networking may enter any module under `plugins/hull/hull/`. An AST test enforces this repo-wide.
- **Stdlib only.** No new dependencies, in engine or tests.
- **Existing goldens must not move.** `tests/golden/security.yml` and `tests/golden/security-license.yml` are byte-identity assertions on gitleaks output. If either changes, the change is wrong.
- **Action refs are SHA pins.** `owner/repo@<40-hex>`, with `action_ref_version` carrying the human-readable tag. A `@v3`-style ref is rejected by an existing test.
- **`github.` must never appear in rendered output.** `test_no_github_context_reference` enforces this. TruffleHog's basic form needs no `${{ github.* }}` wiring, which is why the design uses it.
- **Run from the repo root**, `/Users/steveharmeyer/Development/submtd/shipyard`. The full suite is `python3 -m pytest -q` and must stay at **1331 passed** plus whatever each task adds.
- **Exact pin to use:** `trufflesecurity/trufflehog@27b0417c16317ca9a472a9a8092acce143b49c55` with `action_ref_version="v3.95.9"`.

## File Structure

| File | Responsibility | Change |
|---|---|---|
| `plugins/hull/hull/scanners.py` | Registry of scanners | Add `scan_with` field; add `trufflehog` entry |
| `plugins/hull/hull/plan.py` | Config → plan | Pass `spec.scan_with` into the scan `Step` |
| `plugins/hull/hull/scaffold.py` | Init-time guards | Blocker message names `trufflehog`; new `BASE == HEAD` advisory |
| `plugins/hull/tests/golden/security-trufflehog.yml` | Byte-identity pin | Create |
| `plugins/hull/skills/init/SKILL.md` | Operator instructions | Document the scanner choice |
| `CHANGELOG.md` | Release notes | New `Unreleased` entry |

`render.py` is **not** modified — `_step_lines` already emits `with_` and already omits a falsy `env`.

---

### Task 1: `ScannerSpec.scan_with`, with gitleaks output unchanged

The enabling field. Deliberately separate from Task 2 so that "gitleaks output did not move" is proven by a commit that adds no scanner.

**Files:**
- Modify: `plugins/hull/hull/scanners.py` (add field to `ScannerSpec`, after `license_env`)
- Modify: `plugins/hull/hull/plan.py:66-77` (`_build_job`)
- Test: `plugins/hull/tests/test_plan.py`, `plugins/hull/tests/test_scanners.py`

**Interfaces:**
- Produces: `ScannerSpec.scan_with: Optional[dict] = None` — the scan step's `with:` mapping, or `None` to emit no `with:` block. Consumed by Task 2.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/hull/tests/test_scanners.py`:

```python
def test_scan_with_defaults_to_none():
    """A scanner that needs no `with:` block says so by omission, so the
    renderer emits nothing rather than an empty mapping."""
    spec = ScannerSpec(
        id="example",
        action_ref="owner/action@" + "a" * 40,
        action_ref_version="v1",
        checkout_fetch_depth="0",
        env={},
    )
    assert spec.scan_with is None


def test_gitleaks_needs_no_scan_with():
    """gitleaks is configured entirely through env, so adding this field
    must not have given it a `with:` block."""
    assert REGISTRY["gitleaks"].scan_with is None
```

Append to `plugins/hull/tests/test_plan.py`:

```python
def test_scan_step_carries_the_specs_scan_with(monkeypatch):
    """The registry's scan_with reaches the rendered step rather than being
    dropped between plan and render. Staged with a patched registry because
    no scanner declares scan_with yet -- monkeypatch.setitem, matching how
    every other registry-staging test in this suite is written."""
    import dataclasses

    from hull import scanners

    withful = dataclasses.replace(scanners.REGISTRY["gitleaks"],
                                  scan_with={"extra_args": "--flag"})
    monkeypatch.setitem(scanners.REGISTRY, "gitleaks", withful)
    job = build_plan(Config(name="security", scanner="gitleaks")).jobs[0]
    assert job.steps[1].with_ == {"extra_args": "--flag"}


def test_scan_step_has_no_with_when_the_spec_declares_none():
    job = build_plan(Config(name="security", scanner="gitleaks")).jobs[0]
    assert job.steps[1].with_ is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/hull/tests/test_scanners.py::test_scan_with_defaults_to_none plugins/hull/tests/test_plan.py::test_scan_step_carries_the_specs_scan_with -v`

Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'scan_with'` and `AttributeError`.

- [ ] **Step 3: Add the field**

In `plugins/hull/hull/scanners.py`, immediately after the `license_env` field in `ScannerSpec`:

```python
    #: The scan step's `with:` mapping, or None when the scanner needs no
    #: inputs at all. A registry constant, never user input -- which is what
    #: keeps it outside the injection surface: `with:` values are rendered as
    #: quoted YAML scalars exactly like `env:` values, but unlike
    #: `licenseSecret` nothing here is derived from .hull.json, so no
    #: validation is required for it and none is implied. A scanner needing a
    #: user-supplied `with:` value would be a genuinely new decision, not an
    #: extension of this one.
    scan_with: Optional[dict] = None
```

- [ ] **Step 4: Pass it through the plan**

In `plugins/hull/hull/plan.py`, change the `scan_step` construction inside `_build_job`:

```python
    scan_step = scanners.Step(uses=spec.action_ref,
                              env=_scan_env(spec, license_secret),
                              with_=spec.scan_with,
                              uses_version=spec.action_ref_version)
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1335 passed`. Critically, the two golden tests still pass — this change adds a field nobody uses yet, so gitleaks output is byte-identical.

- [ ] **Step 6: Commit**

```bash
git add plugins/hull/hull/scanners.py plugins/hull/hull/plan.py plugins/hull/tests/test_scanners.py plugins/hull/tests/test_plan.py
git commit -m "feat(hull): add ScannerSpec.scan_with, unused by any scanner yet

The enabling field for a scanner configured through \`with:\` rather than
\`env:\`. Committed alone so that gitleaks' output being byte-identical is
proven by a commit that adds no scanner.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: The `trufflehog` registry entry and its golden

**Files:**
- Modify: `plugins/hull/hull/scanners.py` (new `REGISTRY` entry)
- Create: `plugins/hull/tests/golden/security-trufflehog.yml`
- Test: `plugins/hull/tests/test_render.py`, `plugins/hull/tests/test_scanners.py`, `plugins/hull/tests/test_injection.py`

**Interfaces:**
- Consumes: `ScannerSpec.scan_with` from Task 1.
- Produces: `REGISTRY["trufflehog"]`, and therefore `"trufflehog" in SCANNER_IDS`. Consumed by Tasks 3 and 4.

- [ ] **Step 1: Write the golden**

Create `plugins/hull/tests/golden/security-trufflehog.yml` with exactly this content (note: no `env:` block, and only one permission line):

```yaml
name: "security"
on:
  push:
    branches: ["main"]
  pull_request:
permissions:
  contents: read
jobs:
  trufflehog:
    runs-on: "ubuntu-latest"
    steps:
      - uses: "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1"  # v7
        with:
          fetch-depth: "0"
      - uses: "trufflesecurity/trufflehog@27b0417c16317ca9a472a9a8092acce143b49c55"  # v3.95.9
        with:
          extra_args: "--results=verified,unknown"
```

- [ ] **Step 2: Write the failing tests**

Append to `plugins/hull/tests/test_render.py`:

```python
def test_trufflehog_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {"scanner": "trufflehog"}))
    assert render(build_plan(cfg)) == read_golden("security-trufflehog.yml")


def test_trufflehog_renders_no_env_block(tmp_path):
    """It needs no secret at all, so an `env:` block would be an empty
    mapping -- the renderer omits a falsy env rather than emitting one."""
    cfg = load_config(write(tmp_path, {"scanner": "trufflehog"}))
    assert "env:" not in render(build_plan(cfg))


def test_trufflehog_grants_narrower_permissions_than_gitleaks(tmp_path):
    """It reads base and head from the event payload rather than
    enumerating a PR's commits through the API, so it does not need the
    `pull-requests: read` gitleaks requires."""
    truffle = render(build_plan(load_config(write(tmp_path, {"scanner": "trufflehog"}))))
    assert "pull-requests: read" not in truffle
    assert "contents: read" in truffle


def test_gitleaks_goldens_did_not_move(tmp_path):
    """The whole-file guard: adding a scanner must not perturb the existing
    one's output in any way."""
    plain = load_config(write(tmp_path, {}))
    assert render(build_plan(plain)) == read_golden("security.yml")
    licensed = load_config(write(tmp_path, {"licenseSecret": "GITLEAKS_LICENSE"}))
    assert render(build_plan(licensed)) == read_golden("security-license.yml")
```

Append to `plugins/hull/tests/test_scanners.py`:

```python
def test_trufflehog_is_registered_and_has_no_license_gate():
    assert "trufflehog" in SCANNER_IDS
    assert REGISTRY["trufflehog"].license_env is None


def test_trufflehog_reports_verified_and_unknown_results():
    """--results is the noise/recall dial. `unknown` is included because a
    secret trufflehog cannot verify is exactly the kind it should not stay
    quiet about; `unverified` is excluded because reporting everything
    trains a team to ignore the check."""
    extra_args = REGISTRY["trufflehog"].scan_with["extra_args"]
    assert extra_args == "--results=verified,unknown"
    assert "unverified" not in extra_args


def test_at_least_two_scanners_are_registered():
    """The registry's second entry is what makes `scanner` a real choice and
    the org blocker's "choose a scanner with no license gate" remedy real."""
    assert len(SCANNER_IDS) >= 2


def test_at_least_one_registered_scanner_needs_no_license():
    """The property #27 exists to establish, asserted directly rather than
    by naming trufflehog -- a future registry must not lose it."""
    assert any(spec.license_env is None for spec in REGISTRY.values())
```

Append to `plugins/hull/tests/test_injection.py`:

```python
def test_trufflehog_output_contains_no_expressions_at_all(tmp_path):
    """It takes no secret, so there is nothing to interpolate. Zero `${{ }}`
    is the strongest possible version of assertion 3."""
    cfg = load_config(write_config(tmp_path, {"scanner": "trufflehog"}))
    output = render(build_plan(cfg))
    assert EXPRESSION_RE.findall(output) == []
    assert "github." not in output
    for block in iter_run_blocks(output):
        assert "${{" not in block


def test_trufflehog_scan_with_values_are_quoted_scalars(tmp_path):
    """`with:` values are rendered exactly like `env:` values -- quoted, so
    a leading dash cannot be read back as a YAML list item."""
    cfg = load_config(write_config(tmp_path, {"scanner": "trufflehog"}))
    assert '          extra_args: "--results=verified,unknown"' in render(build_plan(cfg))
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `python3 -m pytest plugins/hull/tests/test_render.py -k trufflehog -v`

Expected: FAIL — `ConfigError: .hull.json: 'scanner' must be one of gitleaks (got 'trufflehog')`. That error confirms `_valid_scanner` derives from the registry and needs no change of its own.

- [ ] **Step 4: Add the registry entry**

In `plugins/hull/hull/scanners.py`, add to `REGISTRY` after the `gitleaks` entry:

```python
    "trufflehog": ScannerSpec(
        id="trufflehog",
        action_ref="trufflesecurity/trufflehog@27b0417c16317ca9a472a9a8092acce143b49c55",
        action_ref_version="v3.95.9",
        checkout_fetch_depth="0",
        # Nothing to pass: trufflehog needs no token and no license, which is
        # the entire reason this entry exists. The renderer omits a falsy
        # env rather than emitting an empty mapping.
        env={},
        # Narrower than gitleaks deliberately, and not an oversight: this
        # action reads base and head from the event payload instead of
        # enumerating a pull request's commits through the API, and that API
        # call is exactly why gitleaks additionally needs pull-requests:read.
        permissions=("contents: read",),
        # AGPL 3.0 open source, no license key, no organization gate. This is
        # the property the whole entry exists for -- see check_preconditions,
        # which keys its organization blocker off license_env being set.
        license_env=None,
        # trufflehog's own documented recommendation. `verified` means the
        # credential was live-tested and works; `unknown` means it has no
        # verifier for that shape and could not test it. Both are reported
        # because a secret the tool CANNOT verify is exactly the kind it
        # should not stay quiet about -- in a private repo, internal and
        # custom token formats are often most of them. `unverified` is
        # excluded: reporting everything trains a team to ignore the check,
        # which is the failure mode the organization blocker exists to
        # prevent in the first place.
        scan_with={"extra_args": "--results=verified,unknown"},
    ),
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1345 passed`. If `security.yml` or `security-license.yml` fails, stop — gitleaks output moved and something is wrong.

- [ ] **Step 6: Commit**

```bash
git add plugins/hull/hull/scanners.py plugins/hull/tests/
git commit -m "feat(hull): register trufflehog, a scanner with no license gate

Closes the gap 0.6.0 left: an organization-owned repo with no gitleaks
license now has a working alternative rather than no secret scanning at all.
Needs only contents:read, since it reads base and head from the event
payload rather than enumerating a PR's commits through the API.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: The blocker message names trufflehog

**Files:**
- Modify: `plugins/hull/hull/scaffold.py` (the `blockers.append(...)` string in `check_preconditions`)
- Test: `plugins/hull/tests/test_scaffold.py`, `plugins/hull/tests/test_config.py`

**Interfaces:**
- Consumes: `REGISTRY["trufflehog"]` from Task 2.

No logic changes. `check_preconditions` already keys the blocker off `license_env`.

- [ ] **Step 1: Write the failing test**

Append to `plugins/hull/tests/test_scaffold.py`:

```python
def test_blocker_names_the_licenseless_scanner_concretely():
    """Before #27 the message ended "or choose a scanner with no license
    gate", which named nothing real -- the registry had one entry. The
    remedy is only actionable if it names the scanner to re-run with."""
    (blocker,) = check_preconditions({"ownerType": "Organization"}).blockers
    assert "trufflehog" in blocker


def test_every_remedy_the_blocker_offers_actually_exists():
    """Guards the message against drifting back into naming a scanner that
    was removed from the registry."""
    (blocker,) = check_preconditions({"ownerType": "Organization"}).blockers
    named = [s for s in SCANNER_IDS if s in blocker]
    assert "trufflehog" in named
    for scanner_id in named:
        assert scanner_id in REGISTRY
```

Add the imports this needs at the top of `plugins/hull/tests/test_scaffold.py`:

```python
from hull.scanners import REGISTRY, SCANNER_IDS
```

(The file currently imports `SCANNER_IDS` only — extend that line rather than adding a second import.)

- [ ] **Step 2: Run to verify it fails**

Run: `python3 -m pytest plugins/hull/tests/test_scaffold.py::test_blocker_names_the_licenseless_scanner_concretely -v`

Expected: FAIL — `assert 'trufflehog' in "This repository is owned by..."`.

- [ ] **Step 3: Update the message**

In `plugins/hull/hull/scaffold.py`, replace the final clause of the blocker string. Change:

```python
            f"\"{license_env}\") so hull renders it into the scan step -- or "
            f"choose a scanner with no license gate."
```

to:

```python
            f"\"{license_env}\") so hull renders it into the scan step -- or "
            f"re-run hull:init choosing the \"trufflehog\" scanner, which "
            f"needs no license, no secret, and fewer token permissions."
```

- [ ] **Step 4: Drop the monkeypatch staging from two tests**

These were written against a hypothetical licenseless scanner. Now one exists, so they should exercise the real thing. In `plugins/hull/tests/test_scaffold.py`, replace `test_organization_with_a_licenseless_scanner_is_clear` entirely with:

```python
def test_organization_with_a_licenseless_scanner_is_clear():
    """The blocker is keyed off the SCANNER's license gate, not off the
    owner type alone. Previously staged with a patched registry because no
    licenseless scanner existed; it now exercises the real one."""
    assert check_preconditions({
        "ownerType": "Organization", "scanner": "trufflehog",
    }).blockers == ()
```

And replace `test_advisory_absent_for_a_scanner_with_no_license_gate` entirely with:

```python
def test_fork_pr_advisory_absent_for_a_scanner_with_no_license_gate():
    """The fork-PR advisory is about secrets being withheld from fork runs.
    trufflehog reads no secret, so the caveat does not apply to it."""
    advisories = check_preconditions({
        "ownerType": "User", "scanner": "trufflehog",
    }).advisories
    assert not any("fork" in a.lower() for a in advisories)
```

Note the rename: the new name says *which* advisory is absent, because Task 4 adds a second advisory that **is** present for trufflehog.

Also in `plugins/hull/tests/test_config.py`, replace `test_license_secret_rejected_for_a_scanner_with_no_license_gate` entirely with:

```python
def test_license_secret_rejected_for_a_scanner_with_no_license_gate(tmp_path):
    """A licenseSecret set for a scanner that has nowhere to put it is not
    harmless -- it is a user believing they configured something that is
    silently discarded. Now exercised against the real trufflehog entry
    rather than a patched registry."""
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {
            "scanner": "trufflehog", "licenseSecret": "GITLEAKS_LICENSE",
        }))
    assert "licenseSecret" in str(e.value)
```

- [ ] **Step 5: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1347 passed`.

- [ ] **Step 6: Commit**

```bash
git add plugins/hull/hull/scaffold.py plugins/hull/tests/
git commit -m "feat(hull): the org blocker names trufflehog as a real remedy

The message offered "or choose a scanner with no license gate" when the
registry had exactly one entry, so the remedy named nothing. Three tests
that staged a licenseless scanner with monkeypatch now use the real one.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: The `BASE == HEAD` advisory

**Files:**
- Modify: `plugins/hull/hull/scaffold.py` (`check_preconditions`)
- Test: `plugins/hull/tests/test_scaffold.py`

**Interfaces:**
- Consumes: `REGISTRY["trufflehog"]` from Task 2.

An **advisory**, not a blocker. gitleaks' org gate is systematic — always fails, given those conditions. `BASE == HEAD` is an edge case: the action explicitly handles a branch's first push by setting `BASE=""`, and normal pushes and pull requests have distinct base and head.

- [ ] **Step 1: Write the failing tests**

Append to `plugins/hull/tests/test_scaffold.py`:

```python
def test_trufflehog_carries_a_base_equals_head_advisory():
    """Rare, not systematic -- so it belongs in the channel reported
    ALONGSIDE a successful init, never instead of one."""
    result = check_preconditions({"ownerType": "User", "scanner": "trufflehog"})
    assert result.blockers == ()
    (advisory,) = result.advisories
    assert "BASE" in advisory and "HEAD" in advisory
    assert "exits 1" in advisory


def test_base_equals_head_advisory_is_absent_for_gitleaks():
    """It is a property of trufflehog's action, not of scanning generally."""
    advisories = check_preconditions({"ownerType": "User"}).advisories
    assert not any("BASE" in a for a in advisories)


def test_trufflehog_is_never_blocked_in_an_org_repo():
    """The advisory must not have quietly become a blocker -- that would
    reintroduce exactly the dead end #27 exists to remove."""
    assert check_preconditions({
        "ownerType": "Organization", "scanner": "trufflehog",
    }).blockers == ()
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/hull/tests/test_scaffold.py -k base_equals_head -v`

Expected: FAIL — `ValueError: not enough values to unpack (expected 1, got 0)`.

- [ ] **Step 3: Add the advisory**

In `plugins/hull/hull/scaffold.py`, inside `check_preconditions`, after the existing fork-PR advisory block:

```python
    # Scanner-specific and deliberately an advisory, not a blocker. Unlike
    # the organization gate above -- which fails EVERY run, given those
    # conditions -- this one is an edge case: the action explicitly handles a
    # branch's first push by setting BASE to empty, and an ordinary push or
    # pull request has distinct base and head. Stated anyway so a rare red
    # run is diagnosed rather than mistaken for a hull bug.
    if scanner == "trufflehog":
        advisories.append(
            "The trufflehog action exits 1 with \"BASE and HEAD commits are "
            "the same\" when the range it is asked to scan is empty. hull's "
            "triggers make that rare -- a branch's first push is handled by "
            "the action itself, and an ordinary push or pull request has a "
            "distinct base and head -- but if you do see that message, it is "
            "the action declining to scan nothing, not a finding and not a "
            "hull bug."
        )
```

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`

Expected: `1350 passed`.

- [ ] **Step 5: Commit**

```bash
git add plugins/hull/hull/scaffold.py plugins/hull/tests/test_scaffold.py
git commit -m "feat(hull): advise on trufflehog's BASE==HEAD exit

Advisory rather than blocker: unlike gitleaks' org gate this is an edge
case, not a systematic failure, so it is reported alongside a successful
init rather than instead of one.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Documentation

**Files:**
- Modify: `plugins/hull/skills/init/SKILL.md`
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Update the `scanner` signal in SKILL.md**

Find the `scanner` bullet in section 3 ("Propose the config") and replace it with:

```markdown
- `scanner` — optional; defaults to `"gitleaks"` inside `propose_config`.
  Two are registered, and the choice is real:
  - **`gitleaks`** (default) — the incumbent. Requires a free
    `GITLEAKS_LICENSE` for **organization-owned** repos, public or private
    alike; section 2 refuses to scaffold without one. Needs
    `pull-requests: read` in addition to `contents: read`, because it
    enumerates a pull request's commits through the API.
  - **`trufflehog`** — no license, no secret of any kind, and only
    `contents: read`. AGPL 3.0, and it runs as a CI step against the repo
    rather than being linked into anything the project ships, so its licence
    does not reach the consuming codebase. Reports `verified` and `unknown`
    findings (not `unverified`). This is the answer when section 2 reports
    the organization blocker and the user does not want to obtain a licence.

  Both are pinned to an immutable SHA and both are byte-identity tested.
  Ask the user which they want whenever the organization blocker fires;
  otherwise take the default.
```

- [ ] **Step 2: Update the blocker handling in SKILL.md**

In section 2, in the `blockers` bullet, replace the trailing clause "or pick a scanner with no license gate (there is no such scanner registered today, so in practice it is the license)" with:

```markdown
  — or re-run `hull:init` choosing `"trufflehog"`, which has no license gate
  at all. That second remedy became real in 0.7.0; before it, the registry
  had one entry and the blocker's own message named nothing.
```

- [ ] **Step 3: Update the "not here yet" list in SKILL.md**

Replace the bullet reading "scanners beyond `gitleaks` (`hull.scanners.SCANNER_IDS` has exactly one entry today)" with:

```markdown
- scanners beyond `gitleaks` and `trufflehog` (`hull.scanners.SCANNER_IDS`
  has exactly two entries today)
```

- [ ] **Step 4: Add the changelog entry**

Under `## [Unreleased]` in `CHANGELOG.md`:

```markdown
### Added

- **A secret scanner that needs no license.** `.hull.json`'s `scanner` now
  accepts `"trufflehog"` alongside `"gitleaks"`, pinned to
  `trufflesecurity/trufflehog@27b0417c` (v3.95.9). It needs no license key,
  no secret of any kind, and only `contents: read` -- narrower than gitleaks,
  which additionally needs `pull-requests: read` to enumerate a pull
  request's commits through the API.

  This closes a gap 0.6.0 opened. That release taught `hull:init` to refuse
  rather than scaffold a workflow that could not pass, which was right, but
  it left an organization-owned repo with **no secret scanning at all** --
  and the blocker's own suggested remedy, "choose a scanner with no license
  gate", named nothing, because the registry had one entry. It names
  `trufflehog` now. The default is unchanged: `gitleaks` for everyone who
  is not blocked.

  Reports `verified` and `unknown` findings, not `unverified`. A secret the
  tool cannot verify is exactly the kind it should not stay quiet about;
  reporting *everything* trains a team to ignore the check, which is the
  failure mode the organization blocker exists to prevent.
```

- [ ] **Step 5: Verify and commit**

Run: `python3 -m pytest -q`

Expected: `1350 passed` (documentation only — no test count change).

```bash
git add plugins/hull/skills/init/SKILL.md CHANGELOG.md
git commit -m "docs(hull): document the trufflehog scanner choice

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Final verification

- [ ] `python3 -m pytest -q` → `1350 passed`
- [ ] `git diff main --stat -- plugins/hull/tests/golden/security.yml plugins/hull/tests/golden/security-license.yml` → **empty output**. The single most important check in this plan: gitleaks' rendered output must be untouched.
- [ ] Confirm engine purity held: `grep -nE "^(import|from) (os|subprocess|socket|urllib|requests)" plugins/hull/hull/*.py` → no matches.
- [ ] Open the PR with `keel:finish-work`.
