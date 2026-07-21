---
name: init
description: Use to set up baseline files in a repository via stow - detects the repo's stack, proposes a .stow.json, and manages a .gitignore section per opted-in stack, merging with any hand-written entries instead of overwriting them.
---

# Initialising stow in a repo

This scaffolds the **baseline files** layer only: a `.stow.json` config and
the managed sections of `.gitignore` it describes. It does not touch CI
(that's `rigging`'s job) or the git lifecycle — branch protection, PR/issue
templates, CODEOWNERS, the changelog gate (that's `keel`'s job).

## 1. Confirm the repo root and check for an existing config

`git rev-parse --show-toplevel`. Do everything below relative to that path.

Before proposing anything, check whether `.stow.json` already exists and, if
so, whether it loads:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from stow.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `stow` package
sits at its top level.)

This has three possible outcomes, and they are not the same thing:

- **No `.stow.json`** (prints `None`) — proceed with the normal
  fresh-scaffold flow: sections 2-3 below.
- **`.stow.json` exists and loads** (prints a `Config(...)`) — skip straight
  to section 4. That file is the durable record of which stacks this repo
  has opted into; use it as-is. Do NOT run section 3's `propose_config` in
  this case — there is nothing to propose, the config on disk already is the
  answer.
- **`.stow.json` exists but raises `ConfigError`** — it's present but invalid
  (unparseable JSON, wrong shape, an unknown stack id, or a non-object stack
  value). Leave it alone, tell the user stow is misconfigured (show the
  `ConfigError` message verbatim — it already names the field and the bad
  value), and stop here. Do not detect stacks, do not propose a config, and
  do not touch `.gitignore` — increment 1 has no repair logic for an invalid
  `.stow.json`.

## 2. Detect the stack

*(Fresh-scaffold flow only — you're here because section 1 found no
`.stow.json`.)*

Call `detect_stacks`, which checks for each registered stack's marker files
at repo root (today: `python` — `pyproject.toml`/`setup.py`/`setup.cfg`/
`requirements.txt`; `node` — `package.json`) and returns the matching ids, in
registry order:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from stow.detect import detect_stacks; from pathlib import Path; print(detect_stacks(Path('.')))"

`base` (`.DS_Store`, `Thumbs.db`) is always applied regardless of what's
detected — it is not a signal the user chooses, and it must never appear in
the `stacks` list you pass to `propose_config` (that raises `ValueError`; see
section 3).

If `detect_stacks` returns an empty tuple, **do not guess** — ask the user
which of `python`/`node` apply, or confirm base-only (no language stack) is
correct. Increment 1 detects and supports only these two registry stacks.

## 3. Propose the config

*(Fresh-scaffold flow only.)*

Build a signals dict from what you detected (or the user confirmed):

    {"stacks": ["python"]}   # or [], for base-only, or ["python", "node"], etc.

Call `stow.scaffold.propose_config(signals)` to get the `.stow.json` dict:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from stow.scaffold import propose_config
    signals = {'stacks': ['python']}
    print(json.dumps(propose_config(signals), indent=2))
    "

Show the result to the user in full and confirm. If they want changes (add
or drop a stack), adjust the signals dict and re-show — don't write anything
until they've approved what's on screen.

`propose_config` raises `ValueError` — naming the offending field — on an
unknown stack id (including `"base"`, which is never a member of `stacks`;
it's applied unconditionally, not opted into) or a non-list `stacks` value.
Surface that message to the user directly rather than reinterpreting it.

Once confirmed, exclusive-create `.stow.json` (`open(path, "x")`, which
raises rather than overwrites if the path exists — this is the one file
increment 1 treats as no-clobber, not a managed merge):

    python3 -c "
    import json
    cfg = {'stacks': {'python': {}}}
    open('.stow.json', 'x').write(json.dumps(cfg, indent=2) + '\n')
    "

(substitute the actual confirmed dict from above for the `cfg` literal.)

Continue to section 4 to apply it to `.gitignore`.

## 4. Apply to `.gitignore` (managed merge)

*(Reached from section 1's already-configured branch, or from section 3
just after `.stow.json` is written.)*

This is the one step that is genuinely different from `rigging:init`'s
no-clobber model, and it's worth being precise about why. The engine's core
guarantee is `create == apply_blocks("", desired_sections)`: creating the
file from nothing and updating an existing file are literally the same
function call, just with different `existing_text`. So there's no separate
"does `.gitignore` exist yet" branch here — read it if it's there, pass
`""` if it isn't, and let `apply_blocks` do the rest:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from pathlib import Path; from stow.config import load_config; from stow.scaffold import desired_sections; from stow.blocks import apply_blocks; p=Path('.gitignore'); existing=p.read_text() if p.exists() else ''; p.write_text(apply_blocks(existing, desired_sections(load_config(Path('.')))))"

What this does, concretely:

- Every line the user wrote themselves, **outside** a `# >>> stow:<id> >>>`
  / `# <<< stow:<id> <<<` pair, is preserved byte-for-byte — same position,
  same blank-line formatting. stow never reorders or touches free lines.
- Each stack in `.stow.json` (plus `base`, always) gets a managed block: an
  opener, a fixed advisory comment (`# managed by stow — edits inside this
  block are overwritten; put custom entries outside it`), the stack's
  `.gitignore` entries, and a closer. A block already present at its
  existing position is replaced in place with the current canonical body; a
  block not yet present is appended at the end.
- A managed block for a stack that is no longer in `.stow.json` is dropped
  entirely (with tidy blank-line collapsing at the removal site) the next
  time this call runs — so **dropping a stack from `.stow.json` and
  re-running this same step is how you remove it**, and **re-running this
  same step after any edit to `.stow.json` is how you update it**. There is
  no separate "update" flow.
- A block whose id stow doesn't recognize (hand-written or from a newer
  stow) is left untouched.

Tell the user plainly: **anything they want to add to `.gitignore` by hand
belongs outside the `# >>> stow:... >>>` / `# <<< stow:... <<<` markers** —
inside them is overwritten on every run.

If `apply_blocks` raises `StowError`, an existing `.gitignore` has a
malformed stow marker (unterminated opener, orphan closer, mismatched pair,
or duplicate block id) — it names the offending line number(s). Stop, show
the user the error, and do not write `.gitignore`; there is no repair logic
for malformed markers in increment 1.

## 5. Verify and report

Prove the write converged and the file is well-formed:

- **Idempotency** — re-apply and assert the text comes back byte-for-byte
  unchanged, proving the splice has already reached its fixed point:

      python3 -c "
      import sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from stow.config import load_config
      from stow.scaffold import desired_sections
      from stow.blocks import apply_blocks
      p = Path('.gitignore')
      text = p.read_text()
      again = apply_blocks(text, desired_sections(load_config(Path('.'))))
      assert again == text, 'not idempotent'
      print('ok: idempotent')
      "

- **No malformed markers** — `find_blocks` reports an empty malformed list:

      python3 -c "
      import sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from stow.blocks import find_blocks
      _, malformed = find_blocks(Path('.gitignore').read_text())
      assert not malformed, malformed
      print('ok: no malformed markers')
      "

Report: the confirmed `.stow.json` (or, in already-configured mode, the
config that was already on disk), which managed blocks are now present in
`.gitignore`, and the verification result. Remind the user that custom
entries belong outside the markers, and that re-running `stow:init` after
editing `.stow.json` is the update path — there's no separate command for
it.

Point the user at `keel:init` for the sibling git-lifecycle layer
(`.keel.json`, changelog, PR/issue templates, CODEOWNERS, the changelog CI
gate) and `rigging:init` for the CI layer (`.rigging.json`, the GitHub
Actions workflow) — stow's half is baseline repo hygiene files only:
`.stow.json` and the managed sections of `.gitignore`.

Note what's deliberately **not** here yet — later stow increments, not gaps
in this one:

- managed files beyond `.gitignore` (e.g. `.editorconfig`)
- stacks beyond `python` and `node`
- an interactive edit path for an existing `.stow.json` (increment 1's only
  ways to change it are hand-editing the file and re-running `stow:init`)
