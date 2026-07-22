# Round-trip property test: propose_config output must load through load_config

**Issue:** #33 · **Date:** 2026-07-22 · **Status:** approved, not yet implemented

## Why

Every plugin's `scaffold.propose_config(signals)` promises: *valid signals in ->
a dict guaranteed to load via `config.load_config` (enforced by test)*. The
parenthetical is a lie of omission. It **is** enforced by a test — one that
hardcodes one or two signal shapes, so it covers only the keys someone
remembered to add.

This contract broke three times in a single day, in three plugins, each caught
by review or by hand and never by a test, each "fixed" by adding a case for the
specific key rather than testing the property:

1. **hull (#27, Critical).** `propose_config({"scanner":"trufflehog",
   "licenseSecret":"X"})` produced a dict `load_config` rejects — a
   `licenseSecret` set for a scanner with no licence gate. Unreachable until the
   first licenceless scanner was registered.
2. **rigging (#26 inc 1, Task 3).** A validator did `value not in REGISTRY`
   before an `isinstance` check, so an unhashable value raised `TypeError`
   where the contract promised `ValueError`/`ConfigError`.
3. **rigging (#26 inc 1, final review).** `propose_config` emitted
   `stacks.python.packageManager`, which `load_config` rejects because python
   has no manager concept. The worst of the three: `rigging:init` writes
   `.rigging.json` **before** rendering, so the failure lands after the file
   exists — the "present but invalid" state the skill says has no repair path.

The unifying shape: `propose_config`'s signal domain and `load_config`'s config
domain are validated independently, and the two drift apart at exactly the
*interaction* points — an optional key paired with a target it is invalid for.

## What we are actually building

The issue's stated ideal — *"adding a config key requires no edit to this
test"* — is literally unachievable. `propose_config` needs a **representative
value** to exercise a new signal (a valid `licenseSecret` string, a `pnpm`),
and no test can conjure a meaningful sample for a key it has never heard of.

So the property we build is the achievable and stronger one:

> Adding a config key requires **no edit to the test's logic**, and forgetting
> to declare the key's representative samples turns the test **red** rather than
> silently skipping it.

This converts the failure mode from *silent omission* (today — the test passes,
so it looks covered) to *loud omission* (a red test until the new key's samples
are declared). Remembering is replaced by enforcement.

Rejected alternative — **introspection**: derive the signal space by
introspecting config dataclasses and registries so truly zero edits are needed.
Rejected because the signal shape (`propose_config` input) deliberately differs
from the config shape (`load_config` input) — and that disagreement *is* the
bug. Introspecting one to test the other is circular and would go green on
precisely the drift it exists to catch.

## Architecture

One property test per plugin, living in that plugin's `tests/test_scaffold.py`.
No shared cross-plugin module: the suite's standing rule is
self-contained-per-plugin (each plugin already carries its own
`_all_non_empty_subsets` helper). The test's *shape* is documented once here as
a template and copied into each plugin's test file. The DRY cost is real and
subordinate to self-containment.

### Where the sample declaration lives

`SIGNAL_SPACE` lives in the **test module**, not in `scaffold.py`. Engine
modules stay pure data->data mappers; and some samples are *deliberately
invalid combinations* (a `licenseSecret` paired with `trufflehog`) whose only
purpose is to exercise the test — that is test data, not production data. This
also matches where keel and rigging already keep their parametrize lists.

### The three parts of each plugin's test

**1. `SIGNAL_SPACE`** — a dict mapping every signal key to a tuple of
representative sample *fragments*. Conventions:

- An `ABSENT` sentinel is always one of the samples (the key omitted entirely),
  because "key present vs absent" is itself a dimension that has hidden bugs
  (the whole point of omitting a key is to get `load_config`'s default, and that
  path must round-trip too).
- Enum-valued keys source their samples from the registry
  (`SCANNER_IDS`, `CONTRIBUTIONS`, `REVIEW_POLICIES`, `INTERVALS`,
  `ECOSYSTEM_IDS`, `STACK_IDS`, package-manager ids) rather than hardcoding a
  literal list — so a newly added enum value is exercised for free.
- Sample counts are bounded to roughly 2-3 per key (`ABSENT` + one or two
  representative values) to keep the cross product bounded. These are
  microsecond pure calls, so full cross product is used; no pairwise reduction.

**2. Coverage guard** — the anti-omission teeth:

```python
assert set(SIGNAL_SPACE) == scaffold.SIGNAL_KEYS
```

Add a key to `SIGNAL_KEYS` without declaring its samples, and this assertion
fails. (hull additionally has `PRECONDITION_SIGNAL_KEYS` for
`check_preconditions`; the guard compares against `SIGNAL_KEYS`, the domain
`propose_config` actually accepts. `ownerType` is deliberately excluded from
`SIGNAL_KEYS` and belongs to a separate `check_preconditions` property, out of
scope here.)

**3. Cross-product harness** — the product of all sample fragments, each combo
asserted against the **two-outcome contract**:

> `propose_config(combo)` must **either** return a dict that `load_config`
> accepts, **or** raise `ValueError` — specifically `ValueError`, not
> `TypeError` or `KeyError` — before returning. Any third outcome is a failure.

`load_config` reads from disk, so the harness writes the returned dict to the
plugin's config filename in a `tmp_path` and loads it, matching how the existing
round-trip tests already work.

### Why the contract catches all three breaks

| Break | Symptom under the harness |
|---|---|
| #1 hull `licenseSecret`+trufflehog | `propose_config` returns a dict `load_config` rejects -> fail |
| #2 rigging unhashable value | raises `TypeError`, not `ValueError` -> fail (requires an unhashable sample, see below) |
| #3 rigging `packageManagers` on python | returns a dict `load_config` rejects -> fail |

### The load-bearing constraint: interaction samples

A cross product that never pairs an interaction key with an *invalid target it
is actually applied to* runs green and proves nothing. So, for every interaction
key, `SIGNAL_SPACE` **must** include a sample that is invalid for at least one
target the cross product will pair it with against a *present* stack/scanner:

- **hull:** `licenseSecret` present is crossed with *both* scanners, so the
  `trufflehog + licenseSecret` combo (break #1) is generated.
- **rigging:** the `packageManagers` samples include one naming a stack with no
  manager concept (python) while that stack is in the `stacks` subset, so the
  break-#3 combo is generated. A separate sample supplies a **list** (unhashable
  / wrong-type) value to force the break-#2 path.
- **keel:** `integration` is crossed with both topologies (`has_develop`
  true/false); `require_changelog` and every enum are exercised.
- **bosun:** `intervals` samples include a valid ecosystem id and an interval
  value; the harness crosses them against the detected-ecosystems dimension.

This constraint is the spec's central risk. It is not self-checking from the
happy path — a plugin author could declare only valid samples and get a green
test that catches nothing. The meta-verification below exists precisely to
prove each plugin's `SIGNAL_SPACE` has teeth.

## Relationship to existing tests

The new property test *subsumes* each plugin's
`test_every_*_subset_round_trips_through_load_config`, which varied only *which
stacks/ecosystems were present, all at defaults*. Those are deleted where fully
subsumed. Tests that assert plugin-specific loaded **values** (e.g.
`loaded.stacks[id].versions == default_versions`, `loaded.target_branch ==
"develop"`) are kept — the property test asserts only "loads without raising,"
not specific field values, so those remain meaningful and non-redundant.

keel's `test_every_proposed_config_round_trips_through_load_config` (a 4-way
cross product hardcoding `["fork","branch","both"]`) is replaced by the
registry-sourced property test.

## Meta-verification (proves the harness has teeth)

Run during implementation, **not committed** — these are how we know each
plugin's test actually catches something rather than passing vacuously:

1. **Reintroduce each of the three historical breaks** in turn (revert the
   specific guard) and confirm the new property test goes red for that plugin.
   If it stays green, that plugin's `SIGNAL_SPACE` is missing the interaction
   sample and must be fixed before the task is done.
2. **Add a dummy key to one plugin's `SIGNAL_KEYS`** and confirm the coverage
   guard fails. This proves the anti-omission mechanism works.

For the plugins with no recorded historical break (stow, ballast, bosun), the
equivalent teeth-check is: temporarily weaken one interaction validator in
`propose_config` (make it accept a value `load_config` rejects) and confirm the
property test catches it.

## Testing

- One `test_propose_config_round_trips_over_signal_space` (or equivalently named)
  per plugin: rigging, hull, keel, bosun, stow, ballast.
- One coverage-guard assertion per plugin (may be its own tiny test or the first
  lines of the property test).
- The full suite must stay green after the weaker subset tests are removed; the
  net test count changes but no *behaviour* coverage is lost (the property test
  covers a superset of the deleted cases).

## What is NOT changing

- **Engine purity.** All samples are pure literals in test modules; no plugin
  engine module gains test-support data.
- **The `propose_config` / `load_config` contracts themselves.** This is
  additive coverage plus deletion of the weaker tests it subsumes. No production
  validator changes — unless meta-verification surfaces a *fourth* latent break,
  which would be fixed and noted.
- **Any rendered artifact.** No golden changes; this touches tests only.
- **`check_preconditions`.** hull's `ownerType` precondition property is a
  separate concern and out of scope.

## Scope

Six plugins carry `propose_config(signals) -> config dict`: rigging, hull, keel,
bosun, stow, ballast. keel was flagged "check before assuming" in the issue — it
was checked and is in the identical shape, with the strongest-yet-still-weak
existing test. All six are covered. Each is an independently reviewable unit;
the plan sequences them one per task.
