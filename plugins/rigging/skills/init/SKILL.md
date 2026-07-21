---
name: init
description: Use to set up CI in a repository via rigging - detects the repo's stack, proposes a .rigging.json, and scaffolds an injection-safe GitHub Actions workflow, detecting sensible defaults and never overwriting existing files.
---

# Initialising rigging in a repo

This scaffolds the **CI pipeline** layer only: a `.rigging.json` config and
one rendered GitHub Actions workflow. It does not touch branch protection,
PR/issue templates, CODEOWNERS, or the changelog gate — that's `keel`'s job,
not rigging's.

## 1. Confirm the repo root

`git rev-parse --show-toplevel`. Do everything below relative to that path.

## 2. Detect the stack

Call `detect_stacks`, which checks for each registered stack's marker files
at repo root (today: `python` — `pyproject.toml`/`setup.py`/`setup.cfg`/
`requirements.txt`; `node` — `package.json`) and returns the matching ids, in
registry order:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from rigging.detect import detect_stacks; from pathlib import Path; print(detect_stacks(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `rigging`
package sits at its top level.)

If this returns an empty tuple, **do not guess** — ask the user which
stack(s) apply, from rigging's currently supported set (`python`, `node`).
Increment 1 detects and supports only these two; if the repo is neither, say
so plainly and stop rather than proposing a config rigging can't back.

## 3. Propose the config

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

## 4. Write the absent artifacts

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

(swap `'ci'` for the confirmed name.)

For each **absent** file, write it:

- `.rigging.json` — the confirmed dict, pretty-printed (`json.dumps(cfg,
  indent=2)` plus a trailing newline).
- `.github/workflows/<name>.yml` — `render(build_plan(load_config(Path('.'))))`.
  This always reads the config back off disk rather than reusing the
  in-memory dict, so it's correct whether `.rigging.json` was just written
  above or already existed:

      mkdir -p .github/workflows
      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from pathlib import Path; from rigging.config import load_config; from rigging.plan import build_plan; from rigging.render import render; print(render(build_plan(load_config(Path('.')))), end='')" > .github/workflows/<name>.yml

For each **present** file, do NOT overwrite. Tell the user it exists and
offer **keep theirs** — that's the only option; increment 1 has no merge
logic for either file (unlike keel's `CHANGELOG.md`/`.keel.json` merge). If
`.rigging.json` is present but doesn't load (`ConfigError` from
`rigging.config.load_config`), say so, leave it alone, and skip the workflow
write entirely — there's no valid config on disk to render from, and
overwriting it isn't on the table either.

## 5. Verify and report

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

  Skip this step (and say so in the report) if `.rigging.json` was present
  but invalid and the user chose to leave it alone in section 4.

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

Point the user at `keel:init` / `keel:protect` for the sibling layer rigging
doesn't own: branch protection, PR/issue templates, CODEOWNERS, and the
changelog gate. rigging's half is the workflow file itself, and it's authored
injection-safely by construction — not by a linter catching mistakes after
the fact, but because the renderer has no code path that can emit anything
other than a whitelisted `matrix.<var>` reference.
