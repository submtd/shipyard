---
name: init
description: Use to set up secret scanning in a repository via hull - proposes a .hull.json and scaffolds an injection-safe GitHub Actions workflow (gitleaks or trufflehog), never overwriting existing files.
---

# Initialising hull in a repo

This scaffolds the **secret-scanning** layer only: a `.hull.json` config and
one rendered GitHub Actions workflow that runs a secret scanner (`gitleaks`
by default, or `trufflehog` — see section 3) on push and pull request. It
does not touch
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
  fresh-scaffold flow: section 2, then section 3, then section 4.
- **`.hull.json` exists and loads** (prints a `Config(...)`) — go to section
  2 (the precondition check still applies — a config that loads can still be
  one that cannot pass CI), then skip to section 4, already-configured mode,
  using the loaded `Config`'s `name` (and `scanner`) as-is. Do NOT run
  section 3's `propose_config` in this
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
Secret scanning is stack-agnostic — either scanner scans the repo's git
history and working tree for credential-shaped strings regardless of what
language or framework the code is written in — so there is nothing to
detect.

## 2. Check the preconditions before writing anything

This section runs **before** `.hull.json` or any workflow file is written,
and it is the one section whose answer can stop the whole flow. It exists
because of a failure mode that is worse than an error: `hull:init` used to
happily commit a workflow that **could never go green**, and said nothing.
`gitleaks/gitleaks-action` v3 checks the repository owner's account type at
startup, and if the owner is a GitHub **Organization** and `GITLEAKS_LICENSE`
is unset it **exits 1 before scanning a single commit** — public or private
makes no difference. The adopter then gets a permanently red required check
whose message is about licensing, in a file hull wrote, for a repo whose code
is fine. Discovering that on a pull request, days later, is the expensive way
to learn it; discovering it here costs one `gh` call.

hull's engine is pure — it runs no `gh`, opens no sockets, and shells out to
nothing — so **this skill** does the lookup and passes the answer in as a
signal:

    gh repo view --json owner -q .owner.type

That prints `Organization` or `User`. **Pass whichever it printed through
verbatim** — those two strings and `None` are the only values
`check_preconditions` accepts, and it raises `ValueError` on anything else,
including a lower-cased `organization` or an abbreviated `org`. That
strictness is deliberate: the organization blocker fires on an exact match, so
a near-miss quietly read as "not an organization" would return a clean result
while leaving the guard switched off — and there would be nothing on disk
afterwards to notice it by.

The lookup can also fail: no remote configured
yet, `gh` not authenticated, or offline. **A failed lookup is not a blocker** —
treat it as unknown and pass `None`. Refusing to scaffold because a network
call failed would make hull unusable on a brand-new repo, which is exactly
where you most want it before the first secret gets committed. Say plainly
that you could not determine the owner type, and carry on.

Feed the result — together with the `scanner` and `licenseSecret` you are
about to propose in section 3 — into `hull.scaffold.check_preconditions`:

    python3 -c "
    import sys, json
    sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}')
    from hull.scaffold import check_preconditions
    signals = {'ownerType': 'Organization', 'scanner': 'gitleaks'}
    result = check_preconditions(signals)
    print(json.dumps({'blockers': list(result.blockers),
                      'advisories': list(result.advisories)}, indent=2))
    "

(substitute the real `ownerType`; drop the key entirely, or set it to `None`,
when the lookup failed. Add `'licenseSecret': '<NAME>'` if the user has
already told you the secret's name, or if you are in already-configured mode
and the loaded `Config` has one — otherwise the guard will correctly conclude
that no license is being supplied.)

The two return channels mean different things and must be handled
differently — that is why they are separate rather than one list of strings:

- **`blockers` is non-empty** — **refuse to scaffold.** Show every blocker
  **verbatim** (it already names the cause, the exit code, and both remedies;
  paraphrasing it loses the part the user needs to act on) and **stop here**.
  Do not write `.hull.json`, do not render a workflow, do not offer to
  proceed anyway. A workflow that cannot pass is worse than no workflow: it
  trains the team to ignore a red secret-scan check, which is the one check
  you never want ignored. The user's way forward is in the message — obtain
  the free license key, add it as a repository or organization Actions secret,
  and re-run `hull:init` telling you the secret's name so it lands in
  `licenseSecret` — or re-run `hull:init` choosing `"trufflehog"`, which has
  no license gate at all. That second remedy is new; before it, the registry
  had one entry and the blocker's own message named nothing.
- **`advisories` is non-empty** — these are **not** blockers. Report them
  alongside a successful init, never instead of one. Which one you get
  depends on the scanner: `gitleaks` returns the fork-PR caveat described in
  section 3 under `licenseSecret`, and `trufflehog` returns the
  `BASE == HEAD` one. Neither scanner returns both — the fork-PR advisory is
  about a secret being withheld, and `trufflehog` reads no secret.

`check_preconditions` raises `ValueError` naming the key on an unrecognised
signal — including a near-miss like `owner_type` for `ownerType`, which would
otherwise look configured while silently disabling the guard. Surface that
message rather than reinterpreting it.

## 3. Propose the config

*(Fresh-scaffold flow only — you're here because section 1 found no
`.hull.json` and section 2 came back with no blockers.)*

Build a signals dict and ask the user only for what you cannot infer:

- `name` — optional; defaults to `"security"` inside `propose_config`. This
  becomes both the workflow's `name:` and the filename
  `.github/workflows/<name>.yml`, so ask if the repo already has a
  convention here. **If the user asks for a `name` that is any case variant
  of `"ci"` (compare with `name.lower() == "ci"` — so `"ci"`, `"CI"`, `"Ci"`,
  `"cI"` all match), warn them before proceeding**: `.github/workflows/ci.yml`
  is the conventional filename `rigging:init` scaffolds for the test-CI
  workflow, and `config.NAME_RE` accepts any of those case variants, so
  picking one for hull risks a filename collision with rigging's `ci.yml` —
  outright (on a case-sensitive filesystem, e.g. Linux/CI, `CI.yml` and
  `ci.yml` coexist as distinct files, which then collides for any teammate on
  a case-insensitive filesystem, e.g. macOS/Windows, checking out both) or via
  the no-clobber stop in section 4 below (exact-case match). Confirm they
  still want that name (e.g. because they've deliberately renamed rigging's
  workflow elsewhere) before using it.
- `scanner` — optional; defaults to `"gitleaks"` inside `propose_config`.
  Two are registered, and the choice is real:
  - **`gitleaks`** (default) — the incumbent. Requires a free
    `GITLEAKS_LICENSE` for **organization-owned** repos, public or private
    alike; section 2 refuses to scaffold without one. Needs
    `pull-requests: read` in addition to `contents: read`, because it
    enumerates a pull request's commits through the API.
  - **`trufflehog`** — no license, no secret of any kind, and only
    `contents: read`. AGPL 3.0, and it runs as a CI step against the repo
    rather than being linked into anything the project ships, so its licence
    does not reach the consuming codebase. Reports `verified` and `unknown`
    findings (not `unverified`). This is the answer when section 2 reports
    the organization blocker and the user does not want to obtain a licence.

  Both are pinned to an immutable SHA and both are byte-identity tested.
  You only reach this section once section 2 came back with no blockers, so
  there is no live blocker to ask about here — if the organization blocker
  fired, section 2 already stopped the flow, and the way forward is the one
  its message states: the *user* re-runs `hull:init`, this time naming
  `"trufflehog"` as the scanner (or supplying `licenseSecret`), and section 3
  is reached again on that fresh run. Absent that, take the default.
- `pushBranches` — optional, defaults to `["main"]`. Pull requests always
  trigger the scan, so `push` is restricted to the long-lived branches;
  without that, every PR raised from a branch in the same repo scans twice.

  List **every long-lived branch**, not just the default. Under gitflow that
  is production *and* integration (`["main", "develop"]`) — most merges land
  on `develop`, so omitting it means the scan never runs on the branch the
  team integrates into. **Check the repo's actual default branch**
  (`git symbolic-ref --short refs/remotes/origin/HEAD`) and set this when it isn't `main` — a repo on
  `master` that takes the default gets no push scan at all, and nothing says
  so. Use the same value rigging's `.rigging.json` has, if it exists.
- `licenseSecret` — optional, defaults to absent. The **name** of the GitHub
  Actions secret holding the scanner's license key — never the key itself.
  hull never sees, stores, or transmits key material; it renders
  `GITLEAKS_LICENSE: "${{ secrets.<licenseSecret> }}"` into the scan step's
  `env` and lets GitHub resolve it at run time. Set this whenever section 2
  reported the organization blocker, and whenever the repo already has such a
  secret. The secret's name is the repo's choice and need not match the
  environment variable — an org that already stores the key as
  `ORG_GITLEAKS_KEY` sets `"licenseSecret": "ORG_GITLEAKS_KEY"` and hull wires
  it to `GITLEAKS_LICENSE` for them.

  This value is validated far more strictly than anything else in
  `.hull.json` (`^[A-Za-z_][A-Za-z0-9_]*$`), because it is the only config
  string that lands inside a GitHub Actions **expression** rather than merely
  inside a quoted YAML scalar. A name containing a brace, a quote, a dot, a
  dash or whitespace is refused outright — such a value could close hull's
  `${{ ... }}` and open its own, or break out of the surrounding scalar. Real
  GitHub secret names are a subset of the accepted pattern, so nothing a user
  could actually have created is being turned away.

  **Fork pull requests cannot read this secret, and that is by design.**
  GitHub withholds repository and organization secrets from `pull_request`
  runs whose head is a fork, so an untrusted contributor cannot exfiltrate
  them. `GITLEAKS_LICENSE` therefore arrives empty on a fork PR and the
  gitleaks job fails on those PRs **even with a valid license configured**.
  If the repo takes fork contributions (keel's `contributions` set to
  `"fork"` or `"both"`), tell the user to expect that red check and to treat
  it as expected rather than as a hull bug or a leaked-secret finding — and,
  in particular, **not** to make this job a required check for fork PRs.
  There is no configuration that fixes it; it is a property of the platform's
  secret model.

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
(rename, though not to any case variant of `ci` without the warning above),
adjust the signals dict and re-show — don't write anything until they've
approved what's on screen.

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

Continue to section 4 to render the workflow.

## 4. Write the workflow (no-clobber)

*(Reached from section 1's already-loads branch, or from section 3 just
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

Continue to section 5 to verify and report either way.

## 5. Verify and report

Prove what's on disk is sound:

- Reload the config — must print a `Config(...)`, not raise:

      python3 -c "import sys; sys.path.insert(0, '${CLAUDE_PLUGIN_ROOT}'); from hull.config import load_config; from pathlib import Path; print(load_config(Path('.')))"

- Re-render from that config and confirm no attacker-reachable expression
  survived into the workflow — hull's core injection-safety property, proven
  two ways:

  1. Every `- run:` step body (via `render.iter_run_blocks`) must be free of
     `${{`. (Neither registered scanner has a `run` step — both gitleaks and
     trufflehog are a single `uses:` action — so today this list is always
     empty; the check stays in place for the day a future scanner adds one.)
  2. Every `${{ ... }}` expression that appears **anywhere** in the rendered
     output must be a bare `${{ secrets.<NAME> }}` lookup — nothing else,
     and never a `github.*` context reference. This is the load-bearing
     assertion, not assertion 1: gitleaks's step does carry a
     `${{ secrets.GITHUB_TOKEN }}` env value (and a second
     `${{ secrets.<licenseSecret> }}` one when a license is configured), so
     this is what actually proves nothing wider (like
     `${{ github.event.issue.title }}`, or a hostile `name` or
     `licenseSecret`) ever reaches the emitted YAML. The secret-name pattern
     below is the same one `config.SECRET_NAME_RE` enforces on the way in,
     which is why the check can be this narrow.

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
      whitelist = re.compile(r'[$]\{\{\s*secrets\.[A-Za-z_][A-Za-z0-9_]*\s*\}\}')
      bad_expr = [e for e in exprs if not whitelist.fullmatch(e)]
      assert not bad_expr, bad_expr
      assert 'github.' not in text
      print('ok: no \${{ in any run block; every \${{ }} expression is a bare secrets.<NAME> lookup')
      "

Report: what you created, what you skipped (and why), the confirmed config,
and the verification result.

**Repeat the licensing situation in the report**, even though section 2
already covered it — it is the single most likely cause of a red job that has
nothing to do with the repo's code, and the person reading the final report is
not always the person who answered section 2's questions:

- `gitleaks/gitleaks-action` requires a free `GITLEAKS_LICENSE` for repos
  owned by a GitHub **organization** account, public or private alike; repos
  owned by a **personal** account need none. Section 2 refuses to scaffold
  when that license is missing on an org-owned repo, so if you got this far
  either the owner is a personal account, or `licenseSecret` is configured,
  or the owner type could not be determined — say **which** of the three, so
  the user knows whether a red job is expected.
- Report every advisory `check_preconditions` returned, verbatim. Which one
  you get depends on the scanner (same as section 2): `gitleaks` returns the
  fork-PR one — **fork pull requests cannot read repository or organization
  secrets**, so the gitleaks job fails on fork PRs even with a valid license.
  There is no config that changes this — it is how GitHub protects secrets
  from untrusted contributors — so a repo taking fork contributions (keel's
  `contributions` of `"fork"` or `"both"`) should not make this a required
  check for fork PRs. `trufflehog` returns the `BASE == HEAD` one instead —
  rare, and not a finding or a hull bug when it happens. Neither scanner
  returns both.

Point the user at:

- `rigging:init` — the sibling layer that authors the test-CI workflow
  (`.rigging.json`, `.github/workflows/ci.yml` by default). hull does not
  own that file; it only guards against a filename collision with it (see
  section 3's warning on any case variant of `name: "ci"`).
- `ballast:init` — the test-runner config layer (`.ballast.json`,
  `pytest.ini`) that rigging's workflow actually runs.
- `stow:init` — baseline repo hygiene (`.stow.json`, managed `.gitignore`
  sections).
- `keel:init` — the git-lifecycle layer (`.keel.json`, changelog, PR/issue
  templates, CODEOWNERS, the changelog CI gate).

Note what's deliberately **not** here yet — later hull increments, not gaps
in this one:

- scanners beyond `gitleaks` and `trufflehog` (`hull.scanners.SCANNER_IDS`
  has exactly two entries today)
- **creating** the license secret itself. hull now renders it through
  (`licenseSecret`, section 3) and refuses to scaffold without it on an
  org-owned repo (section 2), but actually storing the key — `gh secret set
  GITLEAKS_LICENSE` or the repo's Settings UI — is a privileged, one-time
  human action that neither a rendered workflow file nor a pure engine can
  perform, and hull deliberately never handles key material.
- anything that would make the gitleaks job pass on a **fork** pull request.
  Secrets are withheld from fork runs by GitHub's design; the only workarounds
  (`pull_request_target`, or a second workflow that re-runs the scan with
  secrets after review) hand a trusted token to untrusted code, which is not a
  trade hull will make on a user's behalf.
- configurable triggers (today's workflow is always
  `on: [push, pull_request]`), including a scheduled or manually-dispatched
  full-history sweep — see the adoption note below
- scan-scope configuration (path allow/deny lists, custom gitleaks rules) —
  today's job runs the configured scanner with its own defaults
- migrating or reconciling a pre-existing, foreign workflow file at
  `.github/workflows/<name>.yml`
- an interactive edit path for an existing `.hull.json` (increment 1's only
  ways to change it are hand-editing the file and re-running `hull:init` to
  pick up the new workflow, or deleting the workflow file first if you want
  it re-rendered)

## Adoption: scan the existing history once, by hand

Say this to the user plainly when `hull:init` finishes on a repo that
already has commits. The rendered workflow triggers on `push` and
`pull_request`, and both scanners only scan the *commit range of the event*
— that's what `fetch-depth: 0` is there to make possible. So the very run
triggered by the commit that adds `security.yml` scans only that commit,
whichever scanner you chose.

The consequence is worth being explicit about, because the green check is
misleading: **a secret committed before adoption is not found by this
workflow.** The repo shows a passing secret-scan and has never actually
been scanned.

Recommend a one-time sweep over the full history at adoption, with the
scanner you scaffolded:

    gitleaks detect --source . --redact

or, for trufflehog:

    trufflehog git file://. --results=verified,unknown

(both walk full git history; the workflow's per-event range scan does not.)
If either finds anything, rotating the credential is the first step —
rewriting history does not un-leak a secret that has already been pushed.
