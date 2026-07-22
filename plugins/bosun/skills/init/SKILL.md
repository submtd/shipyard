---
name: init
description: Use to set up Dependabot in a repository via bosun - detects the repo's stack, proposes a .bosun.json (github-actions always-on plus any detected pip/npm), and scaffolds a declarative .github/dependabot.yml, never overwriting existing files.
---

# Initialising bosun in a repo

This scaffolds the **dependency-update** layer only: a `.bosun.json` config
and one rendered `.github/dependabot.yml`. It does not scan for
vulnerabilities, run the test suite, scan for secrets, or touch branch
protection, PR/issue templates, CODEOWNERS, or the changelog gate — those
are other plugins' jobs (see the end of this skill).

## 1. Confirm the repo root and check for an existing config

Run `cd "$(git rev-parse --show-toplevel)"` (or equivalent) first, and stay
there for every command below. This plugin's one-liners use `Path('.')` and
bare relative paths (`.bosun.json`, `.github/dependabot.yml`) throughout —
those are only correct when the shell's cwd is the repo root, which cannot
be assumed of the agent's starting cwd.

Before proposing anything, check whether `.bosun.json` already exists and,
if so, whether it loads:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from bosun.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

(`${CLAUDE_PLUGIN_ROOT}` is this plugin's root directory; the `bosun`
package sits at its top level.)

This has three possible outcomes, and they are not the same thing:

- **No `.bosun.json`** (prints `None`) — proceed with the normal
  fresh-scaffold flow: sections 2-3 below.
- **`.bosun.json` exists and loads** (prints a `Config(...)`) — skip
  straight to section 4, already-configured mode, using the config that is
  already on disk. Do NOT run section 3's `propose_config` in this case —
  there is nothing to re-propose; the committed file is the source of truth
  from here on.
- **`.bosun.json` exists but raises `ConfigError`** — it's present but
  invalid (unparseable JSON, wrong types, an unknown ecosystem id, or an
  interval outside the allowed set). Leave it alone, tell the user bosun is
  misconfigured (show the `ConfigError` message verbatim — it already names
  the field and the bad value), and stop here. Do not detect ecosystems, do
  not propose a config, and do not write `.github/dependabot.yml` — there is
  no valid on-disk config to render from, and overwriting `.bosun.json`
  isn't on the table either; increment 1 has no repair or merge logic for
  it. Write nothing in this branch.

## 2. Detect the ecosystems

*(Fresh-scaffold flow only — you're here because section 1 found no
`.bosun.json`.)*

Call `detect_ecosystems`, which checks for each registered *always-off*
ecosystem's marker files at repo root (today: `python` —
`pyproject.toml`/`setup.py`/`setup.cfg`/`requirements.txt`; `node` —
`package.json`) and returns the matching ids, in registry order:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from bosun.detect import detect_ecosystems; from pathlib import Path; print(detect_ecosystems(Path('.')))"

`detect_ecosystems` never returns `githubActions`, even if the repo has
`.github/workflows/`. GitHub Actions is registered as **always-on**, not
detected: every repo that has adopted these plugins already has one or more
workflows with pinned action refs (rigging's CI workflow, hull's gitleaks
workflow, and so on), and those refs need to stay current regardless of
what language stack the repo is written in. `propose_config` (next section)
adds `githubActions` unconditionally — you don't need to ask the user about
it, and an empty `detect_ecosystems()` result is not an error; it just means
the proposed config will contain `githubActions` alone.

## 3. Propose the config

*(Fresh-scaffold flow only.)*

Build a signals dict from what you detected:

- `ecosystems` — the detected ids from section 2, as a list (may be empty).
  `githubActions` must NOT be included here — `propose_config` adds it
  itself; passing it explicitly is redundant, not wrong, but leave it out to
  match the examples below.
- `intervals` — optional, `{ecosystem_id: interval}` (`"daily"`, `"weekly"`,
  or `"monthly"`). An id without an entry gets `{}` in the emitted config,
  so `config.load_config` fills in the registry default (`"weekly"`) later.
  Ask if the user wants something other than weekly for a given ecosystem —
  including `githubActions` itself, which `intervals` can also target.
- `targetBranch` — optional, the branch Dependabot opens its update PRs
  against. Determine it from `.keel.json` rather than asking cold; see just
  below.

### Determining `targetBranch`

Omitting this key is not a neutral choice. Dependabot falls back to the
**repository default branch** when `target-branch` is absent, and in a
gitflow repo that branch is `main` — production. A bosun scaffold with no
`targetBranch` in such a repo opens weekly dependency PRs straight at
production, bypassing `develop`, bypassing the changelog convention keel
enforces, and leaving integration behind until somebody back-merges. Two
plugins in the same suite would be contradicting each other.

bosun can usually answer this without asking, because keel already wrote the
answer down. Read it:

    python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from bosun.scaffold import keel_integration_branch; from pathlib import Path; print(keel_integration_branch(Path('.')))"

- **Prints a branch name** (e.g. `develop`) — the repo is keel-managed under
  a gitflow topology. Use it as the `targetBranch` signal. Tell the user
  where the value came from and confirm it, rather than presenting it as
  something you chose.
- **Prints `None`** — this means one of three quite different things, and
  you should say which: there is no `.keel.json` (the repo is not
  keel-managed); the topology is `trunk`, in which case the integration
  branch **is** the repository default branch and omitting `target-branch`
  is exactly right; or `.keel.json` is present but unusable. That helper is
  a convenience, never a validator — it degrades quietly on a malformed file
  precisely so it can never become a second, drifting opinion about whether
  keel's config is sound. If you need to know which case you are in, load it
  through keel's own loader.

  In the not-keel-managed and unusable cases, ask the user whether dependency
  PRs should target something other than the repository default branch, and
  pass what they say. In the trunk case, do not ask — pass nothing.

`propose_config` validates the value against the same branch-name pattern
hull and rigging use (`^[A-Za-z0-9][A-Za-z0-9._/-]*$`) and raises
`ValueError` on anything else. That pattern is deliberately narrower than
git's own rules: the value is rendered into YAML, so a name that would need
quoting or escaping is a name bosun refuses outright.

Call `bosun.scaffold.propose_config(signals)` to get the `.bosun.json`
dict, e.g.:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from bosun.scaffold import propose_config
    signals = {'ecosystems': ['python']}
    print(json.dumps(propose_config(signals), indent=2))
    "

This always emits `githubActions` plus every id you listed — for
`{'ecosystems': ['python']}` that's
`{"ecosystems": {"githubActions": {}, "python": {}}}`, with a top-level
`"targetBranch"` alongside it when (and only when) you passed that signal.
Show the result to
the user in full and confirm. If they want changes (add/drop an ecosystem,
set an interval), adjust the signals dict and re-show — don't write
anything until they've approved what's on screen.

`propose_config` raises `ValueError` — naming the offending field — on an
unknown ecosystem id in `signals['ecosystems']`, an interval outside
`("daily", "weekly", "monthly")` in `signals['intervals']`, or a
`signals['targetBranch']` that is not a legal branch name. Surface that
message to the user directly rather than reinterpreting it; it already
names the field and the bad value.

Once confirmed, exclusive-create `.bosun.json` (`open(path, "x")`, which
raises rather than overwrites if the path exists — this backstops the
no-clobber guarantee even against a loose reading of these instructions: a
file that somehow came into existence since section 1's check can never be
silently clobbered):

    python3 -c "
    import json
    cfg = {'ecosystems': {'githubActions': {}, 'python': {}}}
    open('.bosun.json', 'x').write(json.dumps(cfg, indent=2) + '\n')
    "

(substitute the actual confirmed dict from above for the `cfg` literal.)

Continue to section 4 to render `.github/dependabot.yml`.

## 4. Write dependabot.yml (no-clobber)

*(Reached from section 1's already-loads branch, or from section 3 just
after `.bosun.json` is written. Either way, `.bosun.json` is now on disk.)*

Check whether the rendered file is already there:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from pathlib import Path
    from bosun.scaffold import DEPENDABOT_FILES, classify_files
    print(json.dumps(classify_files(Path('.'), DEPENDABOT_FILES())))
    "

`DEPENDABOT_FILES()` is `[".bosun.json", ".github/dependabot.yml"]`, so this
reports both; `.bosun.json` will classify as `present` at this point
regardless of which branch you arrived from — that's expected, not a signal
to touch it again. What matters here is only the `.github/dependabot.yml`
entry.

- If `.github/dependabot.yml` classifies as **absent**, render it from the
  config that is now on disk and exclusive-create it — not
  `open(path, "w")` — so a file that appeared between the classify check and
  the write can never be silently clobbered. Create the `.github` directory
  first (`os.makedirs(..., exist_ok=True)`, safe whether or not it already
  exists):

      python3 -c "
      import os, sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from bosun.config import load_config
      from bosun.plan import build_plan
      from bosun.render import render
      os.makedirs('.github', exist_ok=True)
      text = render(build_plan(load_config(Path('.'))))
      open('.github/dependabot.yml', 'x').write(text)
      "

- If `.github/dependabot.yml` classifies as **present**, this is a
  **no-clobber stop**, not a fresh-scaffold continuation: bosun is a
  no-clobber plugin like `rigging:init`/`hull:init`/`ballast:init`/
  `keel:init`, not a managed-merge plugin like `stow`. Do NOT overwrite it
  and do NOT attempt to migrate or reconcile it with what bosun would
  render — increment 1 has no merge logic for a foreign `dependabot.yml` at
  that path. Tell the user plainly that `.github/dependabot.yml` already
  exists, bosun won't touch it in increment 1, and if they want bosun
  managing it they need to remove or rename the existing file (or adopt it
  by hand) and re-run `bosun:init`.

Continue to section 5 to verify and report either way.

## 5. Verify and report

Prove what's on disk is sound:

- Reload the config — must print a `Config(...)`, not raise:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from bosun.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

- Re-render from that config and confirm it matches what's on disk
  byte-for-byte, and that the output is declarative-only — bosun's core
  safety property, since `dependabot.yml` has no `run:`/`uses:` step and no
  `${{ }}` expression syntax anywhere in its schema:

      python3 -c "
      import sys
      sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
      from pathlib import Path
      from bosun.config import load_config
      from bosun.plan import build_plan
      from bosun.render import render
      text = render(build_plan(load_config(Path('.'))))
      on_disk = Path('.github/dependabot.yml').read_text()
      assert text == on_disk, 'rendered output does not match .github/dependabot.yml'
      assert '\${{' not in text, 'unexpected \${{ expression in dependabot.yml'
      assert 'run:' not in text, 'unexpected run: step in dependabot.yml'
      print('ok: rendered output matches disk and is declarative-only')
      "

  This `${{`/`run:` check is a **structural** guard, not the load-bearing
  proof — unlike rigging/hull there is no free-text render input for an
  attacker to smuggle an expression through in the first place: `.bosun.json`
  only ever contributes an `interval` (enum-validated against
  `("daily", "weekly", "monthly")`), a set of ecosystem ids (whitelisted
  against the registry), and a `targetBranch` (matched against
  `^[A-Za-z0-9][A-Za-z0-9._/-]*$`, which admits no whitespace, no newline,
  no quote, and no `$` — so it cannot open an expression or start a new YAML
  key), and `directory` is fixed at `"/"` by `plan.py`, never read from
  config. The assertion documents that invariant; it doesn't establish it.

Report: what you created, what you skipped (and why), the confirmed config,
and the verification result.

**Surface the Dependabot-enablement caveat explicitly** — it's easy for a
maintainer to be surprised by a wave of unfamiliar PRs a day or two after
this skill runs: committing `.github/dependabot.yml` **activates Dependabot
on GitHub itself**. Once it's pushed, GitHub starts opening version-update
pull requests on the configured schedule — one PR per outdated dependency,
for every ecosystem in the config (the pinned `uses:` action refs under
`github-actions`, plus any detected `pip`/`npm` dependencies) — and a human
needs to review and merge (or close) each one. This is expected behavior,
not a bug in what bosun wrote; tell the user to expect these PRs to start
showing up once the file is merged to the default branch.

Also note the settled boundary, since the two are easy to conflate: bosun
does dependency **updates** — opening PRs to bump pinned versions on a
schedule. Dependency **vulnerability scanning** (GitHub's Dependabot alerts
/ security-advisory layer) is a related but distinct feature, and it is out
of scope here — it's a candidate for a future `hull` increment (hull today
does secret scanning), not something `bosun:init` configures.

Point the user at the sibling init skills for the layers bosun doesn't own:

- `keel:init` — the git-lifecycle layer: branch protection, PR/issue
  templates, CODEOWNERS, and the changelog gate.
- `rigging:init` — the CI pipeline layer: `.rigging.json` and the rendered
  test-CI workflow.
- `stow:init` — baseline repo hygiene: `.stow.json` and a managed
  `.gitignore`.
- `ballast:init` — the test-runner config layer: `.ballast.json` and
  `pytest.ini`.
- `hull:init` — the secret-scanning layer: `.hull.json` and a rendered
  gitleaks workflow.

Note what's deliberately **not** here yet — these are later bosun
increments, not gaps in this one:

- ecosystems beyond `github-actions`, `python` (`pip`), and `node` (`npm`)
- a configurable `directory` (today's plan always fixes it at `"/"`, i.e.
  the repo root — no per-ecosystem manifest path, no monorepo support)
- reviewers, assignees, labels, commit-message prefixes, `open-pull-requests-limit`,
  or grouped updates — today's renderer only emits `package-ecosystem`,
  `directory`, `target-branch` (when configured), and `schedule.interval`
- configurable triggers
- dependency vulnerability scanning/alerts (see the settled boundary above)
- an interactive edit path for an existing `.bosun.json` (increment 1's only
  ways to change it are hand-editing the file and re-running `bosun:init` to
  pick up the new `.github/dependabot.yml`, or deleting that file first if
  you want it re-rendered)
