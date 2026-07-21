---
name: init
description: Use to configure the pytest runner in a repository via ballast - detects the repo's stack, proposes a .ballast.json, and renders a pytest.ini, never overwriting an existing one.
---

# Initialising ballast in a repo

This scaffolds the **test-runner config** layer only: a `.ballast.json` and
one rendered `pytest.ini`. It does not run the tests (that's `rigging`'s
job, in CI), manage baseline files (`stow`), or touch the git lifecycle —
branch protection, PR/issue templates, CODEOWNERS, the changelog gate
(`keel`'s job).

Increment 1 supports exactly one stack: **python** via **pytest**. Node
test-runner configuration is not implemented yet.

## 1. Confirm the repo root and check for an existing config

Run `cd "$(git rev-parse --show-toplevel)"` (or equivalent) first, and stay
there for every command below. This plugin's one-liners use `Path('.')` and
bare relative paths (`.ballast.json`, `pytest.ini`) throughout — those are
only correct when the shell's cwd is the repo root, which cannot be assumed
of the agent's starting cwd.

Before proposing anything, check whether `.ballast.json` already exists and,
if so, whether it loads:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from ballast.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `ballast`
package sits at its top level.)

This has three possible outcomes, and they are not the same thing:

- **No `.ballast.json`** (prints `None`) — proceed with the normal
  fresh-scaffold flow: sections 2-3 below.
- **`.ballast.json` exists and loads** (prints a `Config(...)`) — skip
  straight to section 4. That file is the durable record of this repo's
  pytest configuration; use it as-is. Do NOT run section 3's
  `propose_config` in this case — there is nothing to propose, the config on
  disk already is the answer.
- **`.ballast.json` exists but raises `ConfigError`** — it's present but
  invalid (unparseable JSON, wrong shape, an unknown stack id, a bad
  `importMode`, or a path/flag value outside its allowed charset). Leave it
  alone, tell the user ballast is misconfigured (show the `ConfigError`
  message verbatim — it already names the field and the bad value), and stop
  here. Do not detect stacks, do not propose a config, and do not write
  `pytest.ini` — there is no valid on-disk config to render from, and
  overwriting `.ballast.json` isn't on the table either; increment 1 has no
  repair or merge logic for it.

## 2. Detect the stack

*(Fresh-scaffold flow only — you're here because section 1 found no
`.ballast.json`.)*

Call `detect_stacks`, which checks for python's marker files at repo root
(`pyproject.toml`/`setup.py`/`setup.cfg`/`requirements.txt`) and returns the
matching ids, in registry order:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from ballast.detect import detect_stacks; from pathlib import Path; print(detect_stacks(Path('.')))"

If this returns an empty tuple, **do not guess**. Tell the user plainly:
ballast only configures pytest (python) in increment 1, and node
test-runner config is not supported yet. If the repo genuinely has no
python marker file at its root (e.g. python code lives in a subdirectory
without one of the standard markers), stop and ask rather than fabricating
a config — unless the user explicitly opts in and confirms `python` applies
anyway, in which case you may proceed to section 3 with
`signals = {"stacks": ["python"]}` regardless of what `detect_stacks`
returned. Increment 1 detects and supports only this one stack.

## 3. Propose the config

*(Fresh-scaffold flow only.)*

Build a signals dict from what you detected (or the user confirmed) and ask
only for what you cannot infer:

- `stacks` — `["python"]`. Required, non-empty; increment 1 only has this
  one registry id.
- `configs` — optional, `{"python": {...}}` with camelCase overrides
  matching `.ballast.json`'s own keys:
  - `testPaths` — defaults to `["tests"]` if omitted. Ask if the repo is a
    monorepo with multiple test directories (e.g.
    `["plugins/keel/tests", "plugins/rigging/tests"]`).
  - `pythonPath` — defaults to `[]` (omitted from the rendered `pytest.ini`
    entirely) if omitted. Ask if packages under test live outside the repo
    root and need to be importable (e.g. `["plugins/keel"]`).
  - `importMode` — one of `importlib`/`prepend`/`append`, defaults to
    `importlib` if omitted. Only ask if the user has a reason to want
    something else.
  - `addOpts` — defaults to `[]` if omitted. Ask if the user wants flags
    like `-q` or `--strict-markers` baked into every run.

Call `ballast.scaffold.propose_config(signals)` to get the `.ballast.json`
dict, e.g.:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from ballast.scaffold import propose_config
    signals = {'stacks': ['python']}
    print(json.dumps(propose_config(signals), indent=2))
    "

Show the result to the user in full and confirm. If they want changes (add
`testPaths`, set `pythonPath`, change `importMode`, add `addOpts`), adjust
the signals dict and re-show — don't write anything until they've approved
what's on screen.

`propose_config` raises `ValueError` — naming the offending field — on an
unknown stack id, a non-list `stacks`/`configs` value, a `testPaths`/
`pythonPath` entry with whitespace, a leading `/`, or a `..` segment, an
`importMode` outside the allowed set, or an `addOpts` token containing
whitespace. Surface that message to the user directly rather than
reinterpreting it; it already names the field and the bad value.

Once confirmed, exclusive-create `.ballast.json` (`open(path, "x")`, which
raises rather than overwrites if the path exists — this backstops the
no-clobber guarantee even against a loose reading of these instructions: a
file that somehow came into existence since section 1's check can never be
silently clobbered):

    python3 -c "
    import json
    cfg = {'stacks': {'python': {}}}
    open('.ballast.json', 'x').write(json.dumps(cfg, indent=2) + '\n')
    "

(substitute the actual confirmed dict from above for the `cfg` literal.)

Continue to section 4 to render `pytest.ini`.

## 4. Render `pytest.ini` (no-clobber)

*(Reached from section 1's already-loads branch, or from section 3 just
after `.ballast.json` is written.)*

Check whether `pytest.ini` is already there:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from pathlib import Path
    from ballast.scaffold import CONFIG_FILES, classify_files
    print(json.dumps(classify_files(Path('.'), CONFIG_FILES)))
    "

`CONFIG_FILES` is `[".ballast.json", "pytest.ini"]`, so this reports both;
`.ballast.json` should classify as `present` by this point either way
(fresh-written above, or already on disk per section 1).

- If `pytest.ini` classifies as **absent**, render it from the config that
  is now on disk (the `.ballast.json` you just wrote, or the pre-existing
  one) and exclusive-create it — not `open(path, "w")` — so a file that
  appeared between the classify check and the write can never be silently
  clobbered:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from pathlib import Path; from ballast.config import load_config; from ballast.render import render; text = render(load_config(Path('.'))); open('pytest.ini', 'x').write(text)"

- If `pytest.ini` classifies as **present**, this is a **no-clobber stop**,
  not a fresh-scaffold continuation: ballast is a no-clobber plugin like
  `rigging:init`/`keel:init`, not a managed-merge plugin like `stow`. Do
  NOT overwrite it and do NOT attempt to migrate or reconcile it with
  what ballast would render — increment 1 has no merge logic for a foreign
  `pytest.ini`. Tell the user plainly that a `pytest.ini` already exists,
  ballast won't touch it in increment 1, and if they want ballast managing
  it they need to remove or rename the existing file (or adopt it by hand)
  and re-run `ballast:init`.

Continue to section 5 to verify and report either way.

## 5. Verify and report

Prove what's on disk is sound:

- Reload the config — must print a `Config(...)`, not raise:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from ballast.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

- Compare the render against what's on disk. If you wrote `pytest.ini` in
  section 4, this must match exactly — the render engine is pure and
  deterministic, so the file you wrote and a fresh render from the same
  config are byte-identical by construction:

      python3 -c "
      import sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from ballast.config import load_config
      from ballast.render import render
      expected = render(load_config(Path('.')))
      actual = Path('pytest.ini').read_text()
      assert expected == actual, 'pytest.ini does not match what ballast would render'
      print('ok: pytest.ini matches render(load_config(.))')
      "

  If `pytest.ini` pre-existed and section 4 left it alone instead, run the
  same comparison as an informational check, not a pass/fail gate — report
  whether the foreign file happens to match what ballast would have
  rendered, or diverges from it (either is fine; it's the user's file).

- Run `python3 -m pytest --collect-only` and capture **both** stdout and
  stderr (e.g. `python3 -m pytest --collect-only 2>&1`) — the warning this
  step checks for prints to the warnings summary, which pytest writes
  regardless of exit code, so don't discard stderr or you'll miss it.
  **This is the step that matters most to get right**, and its result is
  not just "exit code zero or not" — grep the captured output for the
  literal string `No files were found in testpaths`. That string's
  presence, not the exit code, is what tells you which of three outcomes
  you're in:

  - **(a) Tests were collected and the warning is absent.** The runner is
    correctly configured and collecting the intended suite. Report
    success — this is what shipyard's own repo hits: every directory
    listed in its `.ballast.json` `testPaths` exists, a non-zero number of
    tests is collected, and no warning is printed. Compare against the
    config in front of you, not against a remembered test count: the
    number changes with every commit, so a hardcoded figure here would
    make this check report a false failure.

  - **(b) The warning `No files were found in testpaths; ... Searching
    recursively from the current directory instead.` is present** —
    regardless of exit code (pytest 8.x prints this and then falls back to
    scanning the whole tree and exits 0, so a passing collection is *not*
    proof of correct configuration by itself). This means the configured
    `testPaths` in `.ballast.json` point at a path with no tests, pytest
    is silently ignoring them, and it is instead scanning the entire repo
    — the exact whole-tree-scan failure mode `ballast:init` exists to
    prevent. Do **not** report success. Flag this to the user as a
    misconfiguration: the `testPaths` value(s) need fixing (a typo'd path,
    a directory that doesn't exist yet, etc.), not an empty-suite warning
    to shrug off.

  - **(c) Zero tests collected (exit 5) and the warning is absent.** The
    configured `testPaths` are real but currently contain no test files.
    This is a *correctly configured* runner reporting a genuinely *empty*
    suite, not a ballast failure. Warn the user plainly and explicitly:
    ballast has configured the pytest runner correctly, but there is no
    test for it to run yet, and an empty suite is a red CI the moment
    `rigging`'s workflow tries to run it. Writing a starter test is the
    user's to do now (or a later ballast increment's to scaffold) — it is
    out of scope for `ballast:init` itself. Do not treat pytest's exit 5
    here as a smoke-test failure; treat it as the exact condition this
    outcome exists to catch and surface.

Report: what you created (`.ballast.json`, `pytest.ini`) or skipped (and
why — a pre-existing `.ballast.json` used as-is, or a pre-existing
`pytest.ini` left untouched), the confirmed/loaded config, the render
comparison result, and which of the three `--collect-only` outcomes above
you hit (including surfacing the misconfiguration in case (b), or the
zero-tests warning in case (c), as applicable).

Point the user at:

- `rigging:init` — the sibling layer that actually *runs* whatever ballast
  configures, in CI (`.rigging.json`, the GitHub Actions workflow).
- `stow:init` — baseline repo hygiene (`.stow.json`, managed `.gitignore`
  sections).
- `keel:init` — the git-lifecycle layer (`.keel.json`, changelog, PR/issue
  templates, CODEOWNERS, the changelog CI gate).

Note what's deliberately **not** here yet — later ballast increments, not
gaps in this one:

- stacks beyond `python` (no node/jest/vitest test-runner config)
- migrating or reconciling a pre-existing, foreign `pytest.ini`
- scaffolding a starter test when the suite is empty
- an interactive edit path for an existing `.ballast.json` (increment 1's
  only ways to change it are hand-editing the file and re-running
  `ballast:init` to pick up the new `pytest.ini`, or deleting `pytest.ini`
  first if you want it re-rendered)
- other python test runners (unittest, tox, nox) or coverage thresholds
