# Roster Closure + Skill-Integrity Guard + ballast addOpts Denylist — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the Shipyard core roster at six plugins (fathom will not be built), and ship the two real findings the fathom evaluation produced: a repo-wide skill-integrity guard and a `ballast` `addOpts` denylist for flags that are harmful in a committed `pytest.ini`.

**Architecture:** No new plugin, no new package, no new tests directory. One new test module in an existing tests directory (`plugins/keel/tests/`), one validation addition to `ballast`'s existing config loader, and documentation edits. Because no new tests directory ships, the 5-edit ballast lockstep is **not** incurred.

**Tech Stack:** Python 3.9+ stdlib only, pytest.

## Global Constraints

- **Python 3.9+**: `from __future__ import annotations` wherever `X | None` appears in annotations; **no `match` statement**.
- **stdlib only** at runtime. No new dependencies.
- **These three files MUST stay byte-identical** — verify with `git diff --stat` printing nothing for each: `pytest.ini`, `.ballast.json`, `.claude-plugin/marketplace.json`. A change to any of them means the decision was misread.
- **These paths MUST NOT be created**: `plugins/fathom/**`, `.fathom.json`, `.vscode/**`, any new file under `.github/workflows/`.
- **No `plugins/*/tests/__init__.py`** (repo-wide guard forbids it).
- Charset/enum validators use `.fullmatch()`, never `.match()`.
- Baseline suite before this plan: **917 passed**. Every task ends with the full suite green.
- The changelog gate must pass: `python3 scripts/check_changelog.py main "$(git branch --show-current)"` → exit 0.
- Branch: `feature/close-fathom-roster`. The decision record `docs/superpowers/specs/2026-07-21-fathom-decision.md` is already committed — treat it as the spec.

---

### Task 1: Repo-wide skill-integrity guard

**Files:**
- Create: `plugins/keel/tests/test_skill_integrity.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: nothing other tasks consume.

**Why keel hosts it:** keel owns 11 of the suite's 16 skills and none are validated today; the suite's precedent is that repo-wide guards live inside a plugin's tests dir (cf. the `plugins/*/tests/__init__.py` guard). `plugins/keel/tests` is already in `.ballast.json` testPaths — which is exactly why this costs no lockstep.

**Verified baseline (do not hardcode these as expectations, only as anti-vacuity floors):** 16 SKILL.md files, 61 cross-plugin references, all resolving; 0 frontmatter deviations; `plugins/*` dirs == marketplace names.

- [ ] **Step 1: Write the negative unit tests FIRST.**

The guard passes on the clean repo from the moment it exists, so negative tests on a pure parser are the **only** way to prove it can go red. Write a module-level parser and test it against malformed input.

```python
"""Repo-wide integrity guard for every plugins/*/skills/*/SKILL.md.

Hosted in keel because keel owns 11 of the suite's 16 skills and no plugin
validates skills it does not own; the suite's precedent is that repo-wide
guards live inside a plugin's tests directory (cf. the guard forbidding
plugins/*/tests/__init__.py). Filesystem reads only, no subprocess.

This is a ROT guard: everything it checks passes today. Its value is
coverage -- 11 of 16 SKILL.md files have no frontmatter validation at all,
and nothing checks that cross-plugin `plugin:skill` references resolve or
that the plugins/* directory set and marketplace.json agree.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


class FrontmatterError(Exception):
    """Raised when a SKILL.md frontmatter block is malformed."""


def parse_frontmatter(text):
    """Parse a SKILL.md leading `---` block into a dict of top-level keys.

    Pure: takes text, returns a dict, raises FrontmatterError. Kept
    separate from the filesystem so it can be tested against malformed
    input -- the repo is clean, so this is the only way to prove the
    guard can fail.
    """
    if not text.startswith("---\n"):
        raise FrontmatterError("frontmatter must open with '---' on line 1")
    end = text.find("\n---", 3)
    if end == -1:
        raise FrontmatterError("frontmatter block is not closed")
    block = text[4:end]
    fields = {}
    for line in block.split("\n"):
        if not line.strip() or line.startswith((" ", "\t")):
            continue
        if ":" not in line:
            raise FrontmatterError(f"frontmatter line is not a key: {line!r}")
        key, value = line.split(":", 1)
        fields[key.strip()] = value.strip()
    return fields
```

Negative tests proving each failure mode:

```python
def test_parser_rejects_missing_opening_delimiter():
    with pytest.raises(FrontmatterError):
        parse_frontmatter("name: init\ndescription: x\n")


def test_parser_rejects_unclosed_block():
    with pytest.raises(FrontmatterError):
        parse_frontmatter("---\nname: init\ndescription: x\n")


def test_parser_rejects_a_non_key_line():
    with pytest.raises(FrontmatterError):
        parse_frontmatter("---\nname: init\ngarbage\n---\n")


def test_parser_extracts_exactly_the_top_level_keys():
    fields = parse_frontmatter("---\nname: init\ndescription: does a thing\n---\nbody\n")
    assert fields == {"name": "init", "description": "does a thing"}
```

- [ ] **Step 2: Run the negative tests to verify they pass and genuinely exercise the parser**

Run: `python3 -m pytest plugins/keel/tests/test_skill_integrity.py -v`
Expected: 4 passed.

Then prove non-vacuity: temporarily change `if not text.startswith("---\n")` to `if False`, re-run, confirm `test_parser_rejects_missing_opening_delimiter` FAILS, then revert. Report this in your report.

- [ ] **Step 3: Add the discovery helpers and the repo-wide guards**

**Derive plugin names from the directory listing — never hardcode them**, or the guard rots the moment the roster changes.

```python
def _plugin_names():
    return sorted(d.name for d in (REPO / "plugins").iterdir() if d.is_dir())


def _skill_files():
    return sorted(REPO.glob("plugins/*/skills/*/SKILL.md"))


SKILL_FILES = _skill_files()
REFERENCE_RE = re.compile(r"\b(" + "|".join(_plugin_names()) + r"):([a-z0-9][a-z0-9-]*)\b")


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_frontmatter_is_exactly_name_and_description(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert set(fields) == {"name", "description"}, (
        f"{skill_path} frontmatter keys must be exactly name+description"
    )


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_name_matches_its_directory(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert fields["name"] == skill_path.parts[-2]


@pytest.mark.parametrize("skill_path", SKILL_FILES, ids=lambda p: f"{p.parts[-4]}:{p.parts[-2]}")
def test_every_skill_description_is_non_empty(skill_path):
    fields = parse_frontmatter(skill_path.read_text())
    assert fields["description"].strip()
```

- [ ] **Step 4: Add the cross-reference and marketplace guards**

Scope the reference check to `plugin:skill` matches **only**. Do NOT add a "repo paths mentioned in skills must exist" check — keel's init SKILL.md legitimately names `docs/CODEOWNERS` and `docs/PULL_REQUEST_TEMPLATE.md`, which are **target-repo** probe locations that do not exist here. That variant is a false-positive generator.

```python
def test_every_cross_plugin_skill_reference_resolves():
    unresolved = []
    for skill_path in SKILL_FILES:
        for match in REFERENCE_RE.finditer(skill_path.read_text()):
            plugin, skill = match.group(1), match.group(2)
            if not (REPO / "plugins" / plugin / "skills" / skill / "SKILL.md").exists():
                unresolved.append(f"{skill_path}: {match.group(0)}")
    assert not unresolved, f"unresolved skill references: {unresolved}"


def test_plugins_dir_and_marketplace_agree():
    marketplace = json.loads((REPO / ".claude-plugin/marketplace.json").read_text())
    listed = {p["name"] for p in marketplace["plugins"]}
    on_disk = set(_plugin_names())
    assert on_disk == listed, (
        f"plugin dirs not in marketplace: {on_disk - listed}; "
        f"marketplace entries with no dir: {listed - on_disk}"
    )
```

- [ ] **Step 5: Add the anti-vacuity guard**

A broken glob or regex must not make the whole module pass silently.

```python
def test_guard_scans_a_nontrivial_corpus():
    assert len(SKILL_FILES) >= 16, f"expected >=16 SKILL.md files, found {len(SKILL_FILES)}"
    total_refs = sum(
        len(REFERENCE_RE.findall(p.read_text())) for p in SKILL_FILES
    )
    assert total_refs >= 1, "expected at least one cross-plugin skill reference"
```

- [ ] **Step 6: Run and confirm the corpus size**

Run: `python3 -m pytest plugins/keel/tests/test_skill_integrity.py -q`
Expected: all pass. Print the discovered counts once during development (`len(SKILL_FILES)` and `total_refs`) to confirm **16 skills and 61 references** are actually being scanned — if either is 0, the glob or regex is broken. Report both numbers.

- [ ] **Step 7: Run the full suite**

Run: `python3 -m pytest -q`
Expected: 917 + the new tests, all passing.

- [ ] **Step 8: Verify nothing forbidden changed**

```bash
git diff --stat -- pytest.ini .ballast.json .claude-plugin/marketplace.json
test ! -e plugins/fathom && test ! -e .fathom.json && test ! -e .vscode && echo "no forbidden paths"
```
Expected: the `git diff --stat` prints NOTHING; the second line prints `no forbidden paths`.

- [ ] **Step 9: Commit**

```bash
git add plugins/keel/tests/test_skill_integrity.py
git commit -m "test: repo-wide skill-integrity guard (frontmatter, name==dir, refs, marketplace)"
```

---

### Task 2: ballast addOpts denylist for CI-hostile flags

**Files:**
- Modify: `plugins/ballast/ballast/config.py` (the `_valid_add_opts` function, ~line 96)
- Modify: `plugins/ballast/ballast/__init__.py` (version bump)
- Modify: `plugins/ballast/.claude-plugin/plugin.json` (version bump)
- Modify: `plugins/ballast/tests/test_smoke.py:16`, `plugins/ballast/tests/test_stacks.py:9` (both assert `__version__ == "0.1.0"`)
- Test: `plugins/ballast/tests/test_config.py`

**Interfaces:**
- Consumes: `ballast.config.ConfigError`, `_valid_add_opts`, `FLAG_RE` (all existing).
- Produces: a new module-level `DENIED_ADD_OPTS` frozenset in `ballast/config.py`.

**The defect:** `FLAG_RE = re.compile(r"\S+")` accepts any non-whitespace token, so `--pdb` can be written into `.ballast.json` `addOpts` and rendered into the **committed** `pytest.ini`, hanging CI on the first failure.

- [ ] **Step 1: Write the failing tests**

Add to `plugins/ballast/tests/test_config.py` (match the file's existing helper style for writing a temp `.ballast.json` — read the file first and reuse its existing `write`/tmp_path helper rather than inventing one):

```python
@pytest.mark.parametrize(
    "flag",
    ["--pdb", "--trace", "--pdbcls", "--lf", "--last-failed",
     "--ff", "--failed-first", "--sw", "--stepwise", "--stepwise-skip"],
)
def test_add_opts_rejects_ci_hostile_flags(tmp_path, flag):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": [flag]}}})
    with pytest.raises(ConfigError) as excinfo:
        load_config(root)
    assert flag in str(excinfo.value)


def test_add_opts_rejects_ci_hostile_flag_with_a_value(tmp_path):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": ["--pdbcls=IPython.terminal.debugger:TerminalPdb"]}}})
    with pytest.raises(ConfigError) as excinfo:
        load_config(root)
    assert "--pdbcls" in str(excinfo.value)


@pytest.mark.parametrize("flag", ["-s", "--capture=no", "-x", "--exitfirst", "-q", "--strict-markers"])
def test_add_opts_still_accepts_defensible_flags(tmp_path, flag):
    root = write(tmp_path, {"stacks": {"python": {"addOpts": [flag]}}})
    config = load_config(root)
    assert flag in config.stacks["python"].add_opts
```

- [ ] **Step 2: Run to verify they fail**

Run: `python3 -m pytest plugins/ballast/tests/test_config.py -k "ci_hostile or defensible" -v`
Expected: the `ci_hostile` tests FAIL (no ConfigError raised — the flags are currently accepted); the `defensible` tests PASS already.

- [ ] **Step 3: Implement the denylist**

In `plugins/ballast/ballast/config.py`, add above `FLAG_RE` (keep the existing `FLAG_RE` and its comment intact):

```python
# Flags that are actively harmful in a COMMITTED pytest.ini, which every
# run in every environment inherits. Two families:
#   - interactive debuggers block on stdin and hang CI until it times out;
#   - cache-dependent selection makes WHICH TESTS RUN depend on a previous
#     local run's .pytest_cache, silently narrowing the suite.
# Deliberately NOT denied: -s/--capture=no and -x/--exitfirst are
# defensible standing preferences, not hostile.
DENIED_ADD_OPTS = frozenset({
    "--pdb", "--trace", "--pdbcls",
    "--lf", "--last-failed", "--ff", "--failed-first",
    "--sw", "--stepwise", "--stepwise-skip",
})
```

Then in `_valid_add_opts`, after the existing `FLAG_RE.fullmatch` check and before `opts.append(entry)`:

```python
        flag = entry.split("=", 1)[0]
        if flag in DENIED_ADD_OPTS:
            raise ConfigError(
                f"{CONFIG_NAME}: 'stacks.{stack_id}.addOpts' must not contain "
                f"{flag!r} -- it is unsafe in a committed pytest.ini "
                f"(interactive debuggers hang CI; cache-dependent selection "
                f"silently narrows the suite)."
            )
```

- [ ] **Step 4: Run to verify they pass**

Run: `python3 -m pytest plugins/ballast/tests/test_config.py -v`
Expected: all pass, including the pre-existing tests.

- [ ] **Step 5: Bump ballast to 0.2.0**

This changes the config contract (rejects configs previously accepted), so it is a minor bump, not a patch.

- `plugins/ballast/ballast/__init__.py`: `__version__ = "0.2.0"`
- `plugins/ballast/.claude-plugin/plugin.json`: `"version": "0.2.0"`
- `plugins/ballast/tests/test_smoke.py:16` and `plugins/ballast/tests/test_stacks.py:9`: update both `== "0.1.0"` assertions to `"0.2.0"`.

`.claude-plugin/marketplace.json` has **no** version field — do not touch it.

- [ ] **Step 6: Run the full suite and verify the dogfood is unaffected**

Run: `python3 -m pytest -q`
Expected: all green.

Then confirm shipyard's own config is unaffected (its `addOpts` is `[]`):
```bash
git diff --stat -- pytest.ini .ballast.json .claude-plugin/marketplace.json
```
Expected: prints NOTHING.

- [ ] **Step 7: Commit**

```bash
git add plugins/ballast/
git commit -m "feat(ballast): reject CI-hostile addOpts flags; bump to 0.2.0"
```

---

### Task 3: Close the roster in README and CHANGELOG

**Files:**
- Modify: `README.md` (the roster paragraph, currently lines ~315-318)
- Modify: `CHANGELOG.md` (`## [Unreleased]` → `### Added`)

**Interfaces:** Consumes the decision record at `docs/superpowers/specs/2026-07-21-fathom-decision.md` (already committed) — link to it.

- [ ] **Step 1: Replace the README roster paragraph**

Current text (verify before editing; change **nothing else** in README):

```
With `bosun` shipped, the six-plugin core suite — keel, rigging, stow,
ballast, hull, and bosun — is complete. The only remaining sibling on the
roadmap is `fathom` (debugging/profiling), and it is optional: nothing in
the core suite depends on it.
```

Replace with:

```
With `bosun` shipped, the six-plugin core suite — keel, rigging, stow,
ballast, hull, and bosun — is complete, and the roster is closed at six.
`fathom` (debugging/profiling) was evaluated and deliberately not built:
every candidate artifact was either already owned by another plugin or one
this repo would not genuinely keep, and Shipyard does not ship an artifact
just to give a dogfood test a target. The reasoning, the five candidates,
and the single condition that would reopen it are recorded in
[the fathom decision record](docs/superpowers/specs/2026-07-21-fathom-decision.md).
```

- [ ] **Step 2: Add the CHANGELOG entry**

At the TOP of the `## [Unreleased]` → `### Added` list, matching the file's existing `--` (ASCII double-hyphen) convention:

```markdown
- Repo-wide skill-integrity guard covering every `plugins/*/skills/*/SKILL.md`:
  frontmatter shape, `name` matching its directory, non-empty description,
  cross-plugin `plugin:skill` reference resolution, and `plugins/*`
  vs. `marketplace.json` set equality. 11 of 16 skills had no frontmatter
  validation before this.
```

And add a `### Changed` section (create it if absent, after `### Added`) with:

```markdown
- `ballast` 0.2.0 rejects `addOpts` flags that are unsafe in a committed
  `pytest.ini` -- interactive debuggers (`--pdb`, `--trace`, `--pdbcls`) hang
  CI, and cache-dependent selection (`--lf`, `--ff`, `--sw` and aliases)
  silently narrows the suite. `-s` and `-x` remain allowed.
- The Shipyard core roster is closed at six plugins. `fathom`
  (debugging/profiling) was evaluated and deliberately not built -- see
  `docs/superpowers/specs/2026-07-21-fathom-decision.md`.
```

- [ ] **Step 3: Verify the changelog gate**

Run: `python3 scripts/check_changelog.py main "$(git branch --show-current)"; echo "exit=$?"`
Expected: `exit=0`.

- [ ] **Step 4: Run the full suite**

Run: `python3 -m pytest -q`
Expected: all green.

- [ ] **Step 5: Final forbidden-path and byte-identity verification**

```bash
git diff --stat -- pytest.ini .ballast.json .claude-plugin/marketplace.json
test ! -e plugins/fathom && test ! -e .fathom.json && test ! -e .vscode && echo "no forbidden paths"
```
Expected: `git diff --stat` prints NOTHING; second line prints `no forbidden paths`.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md
git commit -m "docs: close the core roster at six; record the ballast addOpts denylist"
```

---

## Self-Review

**Spec coverage.** Decision record → already committed (the spec itself). README roster closure → T3. Skill-integrity guard (frontmatter shape, name==dir, non-empty description, reference resolution, marketplace set equality, anti-vacuity, negative parser tests) → T1. ballast addOpts denylist (both families, `-s`/`-x` allowed, `=`-form handled) → T2. CHANGELOG → T3. No ballast lockstep, no marketplace entry, no `plugins/fathom` → Global Constraints + verified in T1 Step 8 and T3 Step 5.

**Placeholder scan.** No TBD/TODO. Every code block is complete and runnable. The one instruction to read before writing (T2 Step 1, reusing `test_config.py`'s existing tmp-config helper) is deliberate — the helper's exact name must match the file, and inventing a second one would duplicate it.

**Type consistency.** `parse_frontmatter`/`FrontmatterError`/`SKILL_FILES`/`REFERENCE_RE`/`_plugin_names` (T1) are internal to one module. `DENIED_ADD_OPTS`/`ConfigError`/`_valid_add_opts`/`CONFIG_NAME`/`FLAG_RE` (T2) match `ballast/config.py`'s existing names. Version `0.2.0` is applied consistently across `__init__.py`, `plugin.json`, and both asserting tests (T2 Step 5).
