# rigging: JS toolchains, custom test commands, and service containers

**Issue:** #26 · **Date:** 2026-07-22 · **Status:** approved, not yet implemented

## Why

0.6.0 taught `rigging:init` to refuse when it detects a JavaScript toolchain it
cannot drive. That was the right move — it replaced a workflow that died on
`npm ci` every run with an honest diagnosis at setup time. It did not make
rigging usable for those repos.

The repo that reported #24 still has **no test CI**. It needs three things
rigging cannot express, and it needs all three:

- **pnpm** — `pnpm@9.12.0`, a `pnpm-workspace.yaml`, no `package-lock.json`
- **a Postgres service** — the DB suites need a live server on `TEST_DATABASE_URL`
- **its actual test command** — `turbo run test --concurrency=1`, not `npm test`

Shipping any one of these alone leaves that repo exactly where it is. That is
why this is one design rather than three, even though it ships in three
increments.

## The finding that shapes the whole design

**`shlex.quote` does not protect against GitHub Actions expression injection.**

GitHub substitutes `${{ ... }}` at the YAML layer, before the shell ever sees
the line. An argv element containing `${{ secrets.GITHUB_TOKEN }}` is expanded
regardless of how correctly it was shell-quoted — quoting defends against the
shell, and the shell is not the attacker here.

So the custom test command needs **two independent guarantees**, and only the
second preserves the invariant rigging already advertises:

1. `shlex.quote` on each element, so shell metacharacters cannot mean anything.
2. An explicit rejection of any element containing `${{`, so an Actions
   expression never reaches a `run:` line in the first place.

`tests/test_injection.py` currently guarantees no `${{` appears in any `run:`
block, and that guarantee is free today because no config value can reach one.
This design is the first thing that puts user-controlled text into an
executable line, so guarantee 2 is what keeps that test meaningful rather than
lucky.

## Increment 1: package managers

### The registry

A `NODE_PACKAGE_MANAGERS` table beside the node `StackSpec` in `stacks.py`,
for the same adjacency reason `FOREIGN_NODE_LOCKFILES` lives there: whoever
changes the node steps must walk past the table that describes them.

| id | lockfile | extra setup action | install | test |
|---|---|---|---|---|
| `npm` | `package-lock.json` | — | `npm ci` | `npm test` |
| `pnpm` | `pnpm-lock.yaml` | `pnpm/action-setup@0ebf4713` (v6.0.9) | `pnpm install --frozen-lockfile` | `pnpm test` |
| `yarn1` | `yarn.lock` | — | `yarn install --frozen-lockfile` | `yarn test` |
| `yarn-berry` | `yarn.lock` | — | `yarn install --immutable` | `yarn test` |
| `bun` | `bun.lockb`, `bun.lock` | `oven-sh/setup-bun@0c5077e5` (v2.2.0) | `bun install --frozen-lockfile` | `bun run test` |

Install and test are stored as **argv tuples**, not strings, so increment 2's
custom command and the registry's defaults travel through exactly one
rendering path. `bun run test` rather than `bun test` because `bun test` runs
bun's own runner, while every other entry here runs the repo's `test` script —
a repo using vitest under bun would otherwise silently run a different suite.

`FOREIGN_NODE_LOCKFILES` is deleted. Its job was to say "we cannot drive
this"; the same lockfiles now say *which* manager to drive. Detection keeps
refusing only for the genuinely undeterminable cases below.

### Yarn's two incompatible toolchains

Yarn 1 takes `--frozen-lockfile`; Yarn 2+ takes `--immutable`. Passing either
flag to the other major fails. `yarn.lock` is the lockfile name for both and
does not say which.

Resolution order:

1. `packageManager` in `package.json` (`"yarn@3.6.4"` -> berry) — authoritative.
2. Absent that, **refuse with a diagnosis**, naming the ambiguity and telling
   the user to add a `packageManager` field.

Refusing is consistent with the rule 0.6.0 established. Guessing here would be
worse than the bug this issue exists to fix: a wrong guess produces a workflow
that fails on its install step, which is precisely the outcome the refusal
machinery was built to prevent.

### Ambiguity is a refusal, not a precedence rule

Two different manager lockfiles at the repo root (say `pnpm-lock.yaml` **and**
`yarn.lock`) is not something to resolve by precedence. It means the repo is
mid-migration or has a stale file, and either answer rigging picks is as
likely to be wrong as right. It refuses, naming both files.

A lockfile that disagrees with `packageManager` is the same case and gets the
same treatment.

### Config

`STACK_KEYS` gains `packageManager`. Its legal values are the registry ids
above — including `yarn1` and `yarn-berry` as *separate* values, since they
are separate toolchains that happen to share a lockfile name. A user may
write either by hand; `rigging:init` writes the **detected** value into
`.rigging.json` rather than leaving it implicit.

This matters for a property the suite relies on elsewhere: config fully
determines rendered output. If the manager were re-detected at render time,
the same `.rigging.json` would produce different workflows on different
machines — and adding a lockfile would silently change a committed artifact.

## Increment 2: custom test commands

`.rigging.json` gains `stacks.<id>.testCommand`, an argv array that replaces
the stack's or manager's default test argv:

    "stacks": {"node": {"packageManager": "pnpm",
                        "testCommand": ["turbo", "run", "test", "--concurrency=1"]}}

**Validation:** a non-empty list of non-empty strings; no element may contain
`${{` (guarantee 2 above) or a newline. Everything else is permitted, because
`shlex.quote` makes it inert.

**What is deliberately not expressible:** pipes, redirects, `&&`, subshells,
environment assignments. An argv array cannot represent them, and that is the
feature — those are the constructs that turn a config file into a remote code
execution surface for anyone who can land a commit. A repo needing a shell
pipeline needs a hand-written workflow, and should be told so rather than
accommodated.

`shlex` is stdlib, so engine purity is unaffected.

## Increment 3: service containers

### A registry, not a free-form block

    "services": {"postgres": {"version": "16", "urlEnv": "TEST_DATABASE_URL"}}

`SERVICE_REGISTRY` owns image, port, container env, and **health check** per
known service. The repo chooses only the version and the env var name.

Health checks are the reason this is a registry rather than a passthrough of
GitHub's schema. Without `--health-cmd`, a job races the container's startup
and flakes intermittently — the worst possible failure for a CI layer,
because it teaches a team that red means "run it again". Making the health
check rigging's property rather than the user's means it cannot be forgotten.
It also means no user-supplied string ever lands in a Docker `options:` line.

Initial services: `postgres`, `mysql`, `redis`.

### Image pinning: tags, not digests

Service images are pinned by major tag (`postgres:16`), **not** by digest,
which is a deliberate inconsistency with the SHA-pinning rule for Actions and
is worth stating rather than leaving to be discovered:

- An Action runs *inside* the job with access to the workflow token and the
  checked-out repo. A compromised Action reads secrets and writes commits.
- A service container is an ephemeral test fixture on a private network. It
  never sees the token or the source, and it is destroyed with the job.

The threat models are genuinely different, and a major tag keeps getting
security patches without human intervention. Digest-pinning them would also
inherit exactly the staleness problem #30 just found for the trufflehog pin —
a pin nothing can bump.

### `urlEnv` and where it lands

`urlEnv` names the environment variable the test step receives the connection
URL in. It takes an identifier matching `^[A-Za-z_][A-Za-z0-9_]*$` — the same
strictness, and for the same reason, as hull's `licenseSecret`: it is rendered
into YAML adjacent to values that matter, and no legitimate env var name is
excluded by the pattern.

The URL itself is composed by rigging from the registry's own credentials, so
it is a registry constant and never user input.

### Services attach per stack

`services` sits inside a stack's config, not at the top level. A polyglot repo
where the node suite needs Postgres and the python suite does not should not
pay for a database in both jobs, and a top-level block cannot express that.

## What is NOT changing

- **`npm` remains the default** when a repo has a `package.json` and no other
  signal. That is what an npm repo is.
- **Detection stays separate from diagnosis.** `detect_stacks` continues to
  report what it found; the reasons travel beside it. A future increment that
  adds a manager deletes a refusal and changes nothing about detection.
- **Unknown config keys stay a hard `ConfigError`.** There is still no escape
  hatch for hand-editing rendered steps.
- **Engine purity.** All three increments are stdlib-only; `shlex` and `json`
  are the only additions.

## Testing

- A golden per manager (`node-pnpm.yml`, `node-yarn1.yml`, `node-yarn-berry.yml`,
  `node-bun.yml`), plus one for a custom test command and one for a serviced
  job. The three existing goldens (`node.yml`, `python.yml`, `polyglot.yml`)
  must stay byte-identical — that is what proves npm repos are unaffected.
- **Injection tests are the load-bearing ones for increment 2.** A hostile
  `testCommand` containing `${{ github.event.issue.title }}`, a newline, a
  quote, or a `;` must be refused at load time; and the rendered output for
  every accepted command must still contain no `${{` in any `run:` block.
  Both halves are needed: the first proves the guard exists, the second proves
  it is sufficient.
- The yarn-ambiguity and two-lockfile refusals each need a test asserting the
  reason names the specific files found, not merely that something was refused.
- A round-trip test per increment: `propose_config` output must load through
  `config.load_config`. This is the contract that #27's Critical defect broke,
  and each new config key is a fresh chance to break it again.

## Risks

- **Three new action pins** (`pnpm/action-setup`, `oven-sh/setup-bun`) join
  trufflehog in having no Dependabot path, since rigging's own `ci.yml` is a
  python workflow and references neither. #30 already tracks the general
  problem; this makes it larger and should be noted there.
- **`bun run test` vs `bun test`** is a judgement call that will occasionally
  be wrong for a repo that genuinely wants bun's runner. `testCommand` from
  increment 2 is the escape hatch, which is an argument for shipping the two
  close together.
- **Scope.** This is the largest single design in the suite so far. Each
  increment is independently shippable and independently useful, and the
  issue closes only when all three land.
