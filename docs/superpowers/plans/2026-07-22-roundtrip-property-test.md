# Round-trip Property Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give every plugin a property test proving `scaffold.propose_config` output always loads through `config.load_config`, where forgetting to cover a new signal key turns the test red instead of silently passing.

**Architecture:** Each plugin's `tests/test_scaffold.py` gains three things: a `SIGNAL_SPACE` dict of representative sample values per signal key; a coverage guard asserting `set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS`; and a cross-product harness asserting a two-outcome contract per generated signal combo. The harness is copied verbatim into each plugin (self-contained-per-plugin, no shared import). The weaker single-case/subset round-trip tests it subsumes are deleted.

**Tech Stack:** Python 3.9+, pytest, stdlib `itertools` and `json` only. No new dependencies. Engine modules are not touched except one rigging validator fix (Task 2).

## Global Constraints

- **Self-contained per plugin.** No cross-plugin imports; the harness is duplicated into each plugin's test file, not imported from a shared module.
- **Engine purity.** All `SIGNAL_SPACE` samples are pure literals inside test modules. No plugin engine module gains test-support data.
- **Two-outcome contract (verbatim).** For every generated signal combo, `propose_config(combo)` must **either** return a dict that `load_config` accepts, **or** raise `ValueError` — specifically `ValueError`, not `TypeError`/`KeyError`/any other type — before returning. Any third outcome is a test failure.
- **Coverage guard (verbatim).** `assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS`. Compare against `SIGNAL_KEYS` (the `propose_config` domain), never `PRECONDITION_SIGNAL_KEYS`.
- **Enum-sourced samples.** Samples for an enum-valued key are sourced from the registry tuple (`SCANNER_IDS`, `CONTRIBUTIONS`, `REVIEW_POLICIES`, `INTERVALS`, `NODE_PACKAGE_MANAGERS`), never a hardcoded literal list, so a newly added enum value is exercised for free.
- **`ABSENT` sentinel.** A module-level `ABSENT = object()` marks "omit this key entirely." A key that is *required* (has no default in `propose_config`) omits `ABSENT` from its samples deliberately; every optional key includes it.
- **Delete only the named tests.** Each task names the exact tests to delete (pure round-trip cases the property test subsumes). Keep every test that asserts a specific *loaded field value* — the property test only asserts "loads without raising," so value assertions remain non-redundant.
- **No rendered artifact changes.** No golden files change. This is tests-only, plus the Task 2 validator fix.

## The shared harness (identical in every task)

Every task creates this block in the plugin's `tests/test_scaffold.py`. Only the three import lines and the module names change; the two functions below are byte-identical across all six plugins.

```python
import itertools
import json

import pytest

ABSENT = object()


def _candidate_signals(space):
    """Every combination of one sample per signal key. A key whose chosen
    sample is ABSENT is omitted from the produced dict entirely."""
    keys = sorted(space)
    for combo in itertools.product(*(space[k] for k in keys)):
        yield {k: v for k, v in zip(keys, combo) if v is not ABSENT}


def _assert_round_trips(tmp_path, signals, index):
    """The two-outcome contract for one signal combo."""
    try:
        cfg = propose_config(signals)
    except ValueError:
        return  # a deliberate rejection is an allowed outcome
    except Exception as exc:  # noqa: BLE001 - the point is to catch the wrong type
        pytest.fail(
            f"propose_config({signals!r}) raised {type(exc).__name__}, not "
            f"ValueError: {exc}"
        )
    sub = tmp_path / str(index)
    sub.mkdir()
    (sub / CONFIG_NAME).write_text(json.dumps(cfg))
    loaded = load_config(sub)  # must not raise
    assert loaded is not None, (
        f"load_config returned None for {signals!r} -> {cfg!r}"
    )
```

The per-plugin test that drives them:

```python
def test_signal_space_covers_every_signal_key():
    # Loud-omission guard: add a key to SIGNAL_KEYS without declaring its
    # samples here and this fails, rather than the round-trip silently
    # skipping the new key.
    assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS


def test_propose_config_round_trips_over_signal_space(tmp_path):
    for index, signals in enumerate(_candidate_signals(SIGNAL_SPACE)):
        _assert_round_trips(tmp_path, signals, index)
```

---

### Task 1: hull — establish the template on the clean interaction

hull carries historical break #1 (a `licenseSecret` set for a scanner with no licence gate) and needs no production change, so it is the cleanest place to prove the template works.

**Files:**
- Modify: `plugins/hull/tests/test_scaffold.py` (add the harness + `SIGNAL_SPACE`, delete three subsumed tests)

**Interfaces:**
- Consumes: `hull.scaffold.propose_config`, `hull.scaffold.SIGNAL_KEYS`, `hull.config.CONFIG_NAME`, `hull.config.load_config`, `hull.scanners.SCANNER_IDS` (`("gitleaks", "trufflehog")`).
- Produces: the shared harness shape (`_candidate_signals`, `_assert_round_trips`, `ABSENT`, `SIGNAL_SPACE`) that Tasks 2-6 replicate.

- [ ] **Step 1: Add imports and `SIGNAL_SPACE`**

At the top of `plugins/hull/tests/test_scaffold.py`, ensure these imports exist (some are already present — do not duplicate):

```python
from hull import scaffold
from hull.scaffold import propose_config
from hull.config import CONFIG_NAME, load_config
from hull.scanners import SCANNER_IDS
```

Add the harness block (the two functions and `ABSENT` from "The shared harness" above), then:

```python
SIGNAL_SPACE = {
    "name": (ABSENT, "security"),
    "scanner": (ABSENT,) + SCANNER_IDS,       # ABSENT (default gitleaks), gitleaks, trufflehog
    "pushBranches": (ABSENT, ["main", "master"]),
    "licenseSecret": (ABSENT, "GITLEAKS_LICENSE"),
}
```

Why these catch break #1: `licenseSecret="GITLEAKS_LICENSE"` crossed with `scanner="trufflehog"` is the exact break-#1 combo. On current (fixed) code `propose_config` raises `ValueError` → allowed. If the guard is reverted it returns a dict `load_config` rejects → the test fails.

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` exactly as in "The shared harness" above.

- [ ] **Step 3: Run the new tests — expect PASS**

Run: `python -m pytest plugins/hull/tests/test_scaffold.py -k "signal_space or round_trips_over" -v` (from the repo root, so the root `pytest.ini` `pythonpath` applies)
Expected: both PASS.

- [ ] **Step 4: Teeth check (not committed)**

Temporarily edit `plugins/hull/hull/scaffold.py` `_valid_license_secret`: comment out the `if REGISTRY[scanner].license_env is None:` block (lines 118-122). Re-run Step 3's command.
Expected: `test_propose_config_round_trips_over_signal_space` now FAILS (the trufflehog+licenseSecret combo produces a dict `load_config` rejects). This proves the sample has teeth. **Revert the edit** and confirm the tests pass again.

- [ ] **Step 5: Delete the subsumed tests**

Delete these three tests from `plugins/hull/tests/test_scaffold.py` (each is a single-case round-trip the property test now covers):
- `test_propose_config_defaults_round_trip_through_load_config`
- `test_propose_config_explicit_signals_round_trip_through_load_config`
- `test_propose_config_trufflehog_round_trips_through_load_config`

Keep every other test, including the ones asserting specific loaded values (`push_branches == ("master",)`, `license_secret == "GITLEAKS_LICENSE"`).

- [ ] **Step 6: Run hull's full suite — expect PASS**

Run: `python -m pytest plugins/hull/tests -q`
Expected: all pass, no errors.

- [ ] **Step 7: Commit**

```bash
git add plugins/hull/tests/test_scaffold.py
git commit -m "test(hull): round-trip property test over the signal space (#33)"
```

---

### Task 2: rigging — the richest interactions and the fourth latent break

rigging carries historical breaks #2 (unhashable value → `TypeError`) and #3 (`packageManagers` on a stack with no manager). Designing the samples surfaced a **fourth latent break**: `_valid_package_managers` checks `manager_id not in NODE_PACKAGE_MANAGERS` (a dict) with no `isinstance` guard, so `{"node": ["pnpm"]}` raises `TypeError` today. This task's property test fails on current code until that validator is fixed.

**Files:**
- Modify: `plugins/rigging/rigging/scaffold.py:116` (`_valid_package_managers` — add an `isinstance` guard)
- Modify: `plugins/rigging/tests/test_scaffold.py` (add harness + `SIGNAL_SPACE`, delete one subsumed test)

**Interfaces:**
- Consumes: `rigging.scaffold.propose_config`, `rigging.scaffold.SIGNAL_KEYS` (`{"name","stacks","versions","pushBranches","unsupported","packageManagers"}`), `rigging.config.CONFIG_NAME`, `rigging.config.load_config`, `rigging.stacks.NODE_PACKAGE_MANAGERS` (dict; ids `npm, pnpm, yarn1, yarn-berry, bun`).
- Produces: nothing new for later tasks.

- [ ] **Step 1: Add imports, harness, and `SIGNAL_SPACE`**

In `plugins/rigging/tests/test_scaffold.py` ensure these imports (some exist already):

```python
from rigging import scaffold
from rigging.scaffold import propose_config
from rigging.config import CONFIG_NAME, load_config
from rigging.stacks import NODE_PACKAGE_MANAGERS
```

Add the shared harness block, then:

```python
SIGNAL_SPACE = {
    "name": (ABSENT, "ci"),
    "stacks": (("python",), ("node",), ("python", "node")),  # required: no ABSENT
    "versions": (ABSENT, {"python": ["3.12"]}, {"node": ["20"]}),
    "pushBranches": (ABSENT, ["main"]),
    "unsupported": (ABSENT, {"python": "no test runner detected"}),
    "packageManagers": (
        ABSENT,
        {"node": "pnpm"},          # valid iff node is in stacks
        {"python": "npm"},         # python has no manager -> ValueError (break #3)
        {"node": ["pnpm"]},        # unhashable manager id -> must be ValueError (break #4)
    ),
}
```

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` from "The shared harness".

- [ ] **Step 3: Run the round-trip test — expect FAIL on the fourth break**

Run: `python -m pytest plugins/rigging/tests/test_scaffold.py -k round_trips_over -v`
Expected: FAIL. The failure message is `propose_config({'packageManagers': {'node': ['pnpm']}, 'stacks': ...}) raised TypeError, not ValueError: unhashable type: 'list'`. This is break #4 — the contract promises `ValueError` for a bad field, and the validator leaks `TypeError`.

- [ ] **Step 4: Fix `_valid_package_managers`**

In `plugins/rigging/rigging/scaffold.py`, in `_valid_package_managers`, replace the manager-id membership check (currently lines 116-120):

```python
        if manager_id not in NODE_PACKAGE_MANAGERS:
            raise ValueError(
                f"signals['packageManagers'][{stack_id!r}] must be one of "
                f"{', '.join(NODE_PACKAGE_MANAGERS)} (got {manager_id!r})."
            )
```

with an isinstance-first check (same pattern hull's `OWNER_TYPES` guard uses — an unhashable value must raise `ValueError` naming the field, not `TypeError` from a membership test):

```python
        # isinstance first: an unhashable manager_id (a list, a dict) would
        # raise TypeError from the dict-membership test below rather than the
        # ValueError this validator's contract promises for a bad field.
        if not isinstance(manager_id, str) or manager_id not in NODE_PACKAGE_MANAGERS:
            raise ValueError(
                f"signals['packageManagers'][{stack_id!r}] must be one of "
                f"{', '.join(NODE_PACKAGE_MANAGERS)} (got {manager_id!r})."
            )
```

- [ ] **Step 5: Re-run the round-trip test — expect PASS**

Run: `python -m pytest plugins/rigging/tests/test_scaffold.py -k round_trips_over -v`
Expected: PASS. `{"node": ["pnpm"]}` now raises `ValueError`, an allowed outcome.

- [ ] **Step 6: Teeth check for break #3 (not committed)**

Temporarily edit `_valid_package_managers`: comment out the `if stack_id != "node":` block (lines 111-115). Re-run Step 5's command.
Expected: FAIL — `{"python": "npm"}` with `stacks` containing python now returns a dict `load_config` rejects. This proves the break-#3 sample has teeth. **Revert the edit** and confirm PASS.

- [ ] **Step 7: Delete the subsumed test**

Delete `test_every_non_empty_subset_round_trips_through_load_config` from `plugins/rigging/tests/test_scaffold.py`. Keep the value-asserting round-trip tests (`test_explicit_versions_flow_through`, `test_valid_explicit_version_still_round_trips`, `test_package_managers_signal_round_trips_through_load_config`) — they assert specific loaded field values the property test does not.

- [ ] **Step 8: Run rigging's full suite — expect PASS**

Run: `python -m pytest plugins/rigging/tests -q`
Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add plugins/rigging/rigging/scaffold.py plugins/rigging/tests/test_scaffold.py
git commit -m "fix(rigging): reject unhashable packageManager ids with ValueError; add round-trip property test (#33)"
```

Note in the task report that this task fixed a fourth latent instance of the `propose_config`/`load_config` contract break (`TypeError` leak on an unhashable manager id), surfaced by the property test.

---

### Task 3: keel — the topology gate

keel's `propose_config` has a required `has_develop` signal and enum keys (`contributions`, `review_policy`). Its existing round-trip test is a 4-way cross product that hardcodes `["fork","branch","both"]` — the weakness the property test removes by sourcing `CONTRIBUTIONS`/`REVIEW_POLICIES`.

**Files:**
- Modify: `plugins/keel/tests/test_scaffold.py` (add harness + `SIGNAL_SPACE`, delete one subsumed test)

**Interfaces:**
- Consumes: `keel.scaffold.propose_config`, `keel.scaffold.SIGNAL_KEYS` (`{"has_develop","production","integration","contributions","review_policy","require_changelog"}`), `keel.config.CONFIG_NAME`, `keel.config.load_config`, `keel.config.CONTRIBUTIONS` (`("fork","branch","both")`), `keel.config.REVIEW_POLICIES` (`("approval","review","none")`).

- [ ] **Step 1: Add imports, harness, and `SIGNAL_SPACE`**

In `plugins/keel/tests/test_scaffold.py` ensure:

```python
from keel import scaffold
from keel.scaffold import propose_config
from keel.config import CONFIG_NAME, load_config, CONTRIBUTIONS, REVIEW_POLICIES
```

Add the shared harness block, then:

```python
SIGNAL_SPACE = {
    "has_develop": (True, False),                # required: no ABSENT (propose_config does signals["has_develop"])
    "production": (ABSENT, "main"),
    "integration": (ABSENT, "develop"),          # only consumed under gitflow (has_develop True)
    "contributions": (ABSENT,) + CONTRIBUTIONS,
    "review_policy": (ABSENT,) + REVIEW_POLICIES,
    "require_changelog": (ABSENT, True, False),
}
```

`has_develop` deliberately omits `ABSENT`: it is the one required signal, and `propose_config` reads `signals["has_develop"]` directly (a `KeyError`, not a `ValueError`, if absent) — required-signal handling is a separate concern, out of this test's scope.

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` from "The shared harness".

- [ ] **Step 3: Run the new tests — expect PASS**

Run: `python -m pytest plugins/keel/tests/test_scaffold.py -k "signal_space or round_trips_over" -v`
Expected: both PASS.

- [ ] **Step 4: Teeth check (not committed)**

Temporarily edit `plugins/keel/keel/scaffold.py`: in the `review_policy` validation, change `if review_policy not in REVIEW_POLICIES:` to `if False:` (accept anything). Re-run Step 3's command.
Expected: the coverage guard still passes, but note that every `review_policy` sample here is *valid*, so this weakening would not be caught by round-trip alone (an invalid policy would need to reach `load_config`). Instead, add a throwaway invalid sample: temporarily append `"required"` to the `review_policy` samples tuple and re-run.
Expected: FAIL — `propose_config` now returns `{"reviewPolicy": "required"}` which `load_config` rejects. This proves the round-trip catches a weakened enum validator. **Revert both edits** and confirm PASS.

- [ ] **Step 5: Delete the subsumed test**

Delete `test_every_proposed_config_round_trips_through_load_config` from `plugins/keel/tests/test_scaffold.py`. Keep the negative tests (`bad_signals` parametrized rejections) and any value-asserting tests (`test_integration_signal_defaults_to_develop`).

- [ ] **Step 6: Run keel's full suite — expect PASS**

Run: `python -m pytest plugins/keel/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add plugins/keel/tests/test_scaffold.py
git commit -m "test(keel): registry-sourced round-trip property test over the signal space (#33)"
```

---

### Task 4: bosun — intervals keyed by ecosystem

**Files:**
- Modify: `plugins/bosun/tests/test_scaffold.py` (add harness + `SIGNAL_SPACE`, delete two subsumed tests)

**Interfaces:**
- Consumes: `bosun.scaffold.propose_config`, `bosun.scaffold.SIGNAL_KEYS` (`{"ecosystems","intervals","targetBranch"}`), `bosun.config.CONFIG_NAME`, `bosun.config.load_config`, `bosun.ecosystems.INTERVALS` (`("daily","weekly","monthly","quarterly","semiannually","yearly")`).

- [ ] **Step 1: Add imports, harness, and `SIGNAL_SPACE`**

In `plugins/bosun/tests/test_scaffold.py` ensure:

```python
from bosun import scaffold
from bosun.scaffold import propose_config
from bosun.config import CONFIG_NAME, load_config
from bosun.ecosystems import INTERVALS
```

Add the shared harness block, then:

```python
SIGNAL_SPACE = {
    "ecosystems": ((), ("python",), ("python", "node")),   # githubActions is always added by propose_config
    "intervals": (
        ABSENT,
        {"python": INTERVALS[0]},          # valid ecosystem + valid interval (registry-sourced)
        {"githubActions": INTERVALS[-1]},  # the always-on ecosystem, a different valid interval
        {"bogus": INTERVALS[0]},           # unknown ecosystem id -> ValueError
        {"python": "often"},               # unknown interval -> ValueError
    ),
    "targetBranch": (ABSENT, "develop"),
}
```

`intervals` values are nested inside a per-ecosystem dict, so the top-level coverage guard does not enforce that every `INTERVALS` value is exercised — the valid samples are sourced from `INTERVALS` so that a renamed/removed interval breaks the sample rather than silently drifting, but exhaustive interval coverage is representative, not guaranteed. Note this in the report.

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` from "The shared harness".

- [ ] **Step 3: Run the new tests — expect PASS**

Run: `python -m pytest plugins/bosun/tests/test_scaffold.py -k "signal_space or round_trips_over" -v`
Expected: both PASS.

- [ ] **Step 4: Teeth check (not committed)**

Temporarily edit `plugins/bosun/bosun/scaffold.py`: in the interval-value validation, change `if interval not in ecosystems.INTERVALS:` to `if False:`. Re-run Step 3's command.
Expected: FAIL — `{"python": "often"}` now returns a dict with an invalid interval that `load_config` rejects. This proves the sample has teeth. **Revert the edit** and confirm PASS.

- [ ] **Step 5: Delete the subsumed tests**

Delete `test_no_detected_ecosystems_round_trips_through_load_config` and `test_every_subset_round_trips_through_load_config` from `plugins/bosun/tests/test_scaffold.py`. Keep value-asserting tests (e.g. `test_target_branch_signal_is_emitted_and_round_trips`).

- [ ] **Step 6: Run bosun's full suite — expect PASS**

Run: `python -m pytest plugins/bosun/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add plugins/bosun/tests/test_scaffold.py
git commit -m "test(bosun): round-trip property test over the signal space (#33)"
```

---

### Task 5: stow — the smallest surface

stow has a single signal key (`stacks`). The property test is small but still valuable: it locks the contract before stow grows a second key.

**Files:**
- Modify: `plugins/stow/tests/test_scaffold.py` (add harness + `SIGNAL_SPACE`, delete one subsumed test)

**Interfaces:**
- Consumes: `stow.scaffold.propose_config`, `stow.scaffold.SIGNAL_KEYS` (`{"stacks"}`), `stow.config.CONFIG_NAME`, `stow.config.load_config`, `stow.stacks.STACK_IDS` (`("python","node")`).

Note: `stow.config.load_config` returns `None` when `.stow.json` is absent. The harness always writes the file first, so a `None` return here is a real failure — the `assert loaded is not None` in `_assert_round_trips` is meaningful for stow.

- [ ] **Step 1: Add imports, harness, and `SIGNAL_SPACE`**

In `plugins/stow/tests/test_scaffold.py` ensure:

```python
from stow import scaffold
from stow.scaffold import propose_config
from stow.config import CONFIG_NAME, load_config
```

Add the shared harness block, then:

```python
SIGNAL_SPACE = {
    "stacks": ((), ("python",), ("node",), ("python", "node")),  # empty is base-only, allowed
}
```

`stacks` is required (`propose_config` calls `_reject_unknown_signals` then reads `signals.get("stacks")` and rejects a non-list), but the empty tuple is a *valid* base-only proposal, so it is a sample rather than `ABSENT`.

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` from "The shared harness".

- [ ] **Step 3: Run the new tests — expect PASS**

Run: `python -m pytest plugins/stow/tests/test_scaffold.py -k "signal_space or round_trips_over" -v`
Expected: both PASS.

- [ ] **Step 4: Teeth check (not committed)**

Temporarily edit `plugins/stow/stow/scaffold.py`: change the stack-id check `if stack_id not in STACK_IDS:` to `if False:`. Re-run Step 3 after temporarily adding `("bogus",)` to the `stacks` samples.
Expected: FAIL — a `bogus` stack now produces a dict `load_config` rejects. **Revert both edits** and confirm PASS.

- [ ] **Step 5: Delete the subsumed test**

Delete `test_every_subset_round_trips_through_load_config` from `plugins/stow/tests/test_scaffold.py`. Keep the tests asserting `desired_sections` / file-classification behaviour and the `load_config`-returns-None-when-absent test.

- [ ] **Step 6: Run stow's full suite — expect PASS**

Run: `python -m pytest plugins/stow/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add plugins/stow/tests/test_scaffold.py
git commit -m "test(stow): round-trip property test over the signal space (#33)"
```

---

### Task 6: ballast — nested override dicts

ballast's `configs` signal is a nested dict of per-stack overrides (`testPaths`, `pythonPath`, `importMode`, `addOpts`). The coverage guard operates at signal-key granularity (`stacks`, `configs`), so the nested override keys are covered by representative samples rather than by the guard — state this in the report.

**Files:**
- Modify: `plugins/ballast/tests/test_scaffold.py` (add harness + `SIGNAL_SPACE`, delete one subsumed test)

**Interfaces:**
- Consumes: `ballast.scaffold.propose_config`, `ballast.scaffold.SIGNAL_KEYS` (`{"stacks","configs"}`), `ballast.scaffold.IMPORT_MODES` (`("importlib","prepend","append")`), `ballast.config.CONFIG_NAME`, `ballast.config.load_config`, `ballast.stacks.STACK_IDS` (`("python",)`).

- [ ] **Step 1: Add imports, harness, and `SIGNAL_SPACE`**

In `plugins/ballast/tests/test_scaffold.py` ensure:

```python
from ballast import scaffold
from ballast.scaffold import propose_config, IMPORT_MODES
from ballast.config import CONFIG_NAME, load_config
```

Add the shared harness block, then:

```python
SIGNAL_SPACE = {
    "stacks": (("python",),),   # required; python is the only registered stack
    "configs": (
        ABSENT,
        {"python": {"testPaths": ["tests"]}},
        {"python": {"pythonPath": []}},              # empty pythonPath is allowed
        {"python": {"importMode": IMPORT_MODES[0]}}, # a valid mode, sourced from the registry
        {"python": {"addOpts": ["-q"]}},
        {"python": {"testPaths": []}},               # empty testPaths -> ValueError
        {"python": {"importMode": "bogus"}},         # invalid mode -> ValueError
        {"python": ["not-a-dict"]},                  # override not a dict -> ValueError
    ),
}
```

- [ ] **Step 2: Add the two driver tests**

Add `test_signal_space_covers_every_signal_key` and `test_propose_config_round_trips_over_signal_space` from "The shared harness".

- [ ] **Step 3: Run the new tests — expect PASS**

Run: `python -m pytest plugins/ballast/tests/test_scaffold.py -k "signal_space or round_trips_over" -v`
Expected: both PASS.

- [ ] **Step 4: Teeth check (not committed)**

Temporarily edit `plugins/ballast/ballast/scaffold.py`: change the import-mode check `if import_mode not in IMPORT_MODES:` to `if False:`. Re-run Step 3's command.
Expected: FAIL — `{"python": {"importMode": "bogus"}}` now returns a dict `load_config` rejects. **Revert the edit** and confirm PASS.

- [ ] **Step 5: Delete the subsumed test**

Delete `test_every_non_empty_subset_round_trips_through_load_config` from `plugins/ballast/tests/test_scaffold.py`. Keep value-asserting tests, including `test_empty_python_path_list_is_allowed_and_round_trips`.

- [ ] **Step 6: Run ballast's full suite — expect PASS**

Run: `python -m pytest plugins/ballast/tests -q`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add plugins/ballast/tests/test_scaffold.py
git commit -m "test(ballast): round-trip property test over the signal space (#33)"
```

---

### Task 7: whole-suite green and changelog

**Files:**
- Modify: `CHANGELOG.md` (add an Unreleased entry)

- [ ] **Step 1: Run the entire repo test suite**

Run: `python -m pytest -q` from the repo root (or the repo's documented full-suite command).
Expected: all pass, with net test count changed by the removed subset tests plus the added property tests.

- [ ] **Step 2: Add the changelog entry**

Under `## [Unreleased]` in `CHANGELOG.md`, add:

```markdown
### Added
- Every plugin now has a round-trip property test asserting `propose_config`
  output always loads through `load_config` over a declared signal space, with
  a coverage guard that fails when a new signal key is added without samples
  (#33).

### Fixed
- rigging: an unhashable `packageManagers` value now raises `ValueError` naming
  the field instead of leaking `TypeError` (#33).
```

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): round-trip property tests and the rigging TypeError fix (#33)"
```
