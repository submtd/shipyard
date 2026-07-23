# Kill the version-literal release tax (#29) — Implementation Plan

> Small, mechanical, fully specified by issue #29. Executed inline (not subagent-driven).

**Goal:** A version bump edits only the 12 files that genuinely carry the version (6 `plugin.json` + 6 `__init__.py`). No test file names the version; the suite verifies the version *property* (exists, semver, all six agree) instead of restating the value.

**Principle:** `assert bosun.__version__ == "0.7.0"` cannot catch anything — it fails on every legitimate release and passes on every wrong-but-consistent one. Replace value-restatement with property checks, and add the one real guarantee nothing enforces today: lockstep (all six equal).

## Global Constraints
- No test file contains a version literal after this change.
- Self-contained per plugin: each smoke test keeps its own small semver check (no cross-plugin import); the cross-plugin lockstep check lives in `tests/test_marketplace.py`, which already owns repo-level guards.
- Semver shape for this suite is `MAJOR.MINOR.PATCH` → `^\d+\.\d+\.\d+$`.
- Behaviour-only refactor of tests; no engine/config/rendered-artifact change.

## Changes

### 1. Five per-plugin `test_smoke.py` (hull, bosun, stow, rigging, ballast)
Each has, in `test_package_imports`, `assert <pkg>.__version__ == "0.7.0"`, and in `test_plugin_json_parses_and_names_<pkg>`, `assert plugin["version"] == "0.7.0"`. Replace both with property checks. Add `import re` where absent (rigging's smoke has no `re` import).

- `test_package_imports`:
  ```python
      import <pkg>
      assert isinstance(<pkg>.__version__, str)
      assert re.fullmatch(r"\d+\.\d+\.\d+", <pkg>.__version__), <pkg>.__version__
  ```
- plugin.json test: replace `assert plugin["version"] == "0.7.0"` with
  ```python
      assert re.fullmatch(r"\d+\.\d+\.\d+", plugin["version"]), plugin["version"]
  ```
  (Agreement between plugin.json and `__init__.py` is already owned by
  `test_marketplace.py::test_plugin_json_version_matches_the_package_version`, so the
  local check only needs to assert the value is a well-formed version.)

### 2. keel `test_smoke.py`
Remove the `VERSION = "0.7.0"` module constant. Change the two `== VERSION` assertions (in `test_package_imports` and `test_plugin_json_parses_and_names_keel`) to the same property checks as above. keel's smoke already imports nothing for regex — add `import re`.

### 3. Three `test_stacks.py` version tests (rigging, ballast, stow)
`test_rigging_version` / `test_ballast_version` / `test_stow_version` each assert `x.__version__ == "0.7.0"` — an exact duplicate of the smoke check. **Delete these three functions.** (The property is covered once, in each plugin's smoke test.)

### 4. `tests/test_marketplace.py` — the one new guarantee
Add a lockstep test that names no version:
```python
def test_all_plugins_report_the_same_version():
    """Lockstep is a stated property of this suite (see the changelog preamble)
    and nothing enforced it. Reads every plugin's __init__ version and asserts
    they are all equal, naming no literal -- so it passes at every consistent
    release and fails only on a genuine desync."""
    import re

    versions = {}
    for name in PLUGIN_DIRS:
        init = (REPO / "plugins" / name / name / "__init__.py").read_text()
        match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', init)
        assert match, f"{name}: no __version__ in {name}/__init__.py"
        versions[name] = match.group(1)
    distinct = set(versions.values())
    assert len(distinct) == 1, f"plugins are not in lockstep: {versions}"
```

## Verification
1. Full suite green after the edits.
2. `grep -rn '\d\.\d\.\d' plugins/*/tests/ tests/` returns no version literal in any test.
3. **Teeth check (not committed):** temporarily change one plugin's `__init__.py` version to a different value → confirm `test_all_plugins_report_the_same_version` AND `test_plugin_json_version_matches_the_package_version` go red → revert.
4. **Release-proof check (not committed):** temporarily bump ALL 12 carriers consistently to a fake version (e.g. 9.9.9) → confirm the whole suite stays green with zero test edits → revert. This is the property the change exists to deliver.
