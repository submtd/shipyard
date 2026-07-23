#!/usr/bin/env python3
"""Propagate action-pin bumps from the generated workflows back into the
registries that generate them, then regenerate every dogfooded artifact.

Why this exists
---------------
`.github/workflows/ci.yml` and `security.yml` are *rendered output*. Their
source of truth is:

    plugins/rigging/rigging/plan.py     actions/checkout
    plugins/rigging/rigging/stacks.py   actions/setup-python, actions/setup-node
    plugins/hull/hull/plan.py           actions/checkout
    plugins/hull/hull/scanners.py       gitleaks/gitleaks-action

Dependabot does not know that. It edits the rendered workflow and leaves the
registry untouched, so the byte-identity dogfood tests fail immediately and
its PR can never go green on its own:

    plugins/rigging/tests/test_dogfood.py   render(build_plan(cfg)) == committed
    plugins/hull/tests/test_dogfood.py      _rendered() == committed
    plugins/keel/tests/test_templates.py    templates/changelog.yml == live copy

That is the correct behaviour -- the guarantee those tests protect is real --
but it makes a Dependabot PR a dead end without this script. Run it on such a
branch and the PR becomes mergeable:

    python3 scripts/sync_action_pins.py
    git commit -am "chore(deps): sync action pins into the registries"

Stdlib only, no imports from the plugins: it edits their source text, so it
must not depend on importing them mid-edit.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

#: Where each action's pin is authored. One action can appear in several
#: registries (checkout is used by both rigging and hull) and every copy must
#: move together -- a split pin renders two different SHAs for the same
#: action, which is how a supply-chain guarantee quietly stops being one.
REGISTRY_FILES = [
    "plugins/rigging/rigging/plan.py",
    "plugins/rigging/rigging/stacks.py",
    "plugins/hull/hull/plan.py",
    "plugins/hull/hull/scanners.py",
]

#: Generated artifacts Dependabot may have edited, in the order it finds them.
WORKFLOW_FILES = [
    ".github/workflows/ci.yml",
    ".github/workflows/security.yml",
    ".github/workflows/changelog.yml",
]

#: changelog.yml is hand-authored, not rendered, but exists twice with a
#: drift guard -- so a bump to the live copy must be mirrored here.
TEMPLATE_FILES = [
    ("plugins/keel/templates/changelog.yml", ".github/workflows/changelog.yml"),
]

#: `owner/repo@<40-hex>` optionally followed by a `# vN` comment.
#:
#: The optional `["']?` before the comment is load-bearing: rendered
#: workflows quote the scalar (`- uses: "owner/repo@<sha>"  # v7`) while
#: hand-authored ones do not (`- uses: owner/repo@<sha> # v7`). Without it
#: the tag is silently missed in exactly the generated files this script
#: exists to read, and any action appearing only there -- gitleaks, today --
#: would keep a stale `*_version` constant while its SHA moved.
PIN_RE = re.compile(
    r"(?P<repo>[A-Za-z0-9._-]+/[A-Za-z0-9._-]+)@(?P<sha>[0-9a-f]{40})"
    r"(?P<quote>[\"']?)"
    r"(?P<comment>\s*#\s*(?P<tag>v[0-9][^\s\"']*))?"
)

#: The `*_version` constant carrying a pin's human-readable tag. It sits on
#: its own line beside the ref, so it is matched separately and rewritten
#: only near the pin it belongs to.
#: Matches any `*_version` / `*_VERSION` assignment of a `"vN"` string --
#: `uses_version`, `setup_uses_version`, `action_ref_version`, and module
#: constants like hull's `CHECKOUT_VERSION`. Listing the names explicitly
#: missed the last of those, so hull's checkout tag silently stayed stale
#: while its SHA moved.
VERSION_RE = re.compile(r'((?:\w*_version|\w*_VERSION)\s*=\s*)"v[0-9][^"]*"')

#: How far below a pin to look for its version constant.
VERSION_LOOKAHEAD = 4


def pins_in(text):
    """Map action repo -> (sha, tag or None) for every pin in `text`."""
    found = {}
    for m in PIN_RE.finditer(text):
        found[m.group("repo")] = (m.group("sha"), m.group("tag"))
    return found


def read(rel):
    return (REPO / rel).read_text(encoding="utf-8")


def write(rel, text):
    (REPO / rel).write_text(text, encoding="utf-8")


def collect_desired():
    """The pin each action should have, taken from the workflow files.

    Conflicting pins for one action are an error rather than a
    last-one-wins guess: it means a partial bump, and picking a winner
    silently would leave the other copy stale.
    """
    desired = {}
    for rel in WORKFLOW_FILES:
        for repo, (sha, tag) in pins_in(read(rel)).items():
            if repo in desired and desired[repo][0] != sha:
                raise SystemExit(
                    f"conflicting pins for {repo}: {desired[repo][0]} and "
                    f"{sha}. The workflows disagree -- fix them before syncing."
                )
            if repo not in desired or (tag and not desired[repo][1]):
                desired[repo] = (sha, tag)
    return desired


def rewrite_registries(desired):
    """Point every registry pin at the desired sha, moving its tag with it.

    Line-oriented on purpose. A whole-file regex got this wrong twice, both
    times silently:

    * the closing quote of `uses="owner/repo@<sha>"` was consumed by the
      match and dropped by the replacement, leaving an unterminated string
      -- a SyntaxError, so the plugin stopped importing entirely;
    * rewriting `*_version` constants file-wide once per action set every
      constant in a file to whichever action was processed last, so
      checkout's tag ended up as gitleaks'.

    So: rewrite each pin in place preserving its quoting, and update only
    the version constant within VERSION_LOOKAHEAD lines below that pin.
    """
    changes = []
    for rel in REGISTRY_FILES:
        lines = read(rel).split("\n")
        original = list(lines)
        for i, line in enumerate(lines):
            m = PIN_RE.search(line)
            if not m or m.group("repo") not in desired:
                continue
            sha, tag = desired[m.group("repo")]
            replacement = f"{m.group('repo')}@{sha}{m.group('quote')}"
            if m.group("comment"):
                replacement += f"  # {tag}" if tag else m.group("comment")
            lines[i] = line[:m.start()] + replacement + line[m.end():]
            if not tag:
                continue
            for j in range(i, min(i + VERSION_LOOKAHEAD, len(lines))):
                if VERSION_RE.search(lines[j]):
                    lines[j] = VERSION_RE.sub(
                        lambda mm: f'{mm.group(1)}"{tag}"', lines[j], count=1)
                    break
        if lines != original:
            write(rel, "\n".join(lines))
            changes.append(rel)
    return changes


def mirror_templates():
    changed = []
    for template, live in TEMPLATE_FILES:
        if read(template) != read(live):
            write(template, read(live))
            changed.append(template)
    return changed


def regenerate():
    """Re-render every dogfooded artifact and golden from the registries."""
    script = r"""
import sys
sys.path.insert(0, "plugins/rigging"); sys.path.insert(0, "plugins/hull")
from pathlib import Path
from rigging.config import Config as RC, StackConfig as RSC, ResolvedService as RS, load_config as rload
from rigging.plan import build_plan as rplan
from rigging.render import render as rrender
from rigging.stacks import NODE_PACKAGE_MANAGERS, DEFAULT_NODE_PACKAGE_MANAGER
from hull.config import Config as HC, load_config as hload
from hull.plan import build_plan as hplan
from hull.render import render as hrender

open(".github/workflows/ci.yml", "w").write(rrender(rplan(rload(Path(".")))))
open(".github/workflows/security.yml", "w").write(hrender(hplan(hload(Path(".")))))

goldens = {
    "python.yml":   RC(name="ci", stacks={"python": RSC(versions=("3.9", "3.12"))}),
    "polyglot.yml": RC(name="ci", stacks={"python": RSC(versions=("3.12",)), "node": RSC(versions=("20",))}),
    "node-testcommand.yml": RC(name="ci", stacks={"node": RSC(versions=("20",), test_command=("turbo", "run", "test", "--concurrency=1"))}),
    "python-testcommand.yml": RC(name="ci", stacks={"python": RSC(versions=("3.12",), test_command=("pytest", "-q"))}),
    "node-postgres.yml": RC(name="ci", stacks={"node": RSC(
        versions=("20",),
        services=(RS(service_id="postgres", version="16", url_env="TEST_DATABASE_URL"),))}),
    "node-redis.yml": RC(name="ci", stacks={"node": RSC(
        versions=("20",),
        services=(RS(service_id="redis", version="7", url_env="REDIS_URL"),))}),
}
# One golden per registered node package manager, derived from the registry
# rather than hardcoded -- npm keeps the plain "node.yml" name (it is the
# default, selected by omitting packageManager entirely, matching how a
# bare package.json actually resolves); every other manager gets
# "node-<id>.yml". Deriving this from NODE_PACKAGE_MANAGERS means a future
# manager's golden is regenerated automatically instead of silently going
# stale the way pnpm/yarn/bun's did before this fix.
for manager_id in NODE_PACKAGE_MANAGERS:
    if manager_id == DEFAULT_NODE_PACKAGE_MANAGER:
        fn = "node.yml"
        stack = RSC(versions=("20",))
    else:
        fn = f"node-{manager_id}.yml"
        stack = RSC(versions=("20",), package_manager=manager_id)
    goldens[fn] = RC(name="ci", stacks={"node": stack})

for fn, cfg in goldens.items():
    open("plugins/rigging/tests/golden/" + fn, "w").write(rrender(rplan(cfg)))

open("plugins/hull/tests/golden/security.yml", "w").write(
    hrender(hplan(HC(name="security", scanner="gitleaks"))))
"""
    subprocess.run([sys.executable, "-c", script], cwd=REPO, check=True)


def main():
    desired = collect_desired()
    if not desired:
        print("no action pins found in the workflows -- nothing to sync")
        return 0
    print("pins found in the workflows:")
    for repo, (sha, tag) in sorted(desired.items()):
        print(f"  {repo}@{sha[:10]}  {tag or '(no version comment)'}")

    changed = rewrite_registries(desired) + mirror_templates()
    regenerate()

    if changed:
        print("\nupdated:")
        for c in changed:
            print("  ", c)
    print("\nregenerated the workflows and goldens from the registries.")
    print("Run the suite to confirm: python3 -m pytest -q")
    return 0


if __name__ == "__main__":
    sys.exit(main())
