# stow — design spec (increment 1)

**Suite:** Shipyard
**Plugin:** stow (third member, after keel and rigging)
**Increment:** 1 of stow
**Date:** 2026-07-20

## What stow is

stow outfits a repo's **baseline files**. It is the stack-aware sibling keel:init
deferred to: keel:init deliberately writes no `.gitignore`/`.editorconfig` and does
no stack detection. stow closes that gap — it detects a repo's stack(s) and manages
the standard content of `.gitignore`, centrally and updatably, without ever
destroying the user's own lines.

The name is a nautical verb: to *stow* is to store gear securely in its proper
marked place aboard ship. stow keeps each managed section in its own marked region
and reads naturally as the marker prefix (`# >>> stow:python >>>`).

Increment 1 ships **stow v0.1.0**: a stdlib-only pure engine with a **live
managed-block splice** that idempotently writes AND updates a repo's `.gitignore`
from a pure-data section registry (`base` + `python` + `node`), plus a `stow:init`
skill, a committed `.stow.json`, and a rigging-strength dogfood.

## The central design decision: managed-block splice

Baseline files mix **tool-managed** standard content with **user-custom** lines
(shipyard's own `.gitignore` has `.superpowers/`, which no stack-generic generator
would produce). Two obvious models both fail:

- **Static templates + no-clobber** (keel:init's model) can scaffold a new file but
  can never *update* an existing one — that is the abandoned-template-repo failure
  keel and rigging exist to escape.
- **Full render** (rigging's model) is right when the tool owns 100% of the artifact
  (a `ci.yml` has no user content), but it would clobber the user's custom
  `.gitignore` lines.

stow uses the only model that both updates centrally **and** preserves user content:
a **managed-block splice**. The tool owns marker-delimited regions per section; it
rewrites only inside its markers and emits every line outside them verbatim. Central
authority is scoped to the marked regions.

Markers (full-line, anchored regex; conda-init precedent):

```
# >>> stow:python >>>
<one fixed advisory comment>
<registry body lines>
# <<< stow:python <<<
```

`apply_blocks(existing_text, desired_sections) -> new_text` is a pure string→string
transform, and **`create == apply_blocks("", desired_sections)`** — writing a fresh
file and updating an existing one are the same code path. Rules:

1. Lines **outside** any well-formed stow region are emitted verbatim, in original
   order/position — never reordered, deduped, or rewritten. This is where
   user-custom content lives and survives.
2. A managed region whose id is in `desired_sections` is replaced **in place** with
   its freshly rendered block.
3. A managed region whose id is a **known** registry id but **not** desired is
   dropped (declarative removal: drop a stack from `.stow.json`, re-run, its block
   disappears).
4. A managed region whose id is **unknown** to this stow version is left untouched
   (forward-compat).
5. Any desired id with no existing region is appended in canonical order (`base`
   first, then registry order), separated by exactly one blank line, with a single
   guaranteed trailing newline.

**Idempotent by construction:** `apply_blocks(apply_blocks(x)) == apply_blocks(x)`.
**Safe:** a malformed region (opener without closer, or duplicate openers for one id)
raises `StowError` naming the file/line rather than guessing — a hand-corrupted file
is never silently clobbered. v0.1.0 normalizes line endings to `\n` (CRLF
preservation deferred). The marker text is a frozen compatibility contract pinned by
a test.

## Architecture

Mirrors rigging's proven separation: a stdlib-only pure engine (AST-purity-guarded),
Python 3.9+, with all interaction pushed to the `stow:init` skill.

| Path | Responsibility | Pure |
|------|----------------|------|
| `stow/__init__.py` | Empty package marker (`__version__ = "0.1.0"`) | ✓ |
| `stow/stacks.py` | Pure DATA registry (the seam). Frozen `StackSpec{id, detect_files, gitignore: tuple[str,...]}`. `BASE` is a module constant (body: `.DS_Store`, `Thumbs.db`) always applied and NOT in `REGISTRY`. `REGISTRY = {python (detect pyproject.toml/setup.py/setup.cfg/requirements.txt; body __pycache__/, *.py[cod], *.egg-info/, .pytest_cache/, .mypy_cache/, .ruff_cache/, .venv/, build/, dist/), node (detect package.json; body node_modules/, npm-debug.log*, dist/, coverage/, .env)}`. `STACK_IDS = tuple(REGISTRY)`. | ✓ |
| `stow/blocks.py` | THE managed-block engine, pure string→string, no fs. Marker constants + anchored line regex (opener `^# >>> stow:(?P<id>[a-z0-9-]+) >>>$`, closer `^# <<< stow:\1 <<<$`). `StowError`. `render_block(spec) -> str` (deterministic). `find_blocks(text) -> (well-formed (id,start,end) pairs, malformed markers)`. `apply_blocks(existing_text, desired_sections) -> str` (the splice + idempotency, `create == apply_blocks("", ...)`). Raises `StowError` on malformed/duplicate. | ✓ |
| `stow/config.py` | Load/validate `.stow.json` (camelCase, committed). Near-copy of `rigging/config.py`. `Config{stacks: dict[str, ...]}` frozen; `load_config(root) -> Optional[Config]` (absent → None); `ConfigError` on invalid. | ✓ |
| `stow/detect.py` | `detect_stacks(root) -> tuple[str,...]` by repo-root marker files over `REGISTRY`, registry order (`base` excluded — always-on). Intentionally parallel to `rigging/detect.py`. | ✓ |
| `stow/scaffold.py` | Skill seam (reads fs via pathlib only; AST-pure). `MANAGED_FILES = [".gitignore"]`; `classify_files`; `propose_config(signals) -> dict` (guaranteed to load via `load_config`, `ValueError` naming a bad field); `desired_sections(config) -> [BASE] + REGISTRY specs for config.stacks in registry order`. | ✓ |
| `skills/init/SKILL.md` | `stow:init`. Frontmatter exactly `name`+`description`, `name == "init"`. | — |
| `.claude-plugin/plugin.json` | Manifest: name `stow`, version `0.1.0`, keywords `[gitignore, scaffold, baseline]`. | — |
| `tests/` | pytest suite. **No `tests/__init__.py`** (a package-named tests dir shadows same-basename sibling test files under `--import-mode=importlib`). Added to `pytest.ini`. | — |

## The config file: `.stow.json`

Committed, camelCase, validated by `config.load_config` (returns `Config | None`,
raises `ConfigError` on anything invalid). Single top-level key `stacks`: a JSON
object keyed by registry stack id (`python`, `node`), value `{}` or `null` (reserved
for future per-stack options). `base` is always applied and is NOT a legal key
(rejected as unknown, exactly as rigging rejects unknowns). Unknown id / non-object
`stacks` / wrong value type → `ConfigError` naming the field. It is a `dict` (not a
list) so `config.py` is a near-copy of rigging's validator and the per-stack options
seam stays open.

Why commit it: it is the durable **record** of which sections this repo opted into —
which detection can't recover on a repo with no marker files (like shipyard), and
which the dogfood keys off — exactly as shipyard already commits `.rigging.json`.

Example: `{"stacks": {"python": {}}}`

## Stacks & files (increment 1)

`base` (always-on, universal OS cruft), `python`, `node` — the same two language
stacks rigging ships, detected by the same marker files, so a repo rigging can CI,
stow can outfit. File: **`.gitignore` only**. A polyglot repo gets `base` + `python`
+ `node` blocks composed into one file (base first, then registry order).

## Safety analog (rigging's injection test, adapted)

The parser-integrity guarantee: **no registry body line may contain a newline or
match the stow marker regex**, so stow can never emit a body that breaks its own
parser. A `test_stacks.py` assertion pins this — the analog of rigging's injection
test and keel's purity test.

## Dogfood

shipyard adopts stow against its own repo: commit `.stow.json = {"stacks":
{"python": {}}}` and rewrite shipyard's `.gitignore` so `.superpowers/` stays a
**free** line above the markers while its standard lines move into a `stow:base`
block (`.DS_Store`, `Thumbs.db`) and a `stow:python` block (the registry python
body). Since shipyard has no root marker files, `detect_stacks(REPO) == ()`, so the
dogfood is **config-driven** via `load_config(REPO)`, exactly like rigging's.

`test_dogfood.py` asserts byte-for-byte that stow is a **no-op** on its own committed
file: `apply_blocks(read(".gitignore"), desired_sections(load_config(REPO))) ==
read(".gitignore")`. That one assertion is a two-in-one guard: it fails if any
managed block drifted from the current registry body (the central-update integrity
guard, the analog of rigging's `render == committed`), and it proves the round-trip
preserves `.superpowers/` (outside every block, untouched by construction). A second
assertion pins that `.superpowers/` falls in no block returned by `find_blocks`.

## Distribution

stow is added to `.claude-plugin/marketplace.json` (`source ./plugins/stow`,
category `workflow`), version `0.1.0`.

## Scope

**In scope (increment 1):** the pure `config → detect → desired_sections → blocks`
engine, the managed-block splice for `.gitignore`, the `base/python/node` registry,
`.stow.json`, the `stow:init` skill, the parser-integrity guarantee, the dogfood, and
marketplace registration. Version `0.1.0`.

**Deferred to later increments:**
- `.editorconfig` (managed-block too, but needs the `root = true` first-line ordering
  solved) and `.gitattributes`.
- Stacks beyond `base/python/node` (rust, go, java, php, ruby…) — pure registry-data
  additions on the `StackSpec` seam.
- Per-stack config options (the reserved `{}` value), a `files` config key, per-file
  opt-out.
- Editor/IDE ignores (`.idea/`, `.vscode/`) — `base` kept to uncontroversial OS cruft
  so always-on is safe.
- Dedicated `stow:update`/`stow:remove` skills — re-running `init` already updates,
  and dropping a stack + re-running already removes its block declaratively.
- A dry-run/diff-preview mode; CRLF/line-ending preservation; an advisory hook for
  hand-edits inside a block; cross-block dedup of shared entries; auto-migration of a
  plain pre-existing `.gitignore`'s standard lines into managed blocks (first adoption
  is a hand-curated maintainer step, as the dogfood does).
