---
name: init
description: Use to set up secret scanning in a repository via hull - proposes a .hull.json and scaffolds an injection-safe gitleaks GitHub Actions workflow, never overwriting existing files.
---

# Initialising hull in a repo

This scaffolds the **secret-scanning** layer only: a `.hull.json` config and
one rendered GitHub Actions workflow that runs a secret scanner (gitleaks,
today's only registered scanner) on push and pull request. It does not touch
the test-runner config (`ballast`), the CI pipeline that runs the test suite
(`rigging`), `.gitignore` hygiene (`stow`), or the git-lifecycle layer —
branch protection, PR/issue templates, CODEOWNERS, the changelog gate
(`keel`'s job).

## 1. Confirm the repo root and check for an existing config

Run `cd "$(git rev-parse --show-toplevel)"` (or equivalent) first, and stay
there for every command below. This plugin's one-liners use `Path('.')` and
bare relative paths (`.hull.json`, `.github/workflows/<name>.yml`)
throughout — those are only correct when the shell's cwd is the repo root,
which cannot be assumed of the agent's starting cwd.

Before proposing anything, check whether `.hull.json` already exists and, if
so, whether it loads:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from hull.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `hull` package
sits at its top level.)

This has three possible outcomes, and they are not the same thing:

- **No `.hull.json`** (prints `None`) — proceed with the normal
  fresh-scaffold flow: section 2, then section 3.
- **`.hull.json` exists and loads** (prints a `Config(...)`) — skip straight
  to section 3, already-configured mode, using the loaded `Config`'s `name`
  (and `scanner`) as-is. Do NOT run section 2's `propose_config` in this
  case — it defaults `name` to `"security"` regardless of what's already on
  disk, and letting that default leak into this flow is exactly the bug this
  section exists to prevent (a workflow's filename and its internal `name:`
  disagreeing with each other).
- **`.hull.json` exists but raises `ConfigError`** — it's present but
  invalid (unparseable JSON, wrong types, a `name` outside its allowed
  charset, or an unknown `scanner` id). Leave it alone, tell the user hull is
  misconfigured (show the `ConfigError` message verbatim — it already names
  the field and the bad value), and stop here. Do not propose a config and
  do not write a workflow — there is no valid on-disk config to render from,
  and overwriting `.hull.json` isn't on the table either; increment 1 has no
  repair or merge logic for it.

There is no stack-detection step here, unlike `rigging:init`/`ballast:init`.
Secret scanning is stack-agnostic — gitleaks scans the repo's git history
and working tree for credential-shaped strings regardless of what language
or framework the code is written in — so there is nothing to detect.

## 2. Propose the config

*(Fresh-scaffold flow only — you're here because section 1 found no
`.hull.json`.)*

Build a signals dict and ask the user only for what you cannot infer:

- `name` — optional; defaults to `"security"` inside `propose_config`. This
  becomes both the workflow's `name:` and the filename
  `.github/workflows/<name>.yml`, so ask if the repo already has a
  convention here. **If the user asks for `name: "ci"`, warn them before
  proceeding**: `.github/workflows/ci.yml` is the conventional filename
  `rigging:init` scaffolds for the test-CI workflow, and picking it for hull
  too means whichever plugin runs `init` second will hit the no-clobber stop
  in section 3 below against the other's file. Confirm they still want `ci`
  (e.g. because they've deliberately renamed rigging's workflow elsewhere)
  before using it.
- `scanner` — optional; defaults to `"gitleaks"` inside `propose_config`,
  currently the only registered scanner id
  (`hull.scanners.SCANNER_IDS == ("gitleaks",)`). No need to ask unless the
  user specifically wants to override it — there's nothing else to pick yet.

Call `hull.scaffold.propose_config(signals)` to get the `.hull.json` dict,
e.g.:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from hull.scaffold import propose_config
    signals = {'name': 'security', 'scanner': 'gitleaks'}
    print(json.dumps(propose_config(signals), indent=2))
    "

Show the result to the user in full and confirm. If they want changes
(rename, though not to `ci` without the warning above), adjust the signals
dict and re-show — don't write anything until they've approved what's on
screen.

`propose_config` raises `ValueError` — naming the offending field — on a
`name` outside its allowed charset or an unknown `scanner` id (this is also
what keeps a hostile name like `"${{ github.token }}"` from ever reaching
the renderer). Surface that message to the user directly rather than
reinterpreting it; it already names the field and the bad value.

Once confirmed, exclusive-create `.hull.json` (`open(path, "x")`, which
raises rather than overwrites if the path exists — this backstops the
no-clobber guarantee even against a loose reading of these instructions: a
file that somehow came into existence since section 1's check can never be
silently clobbered):

    python3 -c "
    import json
    cfg = {'name': 'security', 'scanner': 'gitleaks'}
    open('.hull.json', 'x').write(json.dumps(cfg, indent=2) + '\n')
    "

(substitute the actual confirmed dict from above for the `cfg` literal.)

Continue to section 3 to render the workflow.

## 3. Write the workflow (no-clobber)

*(Reached from section 1's already-loads branch, or from section 2 just
after `.hull.json` is written. Either way, `.hull.json` is now on disk.)*

Check whether the workflow file is already there:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from pathlib import Path
    from hull.scaffold import SECURITY_FILES, classify_files
    print(json.dumps(classify_files(Path('.'), SECURITY_FILES('<name>'))))
    "

(swap `<name>` for the confirmed/loaded name.) `SECURITY_FILES(name)` is
`[".hull.json", ".github/workflows/<name>.yml"]`, so this reports both;
`.hull.json` will classify as `present` at this point regardless of which
branch you arrived from — that's expected, not a signal to touch it again.
What matters here is only the workflow entry.

- If `.github/workflows/<name>.yml` classifies as **absent**, render it from
  the config that is now on disk and exclusive-create it — not
  `open(path, "w")` — so a file that appeared between the classify check and
  the write can never be silently clobbered. Create the `.github/workflows`
  directory first (`os.makedirs(..., exist_ok=True)`, safe whether or not it
  already exists):

      python3 -c "
      import os, sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from hull.config import load_config
      from hull.plan import build_plan
      from hull.render import render
      os.makedirs('.github/workflows', exist_ok=True)
      text = render(build_plan(load_config(Path('.'))))
      open('.github/workflows/<name>.yml', 'x').write(text)
      "

- If `.github/workflows/<name>.yml` classifies as **present**, this is a
  **no-clobber stop**, not a fresh-scaffold continuation: hull is a
  no-clobber plugin like `rigging:init`/`ballast:init`/`keel:init`, not a
  managed-merge plugin like `stow`. Do NOT overwrite it and do NOT attempt
  to migrate or reconcile it with what hull would render — increment 1 has
  no merge logic for a foreign workflow at that path. Tell the user plainly
  that `.github/workflows/<name>.yml` already exists, hull won't touch it in
  increment 1, and if they want hull managing it they need to remove or
  rename the existing file (or adopt it by hand) and re-run `hull:init`.

Continue to section 4 to verify and report either way.

## 4. Verify and report

Prove what's on disk is sound:

- Reload the config — must print a `Config(...)`, not raise:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from hull.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

- Re-render from that config and confirm no attacker-reachable expression
  survived into the workflow — hull's core injection-safety property, proven
  two ways:

  1. Every `- run:` step body (via `render.iter_run_blocks`) must be free of
     `${{`. (Increment 1's only scanner, gitleaks, has no `run` step — it's
     a single `uses:` action — so today this list is always empty; the check
     stays in place for the day a future scanner adds one.)
  2. Every `${{ ... }}` expression that appears **anywhere** in the rendered
     output must fullmatch the whitelist `${{ secrets.GITHUB_TOKEN }}` —
     nothing else, and never a `github.*` context reference. This is the
     load-bearing assertion, not assertion 1: gitleaks's step does carry a
     `${{ secrets.GITHUB_TOKEN }}` env value, so this is what actually
     proves nothing wider (like `${{ github.event.issue.title }}` or a
     hostile `name`) ever reaches the emitted YAML.

  Both checks in one pass:

      python3 -c "
      import re, sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from hull.config import load_config
      from hull.plan import build_plan
      from hull.render import render, iter_run_blocks
      text = render(build_plan(load_config(Path('.'))))
      bad_run = [b for b in iter_run_blocks(text) if '\${{' in b]
      assert not bad_run, bad_run
      exprs = re.findall(r'[$]\{\{.*?\}\}', text)
      whitelist = re.compile(r'[$]\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}')
      bad_expr = [e for e in exprs if not whitelist.fullmatch(e)]
      assert not bad_expr, bad_expr
      print('ok: no \${{ in any run block; every \${{ }} expression is secrets.GITHUB_TOKEN')
      "

Report: what you created, what you skipped (and why), the confirmed config,
and the verification result.

**Surface the gitleaks licensing caveat explicitly** — it's easy for an
adopter to be surprised by a red job that has nothing to do with their code:
`gitleaks/gitleaks-action` requires a free `GITLEAKS_LICENSE` for repos owned
by a GitHub **organization** account, regardless of whether the repo is
public or private; repos owned by a **personal** account need no license. If
this workflow is being scaffolded for a repo owned by an **organization**,
the gitleaks job will fail at run time unless a `GITLEAKS_LICENSE` secret
(obtainable free from gitleaks for this case) is set as a repo or org
secret. Tell the user this up front rather than letting them discover it via
a failing Actions run.

Point the user at:

- `rigging:init` — the sibling layer that authors the test-CI workflow
  (`.rigging.json`, `.github/workflows/ci.yml` by default). hull does not
  own that file; it only guards against a filename collision with it (see
  section 2's warning on `name: "ci"`).
- `ballast:init` — the test-runner config layer (`.ballast.json`,
  `pytest.ini`) that rigging's workflow actually runs.
- `stow:init` — baseline repo hygiene (`.stow.json`, managed `.gitignore`
  sections).
- `keel:init` — the git-lifecycle layer (`.keel.json`, changelog, PR/issue
  templates, CODEOWNERS, the changelog CI gate).

Note what's deliberately **not** here yet — later hull increments, not gaps
in this one:

- scanners beyond `gitleaks` (`hull.scanners.SCANNER_IDS` has exactly one
  entry today)
- automating the `GITLEAKS_LICENSE` secret itself (hull can only warn that
  an organization-owned repo needs one; setting a repo/org secret is outside
  what a rendered workflow file can do)
- configurable triggers (today's workflow is always
  `on: [push, pull_request]`)
- scan-scope configuration (path allow/deny lists, custom gitleaks rules) —
  today's job runs gitleaks with its own defaults
- migrating or reconciling a pre-existing, foreign workflow file at
  `.github/workflows/<name>.yml`
- an interactive edit path for an existing `.hull.json` (increment 1's only
  ways to change it are hand-editing the file and re-running `hull:init` to
  pick up the new workflow, or deleting the workflow file first if you want
  it re-rendered)
