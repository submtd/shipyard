---
name: init
description: Use to set up CI in a repository via rigging - detects the repo's stack, proposes a .rigging.json, and scaffolds an injection-safe GitHub Actions workflow, detecting sensible defaults and never overwriting existing files.
---

# Initialising rigging in a repo

This scaffolds the **CI pipeline** layer only: a `.rigging.json` config and
one rendered GitHub Actions workflow. It does not touch branch protection,
PR/issue templates, CODEOWNERS, or the changelog gate — that's `keel`'s job,
not rigging's.

## 1. Confirm the repo root and check for an existing config

`git rev-parse --show-toplevel`. Do everything below relative to that path.

Before proposing anything, check whether `.rigging.json` already exists and,
if so, whether it loads:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from rigging.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `rigging`
package sits at its top level.)

This has three possible outcomes, and they are not the same thing:

- **No `.rigging.json`** (prints `None`) — proceed with the normal
  fresh-scaffold flow: sections 2-4 below.
- **`.rigging.json` exists and loads** (prints a `Config(...)`) — skip
  straight to section 5, already-configured mode. Do NOT run section 3's
  `propose_config` in this case — it defaults `name` to `"ci"` regardless of
  what's already on disk, and letting that default leak into this flow is
  exactly the bug this section exists to prevent (a workflow's filename and
  its internal `name:` disagreeing with each other).
- **`.rigging.json` exists but raises `ConfigError`** — it's present but
  invalid (unparseable JSON, wrong types, an unknown stack id, or a value
  outside an allowed charset). Leave it alone, tell the user rigging is
  misconfigured (show the `ConfigError` message verbatim — it already names
  the field and the bad value), and stop here. Do not detect stacks, do not
  propose a config, and do not write a workflow — there is no valid on-disk
  config to render from, and overwriting `.rigging.json` isn't on the table
  either; increment 1 has no repair or merge logic for it.

## 2. Detect the stack

*(Fresh-scaffold flow only — you're here because section 1 found no
`.rigging.json`.)*

Call `detect_stacks`, which checks for each registered stack's marker files
at repo root (today: `python` — `pyproject.toml`/`setup.py`/`setup.cfg`/
`requirements.txt`; `node` — `package.json`) and returns the matching ids, in
registry order:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from rigging.detect import detect_stacks; from pathlib import Path; print(detect_stacks(Path('.')))"

If this returns an empty tuple, **do not guess** — ask the user which
stack(s) apply, from rigging's currently supported set (`python`, `node`).
Increment 1 detects and supports only these two; if the repo is neither, say
so plainly and stop rather than proposing a config rigging can't back.

## 3. Propose the config

*(Fresh-scaffold flow only.)*

Build a signals dict from what you detected and ask the user only for what
you cannot infer:

- `stacks` — the detected (or user-supplied) ids, as a list. Required,
  non-empty.
- `name` — optional; defaults to `"ci"` inside `propose_config`. This becomes
  both the workflow's `name:` and the filename `.github/workflows/<name>.yml`,
  so ask if the repo already has a convention here (e.g. it wants `test.yml`
  instead of `ci.yml`).
- `versions` — optional, `{stack_id: [version, ...]}`. A stack without an
  entry gets `{}` in the emitted config, so `config.load_config` fills in the
  registry default later (`python` → `3.12`, `node` → `20`). Ask if the user
  wants something else, e.g. a matrix of `["3.10", "3.11", "3.12"]`.

Call `rigging.scaffold.propose_config(signals)` to get the `.rigging.json`
dict, e.g.:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from rigging.scaffold import propose_config
    signals = {'stacks': ['python'], 'name': 'ci'}
    print(json.dumps(propose_config(signals), indent=2))
    "

Show the result to the user in full and confirm. If they want changes (drop
a stack, add versions, rename), adjust the signals dict and re-show — don't
write anything until they've approved what's on screen.

`propose_config` raises `ValueError` — naming the offending field — on an
unknown stack id, a `name` outside its allowed charset, or a version string
outside its allowed charset (this is also what keeps a hostile version like
`"${{ github.token }}"` from ever reaching the renderer). Surface that
message to the user directly rather than reinterpreting it; it already names
the field and the bad value.

## 4. Write the absent artifacts (fresh-scaffold flow)

Call `classify_files(root, CI_FILES(name))` — this tells you,
deterministically, which of the two candidate paths are absent (safe to
write) and which are already present (must not be touched):

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from pathlib import Path
    from rigging.scaffold import CI_FILES, classify_files
    print(json.dumps(classify_files(Path('.'), CI_FILES('ci'))))
    "

(swap `'ci'` for the confirmed name.) Section 1 already established
`.rigging.json` is absent, so it should classify as absent here too; if the
workflow path is somehow already present anyway (e.g. hand-authored, with no
`.rigging.json` to match it), treat it like any other present file below.

For each **absent** file, write it. Use exclusive-create (`open(path, "x")`,
which raises rather than overwrites if the path exists) for both writes
below, not `open(path, "w")` — this backstops the classify-gate no-clobber
guarantee even against a loose reading of these instructions: a file that
somehow came into existence between the classify check and the write can
never be silently clobbered.

- `.rigging.json` — the confirmed dict, pretty-printed (`json.dumps(cfg,
  indent=2)` plus a trailing newline):

      python3 -c "
      import json
      cfg = {'name': 'ci', 'stacks': {'python': {}}}
      open('.rigging.json', 'x').write(json.dumps(cfg, indent=2) + '\n')
      "

  (substitute the actual confirmed dict from section 3 for the `cfg` literal
  above — the `python`/`ci` values here are illustrative, matching section
  3's example.)

- `.github/workflows/<name>.yml` — `render(build_plan(load_config(Path('.'))))`.
  This reads the config back off disk — which, in this flow, is the
  `.rigging.json` you just wrote immediately above, so its `name` matches
  the filename you're about to write to by construction:

      mkdir -p .github/workflows
      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from pathlib import Path; from rigging.config import load_config; from rigging.plan import build_plan; from rigging.render import render; text = render(build_plan(load_config(Path('.')))); open('.github/workflows/<name>.yml', 'x').write(text)"

For each **present** file, do NOT overwrite. Tell the user it exists and
offer **keep theirs** — that's the only option; increment 1 has no merge
logic for either file (unlike keel's `CHANGELOG.md`/`.keel.json` merge).

Continue to section 6 to verify and report.

## 5. Already-configured mode (`.rigging.json` present and loads)

Section 1 sent you here because a valid `.rigging.json` already exists. Do
NOT re-propose a fresh default config — the existing file on disk is the
source of truth for `name` and `stacks` from here on. You already have it
from section 1's `load_config` call (the printed `Config(name=..., stacks=...)`);
call `<existing_name>` its `name` field below.

Classify against that name, not a freshly-proposed one:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from pathlib import Path
    from rigging.scaffold import CI_FILES, classify_files
    print(json.dumps(classify_files(Path('.'), CI_FILES('<existing_name>'))))
    "

(swap `<existing_name>` for the real value.) `.rigging.json` will classify as
**present** — leave it untouched, full stop; do not write to it in this
flow.

If `.github/workflows/<existing_name>.yml` classifies as **absent**, write it
exactly as section 4's workflow step does — exclusive-create, so it can never
clobber a file that appeared after the classify check — reading the config
back off disk (the same pre-existing `.rigging.json`, unchanged), so the
filename you write to and the workflow's internal `name:` always agree:

    mkdir -p .github/workflows
    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from pathlib import Path; from rigging.config import load_config; from rigging.plan import build_plan; from rigging.render import render; text = render(build_plan(load_config(Path('.')))); open('.github/workflows/<existing_name>.yml', 'x').write(text)"

If `.github/workflows/<existing_name>.yml` classifies as **present** too,
there's nothing left to write — tell the user rigging is already fully
configured for this repo and stop.

If the user wants different stacks, a different name, or different versions,
tell them to edit `.rigging.json` by hand and re-run `rigging:init` —
increment 1 has no interactive edit path for an existing config, only
fresh-scaffold and fill-in-the-missing-workflow.

Continue to section 6 to verify and report.

## 6. Verify and report

*(Reached from section 4 or section 5 — section 1's invalid-config branch
stops before ever getting here.)*

Prove what you wrote works:

- Reload the config — must print a `Config(...)`, not raise:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from rigging.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

- Re-render from that config and confirm no attacker-reachable expression
  survived into the workflow — rigging's core injection-safety property.
  Every `- run:` step body (via `render.iter_run_blocks`) must be free of
  `${{`; the only `${{ ... }}` forms rigging ever emits are whitelisted
  `${{ matrix.<var> }}` references inside `with:` blocks, never inside a
  `run:` step and never `github.*`:

      python3 -c "
      import sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from rigging.config import load_config
      from rigging.plan import build_plan
      from rigging.render import render, iter_run_blocks
      text = render(build_plan(load_config(Path('.'))))
      bad = [b for b in iter_run_blocks(text) if '\${{' in b]
      assert not bad, bad
      print('ok: no \${{ in any run block')
      "

Report: what you created, what you skipped (and why), the confirmed config,
and the verification result.

Note what's deliberately **not** here yet — these are later rigging
increments, not gaps in this one:

- stacks beyond `python` and `node`
- lint, build, and type-check jobs (today's job per stack only installs and
  runs tests)
- dependency caching
- configurable triggers (today's workflow is always `on: [push,
  pull_request]`)
- hooks (e.g. warning when someone edits `.github/workflows/<name>.yml` by
  hand instead of through rigging)

Two per-stack limitations worth surfacing to a maintainer explicitly, since
they can make a freshly-scaffolded workflow red for reasons that have
nothing to do with the project's own tests:

- **node**: the generated job runs `npm ci` then `npm test`. `npm ci`
  requires a committed `package-lock.json` (it fails outright without one,
  unlike `npm install`), and `npm test` requires a `test` script defined in
  `package.json`. Neither is scaffolded or checked by rigging today — if
  either is missing, tell the user to add it.
- **python**: the generated job installs `requirements.txt` if present
  (`if [ -f requirements.txt ]; then pip install -r requirements.txt; fi`),
  matching GitHub's official python starter workflow. It does not yet
  handle poetry, pdm, or an editable `pyproject.toml` install — a project
  using one of those needs to either add a `requirements.txt` or wait for a
  later rigging increment.

Point the user at `keel:init` / `keel:protect` for the sibling layer rigging
doesn't own: branch protection, PR/issue templates, CODEOWNERS, and the
changelog gate. rigging's half is the workflow file itself, and it's authored
injection-safely by construction — not by a linter catching mistakes after
the fact, but because the renderer has no code path that can emit anything
other than a whitelisted `matrix.<var>` reference.
