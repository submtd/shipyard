# fathom — decision record: not built, roster closed at six

**Suite:** Shipyard
**Status:** Decided — `fathom` will not be built. The core roster closes at six.
**Date:** 2026-07-21

## The decision

`fathom` (debugging and profiling) was the seventh and last entry on the original
Shipyard roster, carried since keel's design spec. It will **not** be built. The
core suite is complete at six: `keel`, `rigging`, `stow`, `ballast`, `hull`,
`bosun`.

This is not a scheduling deferral. fathom is blocked on a **host repo**, not on
design work. See [Reopening condition](#reopening-condition).

## Why: the dogfood-inversion test

Every Shipyard plugin owns a file **the repo would keep on its own merits**, and
dogfoods it as a consequence:

| Artifact | Why the repo keeps it |
|----------|----------------------|
| `.gitignore` | changes what git does |
| `pytest.ini` | collection does not work without it |
| `ci.yml` | gates merges |
| `security.yml` | catches a real leaked secret |
| `dependabot.yml` | opens real PRs |
| `changelog.yml` | enforces the changelog rule server-side |

fathom would **invert** that relationship: the artifact would exist *because the
byte-identity test needs a target*. Shipping the first inversion costs more than
the plugin is worth — it retroactively discounts the six honest dogfoods.

## The five candidates, and the measured evidence against each

All facts below were verified against this repo, not asserted.

### 1. `.vscode/launch.json` — the only candidate that passes *artifact* honesty

It is one of the most commonly hand-authored, hand-committed dev files in the
ecosystem, read by VS Code, Cursor, Windsurf, VSCodium, and nvim-dap
(`require('dap.ext.vscode').load_launchjs()`).

It fails **dogfood** honesty *here specifically*:

```
git log --all --diff-filter=A --name-only --pretty=format: | sort -u | grep -ciE '\.vscode|\.idea'
→ 0
```

shipyard has never contained a `.vscode/` or `.idea/` across **126 commits and
173 tracked files**. The file would land in the same PR as the test that consumes
it. Nobody has missed it.

Note also that adopting it would be a posture change: all six shipped artifacts
own tool-neutral standards (GitHub Actions, Dependabot, pytest, gitignore).
`launch.json` is editor-specific. That is defensible — there is no editor-neutral
alternative to be agnostic toward, and the file is inert for anyone not using a
compatible editor — but it is a category change, not a seventh instance of the
pattern.

### 2. Profiling / benchmark CI (`profile.yml`, `perf.yml`, flamegraphs)

Settled by arithmetic: **917 tests in ~3.4s**, slowest test ~0.22s, no runtime
code, no dependencies. A perf gate over that is a hang detector that can never
fire — CI minutes and threshold flake for zero signal. It would also force a
third full suite run alongside rigging's 3.9/3.12 matrix. Perf CI has no day-one
signal without baseline storage, which is nowhere near a v0.1.0 increment.

### 3. Logging configuration

There is no runtime application, no daemon, no server, no entrypoint. Nothing
emits logs. Pure fabrication.

### 4. `.pdbrc`

Real, but it is a personal dotfile people usually gitignore, and it is a command
file **pdb executes on start**. Committing one imposes one developer's debugger
preferences on contributors and is a small code-execution vector — a poor thing
for the suite that also ships `hull`.

### 5. `tasks.json`

A real format, but it is a task runner, not a debugger; it overlaps `make`/pytest
invocation rather than debugging. Left unclaimed.

## The structural finding

**For a stdlib-only pytest repo, the debugging surface *is* the test-runner
surface — and `ballast` already owns it.**

The genuinely useful Python debug knobs (`--pdb`, `-x`, `--lf`, `--tb`, `--sw`)
are `pytest.ini` keys, i.e. `ballast` `addOpts` values. That is an **ownership
collision**, not an available new filename. There is no artifact left for fathom
to own that another plugin does not already own or that the repo would not
delete.

## Corrections to the record

Two arguments that arose during the evaluation are **false** and must not be
carried forward if this is ever revisited:

1. **"A pytest launch config would duplicate `.ballast.json`'s pythonpath."**
   False. A `module: pytest` configuration with `cwd: ${workspaceFolder}`
   inherits `pytest.ini`'s `pythonpath` — empirically, the whole 917-test suite
   runs from the repo root with no `PYTHONPATH` set. The case against fathom
   rests on the missing dogfood target, **not** on a duplication that does not
   arise.

2. **"A workflow-filename collision warning is duplicated across four SKILL.md
   files."** False. Only `hull` has a configurable workflow filename
   (`.hull.json` `name` → `security.yml`); `keel`, `rigging`, and `bosun` all
   emit fixed filenames, and the warning lives in exactly one file.

## Why not skills-first

A skills-only `fathom` (debugging/profiling *methodology* rather than a rendered
artifact) was evaluated and rejected: `superpowers:systematic-debugging` already
covers that ground, a skills-only plugin would break four suite conventions at
once, and it would make "just write some skills" the cheapest path for anything
that follows. Its one genuinely load-bearing idea — cross-plugin reference
resolution — was harvested instead (see below).

## Reopening condition

Revisit fathom **only** if shipyard, or a repo being scaffolded with it, grows a
**real runtime entrypoint** — a service, or a CLI with args and env. That flips
`launch.json` from inert to load-bearing.

The `launch.json` design is kept on file as **blocked, not rejected**: a pure
`launchers.py` registry, stack-detected configurations, and a zero-free-text
config whose justification is that VS Code's `console: "integratedTerminal"`
composes a shell command line. **Note for that day:** v0.1.0's refusal of
`args`/`program`/`env` is exactly what a real-entrypoint adopter needs, so the
free-text injection surface must be *solved* before it ships anywhere it would
be useful — not sidestepped as it was here.

## What this exercise yielded instead

Two real findings, both shipped in this increment:

1. **A repo-wide skill-integrity guard.** 16 SKILL.md files exist; only the five
   init skills validate their own frontmatter, so **11 of 16 are unchecked**
   (all of keel's). Nothing checks that the **61** cross-plugin `plugin:skill`
   references resolve, and nothing checks that the `plugins/*` directory set and
   `marketplace.json` agree in both directions. All pass today — this is a
   **rot guard**, and its honest value is coverage, not repair.

2. **A `ballast` `addOpts` denylist.** `ballast`'s flag validator accepts any
   `\S+`, so `--pdb`, `-s`, or `--sw` can be written into `.ballast.json` and
   rendered into the *committed* `pytest.ini` — which would hang or break CI on
   the first failure. Interactive/CI-hostile flags are now rejected at config
   load with a `ConfigError` naming the flag.

Note the pleasing symmetry of the second finding: the one place debugging flags
genuinely intersect this suite, the correct move was to **forbid** them in a
committed config — the opposite of scaffolding them.

## Scope

**In scope (this increment):** this decision record; the README roster closure;
the skill-integrity guard; the ballast addOpts denylist; a CHANGELOG entry.

**Explicitly NOT created:** `plugins/fathom/**`, `.fathom.json`, any
`marketplace.json` entry, any `.vscode/` file, any new workflow file. Because no
new tests directory ships, the 5-edit **ballast lockstep is not incurred** —
`plugins/keel/tests` is already in `.ballast.json` testPaths, so `pytest.ini`,
`.ballast.json`, and `marketplace.json` must all stay byte-identical.

**Deferred:** `ballast:debug` (a pytest debug-mechanics skill on the plugin that
already owns `pytest.ini`) — cheap if wanted, but it is a flag reference with no
machine-verifiable dogfood and it partially overlaps
`superpowers:systematic-debugging`. Generalizing the skill guard into a shared
helper or a repo-level `tests/` directory — one module in keel is enough; a
repo-level tests dir would itself trigger the full ballast lockstep.
