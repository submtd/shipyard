# keel Git Lifecycle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build `keel`, a Claude Code plugin that guides a project's git lifecycle — starting work, landing it, shipping it — via a rule engine, an advisory hook, and ten skills.

**Architecture:** A pure, side-effect-free rule engine (`config` → `actions` → `facts` → `rules` → `render`) sits behind two thin hook entrypoints. All I/O (git, `gh`) is isolated in two modules so the engine is fully table-testable. Rules key on `(action, base, head, headIsFork, capability)` — there is no role concept.

**Tech Stack:** Python 3.10+, stdlib only (no third-party runtime deps). pytest for tests. GitHub Actions for CI.

## Global Constraints

- **Runtime dependencies: stdlib only.** No `bashlex`, no `requests`, no `pyyaml`. Tests may use pytest.
- **Python 3.9+.** The hook runs under whatever `python3` is on the user's PATH, which is
  commonly 3.9 (it is on the author's machine). Every module that uses `X | None` annotation
  syntax MUST begin with `from __future__ import annotations`. Do not use `match`, and do not
  use `X | Y` outside an annotation context (e.g. not in `isinstance`).
- **The hook is advisory, not a security control.** Never add adversarial shell parsing. Correct *messages* matter; total coverage does not.
- **One fail policy: `unknown` → warn, never block.** Applied uniformly, no exceptions.
- **Every `subprocess.run` call MUST pass `timeout=`.** No exceptions.
- **No network call may be made more than once per concern per invocation.** Batch `gh --json` fields; cache per PR number.
- **The engine modules (`config`, `actions`, `rules`, `render`) must not import `subprocess`.** I/O lives only in `gitio.py` and `ghio.py`. This is what makes the engine testable.
- Plugin manifest path is exactly `.claude-plugin/plugin.json`. Marketplace manifest is exactly `.claude-plugin/marketplace.json`.
- Skill frontmatter uses **only** `name` and `description`. Do not add `tools:` or `allowed-tools:` — the correct field name is unverified (see Task 12).
- Repo root is `~/Development/submtd/shipyard`, already a git repo on branch `main` with one commit.

---

## File Structure

```
shipyard/                                    # marketplace repo root
├── .claude-plugin/
│   └── marketplace.json                     # lists keel; siblings later
├── .github/workflows/ci.yml                 # runs pytest
├── README.md
└── plugins/keel/
    ├── .claude-plugin/plugin.json
    ├── hooks/
    │   ├── hooks.json                       # registers both hooks
    │   ├── guard.py                          # PreToolUse entrypoint
    │   └── orient.py                         # SessionStart entrypoint
    ├── keel/                                 # the engine (pure)
    │   ├── __init__.py
    │   ├── config.py                         # .keel.json -> Config
    │   ├── actions.py                        # command string -> [Action]
    │   ├── facts.py                          # Tri, Facts dataclasses
    │   ├── rules.py                          # (Action, Facts, Config) -> Verdict
    │   ├── render.py                         # Verdict -> hook JSON
    │   ├── gitio.py                          # git subprocess I/O
    │   └── ghio.py                           # gh subprocess I/O + cache
    ├── skills/                               # 10 skills, one dir each
    └── tests/
        ├── test_config.py
        ├── test_actions.py
        ├── test_rules.py
        ├── test_render.py
        ├── test_gitio.py
        └── test_ghio.py
```

**Responsibility boundaries.** `actions.py` answers "what is this command trying to do." `facts.py` answers "what is true about the world." `rules.py` answers "is that allowed." `render.py` answers "how do we say so." Each is independently testable; only `gitio`/`ghio` touch the system.

---

### Task 1: Repo skeleton, plugin manifest, and CI

Establishes an installable plugin and a green test run, so every later task has a working harness.

**Files:**
- Create: `.claude-plugin/marketplace.json`
- Create: `plugins/keel/.claude-plugin/plugin.json`
- Create: `plugins/keel/keel/__init__.py`
- Create: `plugins/keel/tests/test_smoke.py`
- Create: `pytest.ini`
- Create: `.github/workflows/ci.yml`
- Create: `.gitignore`

**Interfaces:**
- Consumes: nothing.
- Produces: importable package `keel`; `pytest` runnable from repo root.

- [ ] **Step 1: Write the failing test**

`plugins/keel/tests/test_smoke.py`:
```python
def test_package_imports():
    import keel
    assert keel.__version__ == "0.1.0"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest plugins/keel/tests/test_smoke.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel'`

- [ ] **Step 3: Create the package and config**

`plugins/keel/keel/__init__.py`:
```python
__version__ = "0.1.0"
```

`pytest.ini`:
```ini
[pytest]
testpaths = plugins/keel/tests
pythonpath = plugins/keel
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python3 -m pytest -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Add the plugin and marketplace manifests**

`plugins/keel/.claude-plugin/plugin.json`:
```json
{
  "name": "keel",
  "displayName": "keel",
  "version": "0.1.0",
  "description": "Guides a project's git lifecycle: start work, land it, ship it.",
  "license": "MIT",
  "keywords": ["git", "workflow", "release", "changelog"],
  "hooks": "./hooks/hooks.json"
}
```

`.claude-plugin/marketplace.json`:
```json
{
  "name": "shipyard",
  "owner": { "name": "Steve Harmeyer" },
  "description": "Claude Code plugins for project tooling.",
  "plugins": [
    {
      "name": "keel",
      "source": "./plugins/keel",
      "description": "Guides a project's git lifecycle: start work, land it, ship it.",
      "category": "workflow"
    }
  ]
}
```

`.gitignore`:
```
__pycache__/
*.py[cod]
.pytest_cache/
.DS_Store
```

- [ ] **Step 6: Add CI**

`.github/workflows/ci.yml`:
```yaml
name: ci
on:
  push:
    branches: [main, develop]
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python }}
      - run: pip install pytest
      - run: python -m pytest -v
    strategy:
      matrix:
        python: ["3.9", "3.12"]
```

- [ ] **Step 7: Commit**

```bash
git add .claude-plugin plugins pytest.ini .github .gitignore
git commit -m "feat: plugin skeleton, marketplace manifest, and CI"
```

---

### Task 2: Config loading

**Files:**
- Create: `plugins/keel/keel/config.py`
- Test: `plugins/keel/tests/test_config.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Config` frozen dataclass with fields: `topology: str`, `production: str`, `integration: str`, `feature_prefix: str`, `release_prefix: str`, `hotfix_prefix: str`, `contributions: str`, `review_policy: str`, `merge_to_integration: str`, `merge_to_production: str`, `require_changelog: bool`
  - `ConfigError(Exception)`
  - `load_config(repo_root: pathlib.Path) -> Config | None` — returns `None` when `.keel.json` is absent (repo not keel-managed); raises `ConfigError` when present but invalid.

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_config.py`:
```python
import json
import pytest
from keel.config import load_config, Config, ConfigError


def write(tmp_path, data):
    (tmp_path / ".keel.json").write_text(json.dumps(data))
    return tmp_path


def test_absent_config_returns_none(tmp_path):
    assert load_config(tmp_path) is None


def test_defaults_fill_in(tmp_path):
    cfg = load_config(write(tmp_path, {}))
    assert cfg.topology == "gitflow"
    assert cfg.production == "main"
    assert cfg.integration == "develop"
    assert cfg.review_policy == "review"
    assert cfg.require_changelog is True


def test_trunk_collapses_integration_into_production(tmp_path):
    cfg = load_config(write(tmp_path, {"topology": "trunk"}))
    assert cfg.integration == cfg.production == "main"


def test_explicit_values_win(tmp_path):
    cfg = load_config(write(tmp_path, {
        "branches": {"production": "master", "integration": "dev"},
        "reviewPolicy": "approval",
        "requireChangelog": False,
    }))
    assert cfg.production == "master"
    assert cfg.integration == "dev"
    assert cfg.review_policy == "approval"
    assert cfg.require_changelog is False


def test_malformed_json_raises_loudly(tmp_path):
    (tmp_path / ".keel.json").write_text("{not json")
    with pytest.raises(ConfigError) as e:
        load_config(tmp_path)
    assert ".keel.json" in str(e.value)


def test_unknown_enum_value_raises(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_config(write(tmp_path, {"reviewPolicy": "vibes"}))
    assert "reviewPolicy" in str(e.value)


def test_unknown_topology_raises(tmp_path):
    with pytest.raises(ConfigError):
        load_config(write(tmp_path, {"topology": "octopus"}))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.config'`

- [ ] **Step 3: Implement**

`plugins/keel/keel/config.py`:
```python
"""Load and validate .keel.json. Stdlib only; no subprocess."""
import json
from dataclasses import dataclass
from pathlib import Path

CONFIG_NAME = ".keel.json"

TOPOLOGIES = ("gitflow", "trunk")
CONTRIBUTIONS = ("fork", "branch", "both")
REVIEW_POLICIES = ("approval", "review", "none")
STRATEGIES = ("squash", "merge", "rebase")


class ConfigError(Exception):
    """Raised when .keel.json exists but cannot be used."""


@dataclass(frozen=True)
class Config:
    topology: str
    production: str
    integration: str
    feature_prefix: str
    release_prefix: str
    hotfix_prefix: str
    contributions: str
    review_policy: str
    merge_to_integration: str
    merge_to_production: str
    require_changelog: bool

    @property
    def is_trunk(self):
        return self.topology == "trunk"


def _one_of(value, allowed, field):
    if value not in allowed:
        raise ConfigError(
            f"{CONFIG_NAME}: '{field}' must be one of {', '.join(allowed)} "
            f"(got {value!r})."
        )
    return value


def load_config(repo_root):
    path = Path(repo_root) / CONFIG_NAME
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        raise ConfigError(f"{CONFIG_NAME} could not be read: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"{CONFIG_NAME} must contain a JSON object.")

    branches = raw.get("branches") or {}
    prefixes = raw.get("prefixes") or {}
    strategy = raw.get("mergeStrategy") or {}

    topology = _one_of(raw.get("topology", "gitflow"), TOPOLOGIES, "topology")
    production = branches.get("production", "main")
    integration = production if topology == "trunk" else branches.get("integration", "develop")

    return Config(
        topology=topology,
        production=production,
        integration=integration,
        feature_prefix=prefixes.get("feature", "feature/"),
        release_prefix=prefixes.get("release", "release/"),
        hotfix_prefix=prefixes.get("hotfix", "hotfix/"),
        contributions=_one_of(raw.get("contributions", "both"), CONTRIBUTIONS, "contributions"),
        review_policy=_one_of(raw.get("reviewPolicy", "review"), REVIEW_POLICIES, "reviewPolicy"),
        merge_to_integration=_one_of(
            strategy.get("toIntegration", "squash"), STRATEGIES, "mergeStrategy.toIntegration"),
        merge_to_production=_one_of(
            strategy.get("toProduction", "merge"), STRATEGIES, "mergeStrategy.toProduction"),
        require_changelog=bool(raw.get("requireChangelog", True)),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_config.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add plugins/keel/keel/config.py plugins/keel/tests/test_config.py
git commit -m "feat: .keel.json loading with loud validation failure"
```

---

### Task 3: Action classification

Classifies a Bash command into intents. Deliberately simple — per Global Constraints, this is not adversarial parsing. It must, however, resolve **push destinations from refspecs** and never fabricate actions from quoted text.

**Files:**
- Create: `plugins/keel/keel/actions.py`
- Test: `plugins/keel/tests/test_actions.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `PushRef` frozen dataclass: `src: str | None`, `dst: str`, `is_tag: bool`
  - `Action` frozen dataclass: `kind: str` (one of `"commit"`, `"push"`, `"pr-create"`, `"pr-merge"`), `refs: tuple[PushRef, ...]`, `base: str | None`, `head: str | None`, `pr_number: str | None`, `strategy: str | None`, `repo: str | None`
  - `classify(command: str) -> list[Action]`

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_actions.py`:
```python
import pytest
from keel.actions import classify


def kinds(cmd):
    return [a.kind for a in classify(cmd)]


def test_plain_commit():
    assert kinds("git commit -m 'hello'") == ["commit"]


def test_quoted_separator_does_not_fabricate_actions():
    # Regression: the old guard split on ';' inside the quoted message and
    # invented a phantom push from the commit text.
    assert kinds("git commit -m 'fix; git push origin main'") == ["commit"]


def test_chained_commands_are_each_classified():
    assert kinds("git add -A && git commit -m x") == ["commit"]
    assert kinds("git commit -m x && git push origin feature/a") == ["commit", "push"]


def test_push_destination_from_refspec():
    (a,) = classify("git push origin HEAD:main")
    assert a.kind == "push"
    assert [(r.src, r.dst, r.is_tag) for r in a.refs] == [("HEAD", "main", False)]


def test_push_current_branch_has_no_explicit_dst():
    (a,) = classify("git push origin feature/x")
    assert [(r.src, r.dst) for r in a.refs] == [("feature/x", "feature/x")]


def test_push_with_no_refs_has_empty_refs():
    (a,) = classify("git push")
    assert a.refs == ()


def test_tags_flag_does_not_mark_branch_refs_as_tags():
    # Regression: 'git push origin main --tags' was treated as a pure tag push
    # and allowed for every role.
    (a,) = classify("git push origin main --tags")
    assert [(r.dst, r.is_tag) for r in a.refs] == [("main", False)]


def test_explicit_tag_refspec_is_a_tag():
    (a,) = classify("git push origin refs/tags/v1.2.3")
    assert a.refs[0].is_tag is True


def test_tags_only_push_has_no_branch_refs():
    (a,) = classify("git push origin --tags")
    assert a.refs == ()


def test_pr_create_base_and_head():
    (a,) = classify("gh pr create --base develop --head feature/x --title t")
    assert (a.kind, a.base, a.head) == ("pr-create", "develop", "feature/x")


def test_pr_create_ignores_flag_values_when_finding_subcommand():
    (a,) = classify("gh pr create --repo o/r --base develop --title 'pr create'")
    assert a.kind == "pr-create"
    assert a.repo == "o/r"


def test_pr_merge_number_is_not_a_flag_value():
    # Regression: '--repo o/r' was counted as a positional, so pr_number == 'o/r'.
    (a,) = classify("gh pr merge --squash --repo o/r 5")
    assert (a.kind, a.pr_number, a.strategy) == ("pr-merge", "5", "squash")


def test_pr_merge_short_squash_flag():
    (a,) = classify("gh pr merge 5 -s")
    assert a.strategy == "squash"


def test_pr_merge_unknown_strategy_is_none():
    (a,) = classify("gh pr merge 5")
    assert a.strategy is None


@pytest.mark.parametrize("cmd", [
    "git status",
    "git log --oneline",
    "echo 'git commit -m x'",
    "gh pr view 5",
])
def test_read_only_commands_classify_to_nothing(cmd):
    assert classify(cmd) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_actions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.actions'`

- [ ] **Step 3: Implement**

`plugins/keel/keel/actions.py`:
```python
"""Classify a Bash command string into lifecycle intents.

Deliberately NOT an adversarial parser -- see the plan's Global Constraints.
The goal is to recognise honest commands correctly, never to be unevadable.
Critically, it must not fabricate actions out of quoted text.
"""
import re
import shlex
from dataclasses import dataclass, field

# Flags that consume the following token as their value. Used so that a flag
# value is never mistaken for a positional argument.
GH_VALUE_FLAGS = {
    "--base", "-B", "--head", "-H", "--repo", "-R", "--title", "-t",
    "--body", "-b", "--body-file", "-F", "--reviewer", "-r", "--assignee", "-a",
    "--label", "-l", "--milestone", "-m", "--project", "-p",
    "--subject", "--match-head-commit",
}
GIT_VALUE_FLAGS = {
    "-C", "-c", "--git-dir", "--work-tree", "--namespace",
    "--exec-path", "--super-prefix", "--config-env",
}

TAG_REF = re.compile(r"^refs/tags/")


@dataclass(frozen=True)
class PushRef:
    src: str | None
    dst: str
    is_tag: bool


@dataclass(frozen=True)
class Action:
    kind: str
    refs: tuple = ()
    base: str | None = None
    head: str | None = None
    pr_number: str | None = None
    strategy: str | None = None
    repo: str | None = None


def _segments(command):
    """Split on shell separators, honouring quotes.

    shlex in POSIX mode keeps quoted text intact, so a ';' inside a commit
    message never becomes a separator.
    """
    lexer = shlex.shlex(command, posix=True, punctuation_chars=True)
    lexer.whitespace_split = True
    out, current = [], []
    try:
        for token in lexer:
            if token in ("&&", "||", ";", "|", "&", "\n"):
                out.append(current)
                current = []
            else:
                current.append(token)
    except ValueError:
        # Unbalanced quotes: give up on this command rather than guess.
        return []
    out.append(current)
    return [seg for seg in out if seg]


def _strip_env_prefix(tokens):
    i = 0
    while i < len(tokens) and "=" in tokens[i] and not tokens[i].startswith("-"):
        i += 1
    if i < len(tokens) and tokens[i] == "env":
        i += 1
        while i < len(tokens) and "=" in tokens[i]:
            i += 1
    return tokens[i:]


def _positionals(args, value_flags):
    """Positional args, skipping flags and the values they consume."""
    out, i = [], 0
    while i < len(args):
        a = args[i]
        if a in value_flags:
            i += 2
            continue
        if a.startswith("-"):
            i += 1
            continue
        out.append(a)
        i += 1
    return out


def _flag_value(args, *names):
    for i, tok in enumerate(args):
        for name in names:
            if tok == name and i + 1 < len(args):
                return args[i + 1]
            if tok.startswith(name + "="):
                return tok.split("=", 1)[1]
    return None


def _parse_push(args):
    refs = []
    positionals = _positionals(args, GIT_VALUE_FLAGS)
    # positionals[0] is 'push'; [1] is the remote if present; rest are refspecs.
    for spec in positionals[2:]:
        if ":" in spec:
            src, dst = spec.split(":", 1)
        else:
            src = dst = spec
        # A ref is a tag only when it says so explicitly. '--tags' elsewhere in
        # the command does NOT make a branch refspec a tag.
        is_tag = bool(TAG_REF.match(dst))
        refs.append(PushRef(src=src or None, dst=dst, is_tag=is_tag))
    return Action(kind="push", refs=tuple(refs))


def _classify_segment(tokens):
    rest = _strip_env_prefix(tokens)
    if not rest:
        return None
    prog, args = rest[0], rest[1:]

    if prog == "git":
        sub = next((a for a in _positionals([prog] + args, GIT_VALUE_FLAGS)[1:]), None)
        if sub == "commit":
            return Action(kind="commit")
        if sub == "push":
            return _parse_push([prog] + args)
        return None

    if prog == "gh":
        pos = _positionals(args, GH_VALUE_FLAGS)
        if len(pos) >= 2 and pos[0] == "pr" and pos[1] == "create":
            return Action(
                kind="pr-create",
                base=_flag_value(args, "--base", "-B"),
                head=_flag_value(args, "--head", "-H"),
                repo=_flag_value(args, "--repo", "-R"),
            )
        if len(pos) >= 2 and pos[0] == "pr" and pos[1] == "merge":
            if "--squash" in args or "-s" in args:
                strategy = "squash"
            elif "--merge" in args or "-m" in args:
                strategy = "merge"
            elif "--rebase" in args or "-r" in args:
                strategy = "rebase"
            else:
                strategy = None
            return Action(
                kind="pr-merge",
                pr_number=pos[2] if len(pos) >= 3 else None,
                strategy=strategy,
                repo=_flag_value(args, "--repo", "-R"),
            )
        return None

    return None


def classify(command):
    actions = []
    for seg in _segments(command):
        action = _classify_segment(seg)
        if action is not None:
            actions.append(action)
    return actions
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_actions.py -v`
Expected: PASS (17 passed)

If `test_pr_merge_short_squash_flag` fails, note that `-m` is ambiguous between `--merge` and `--message`; `gh pr merge` has no `--message` short form, so the ordering above is correct.

- [ ] **Step 5: Commit**

```bash
git add plugins/keel/keel/actions.py plugins/keel/tests/test_actions.py
git commit -m "feat: action classification with refspec-aware push parsing"
```

---

### Task 4: Facts and tri-state

**Files:**
- Create: `plugins/keel/keel/facts.py`
- Test: covered by Task 5's rule tests (this task is pure data declarations).

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `Tri` — string enum with members `TRUE`, `FALSE`, `UNKNOWN`
  - `Facts` frozen dataclass: `branch: str | None`, `capability: Tri`, `pr_base: str | None`, `pr_head: str | None`, `pr_is_fork: Tri`, `pr_review_state: str | None`, `changelog_ok: Tri`
  - `Facts.unknown()` classmethod returning an all-unknown instance

- [ ] **Step 1: Implement**

`plugins/keel/keel/facts.py`:
```python
"""Facts about the world. Tri-state throughout; no I/O in this module."""
from dataclasses import dataclass
from enum import Enum


class Tri(str, Enum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"

    @classmethod
    def of(cls, value):
        """Coerce an optional bool into a Tri. None -> UNKNOWN."""
        if value is None:
            return cls.UNKNOWN
        return cls.TRUE if value else cls.FALSE

    def __bool__(self):
        raise TypeError("Tri is three-valued; compare explicitly (x is Tri.TRUE).")


@dataclass(frozen=True)
class Facts:
    branch: str | None = None
    capability: Tri = Tri.UNKNOWN
    pr_base: str | None = None
    pr_head: str | None = None
    pr_is_fork: Tri = Tri.UNKNOWN
    pr_review_state: str | None = None
    changelog_ok: Tri = Tri.UNKNOWN

    @classmethod
    def unknown(cls):
        return cls()
```

Note the deliberate `__bool__` override: it makes `if facts.capability:` a loud error rather than a silent truthiness bug, which is the class of mistake that produced the original guard's inconsistent fail behaviour.

- [ ] **Step 2: Verify it imports**

Run: `python3 -c "import sys; sys.path.insert(0,'plugins/keel'); from keel.facts import Facts, Tri; print(Facts.unknown())"`
Expected: prints a `Facts(...)` repr with all `Tri.UNKNOWN`

- [ ] **Step 3: Commit**

```bash
git add plugins/keel/keel/facts.py
git commit -m "feat: tri-state facts with explicit-comparison enforcement"
```

---

### Task 5: The rule engine

The heart of the plan. Pure function, exhaustively table-tested.

**Files:**
- Create: `plugins/keel/keel/rules.py`
- Test: `plugins/keel/tests/test_rules.py`

**Interfaces:**
- Consumes: `keel.config.Config`, `keel.actions.Action`, `keel.facts.Facts`, `keel.facts.Tri`
- Produces:
  - `Verdict` frozen dataclass: `decision: str` (`"allow"` | `"warn"` | `"block"`), `rule: str`, `message: str`
  - `ALLOW: Verdict` — the shared allow singleton
  - `evaluate(action: Action, facts: Facts, cfg: Config) -> Verdict`

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_rules.py`:
```python
import pytest
from keel.actions import Action, PushRef
from keel.config import Config
from keel.facts import Facts, Tri
from keel.rules import evaluate, Verdict


def cfg(**over):
    base = dict(
        topology="gitflow", production="main", integration="develop",
        feature_prefix="feature/", release_prefix="release/", hotfix_prefix="hotfix/",
        contributions="both", review_policy="review",
        merge_to_integration="squash", merge_to_production="merge",
        require_changelog=True,
    )
    base.update(over)
    return Config(**base)


# --- Rule 1: protected-branch writes -------------------------------------

def test_commit_on_protected_branch_blocks():
    v = evaluate(Action(kind="commit"), Facts(branch="main"), cfg())
    assert v.decision == "block"
    assert v.rule == "protected-write"


def test_commit_on_feature_branch_allows():
    v = evaluate(Action(kind="commit"), Facts(branch="feature/x"), cfg())
    assert v.decision == "allow"


def test_commit_on_unknown_branch_warns_not_blocks():
    v = evaluate(Action(kind="commit"), Facts(branch=None), cfg())
    assert v.decision == "warn"


def test_push_to_protected_destination_blocks_from_feature_branch():
    # Regression: 'git push origin HEAD:main' was allowed because only the
    # current branch was checked.
    action = Action(kind="push", refs=(PushRef("HEAD", "main", False),))
    v = evaluate(action, Facts(branch="feature/x"), cfg())
    assert v.decision == "block"
    assert v.rule == "protected-write"


def test_push_to_feature_destination_allows():
    action = Action(kind="push", refs=(PushRef("feature/x", "feature/x", False),))
    assert evaluate(action, Facts(branch="feature/x"), cfg()).decision == "allow"


def test_pure_tag_push_allows():
    action = Action(kind="push", refs=(PushRef(None, "refs/tags/v1.0.0", True),))
    assert evaluate(action, Facts(branch="main"), cfg()).decision == "allow"


def test_mixed_tag_and_protected_branch_push_blocks():
    # Regression: 'git push origin main --tags' bypassed everything.
    action = Action(kind="push", refs=(
        PushRef("main", "main", False),
        PushRef(None, "refs/tags/v1.0.0", True),
    ))
    v = evaluate(action, Facts(branch="main"), cfg())
    assert v.decision == "block"


# --- Rule 2: valid PR edges ----------------------------------------------

@pytest.mark.parametrize("head,base", [
    ("feature/x", "develop"),
    ("release/1.2.0", "main"),
    ("hotfix/urgent", "main"),
    ("main", "develop"),
])
def test_valid_edges_allow(head, base):
    action = Action(kind="pr-create", base=base, head=head)
    facts = Facts(branch=head, changelog_ok=Tri.TRUE)
    assert evaluate(action, facts, cfg()).decision != "block"


@pytest.mark.parametrize("head,base", [
    ("feature/x", "main"),
    ("release/1.2.0", "develop"),
])
def test_invalid_edges_block(head, base):
    action = Action(kind="pr-create", base=base, head=head)
    facts = Facts(branch=head, changelog_ok=Tri.TRUE)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "pr-edge"


def test_trunk_topology_allows_feature_into_production():
    action = Action(kind="pr-create", base="main", head="feature/x")
    facts = Facts(branch="feature/x", changelog_ok=Tri.TRUE)
    c = cfg(topology="trunk", integration="main")
    assert evaluate(action, facts, c).decision != "block"


# --- Rule 3: changelog ----------------------------------------------------

def test_feature_pr_without_changelog_blocks():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    v = evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "block"
    assert v.rule == "changelog"


def test_release_pr_skips_changelog_gate():
    action = Action(kind="pr-create", base="main", head="release/1.2.0")
    v = evaluate(action, Facts(branch="release/1.2.0", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "allow"


def test_back_merge_pr_skips_changelog_gate():
    action = Action(kind="pr-create", base="develop", head="main")
    v = evaluate(action, Facts(branch="main", changelog_ok=Tri.FALSE), cfg())
    assert v.decision == "allow"


def test_unknown_changelog_warns():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    v = evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.UNKNOWN), cfg())
    assert v.decision == "warn"


def test_changelog_gate_disabled_by_config():
    action = Action(kind="pr-create", base="develop", head="feature/x")
    c = cfg(require_changelog=False)
    assert evaluate(action, Facts(branch="feature/x", changelog_ok=Tri.FALSE), c).decision == "allow"


# --- Rule 4: merge strategy ----------------------------------------------

def test_non_squash_merge_into_integration_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="APPROVED")
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "merge-strategy"


def test_squash_merge_into_integration_allows():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="APPROVED")
    assert evaluate(action, facts, cfg()).decision == "allow"


def test_merge_commit_into_production_allows():
    action = Action(kind="pr-merge", pr_number="5", strategy="merge")
    facts = Facts(pr_base="main", pr_head="release/1.2.0")
    assert evaluate(action, facts, cfg()).decision == "allow"


# --- Rule 5: review policy -----------------------------------------------

def test_same_repo_pr_still_requires_review():
    # Regression: maintainers merging same-repo feature PRs skipped both the
    # squash and review gates via an isCrossRepository check.
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_is_fork=Tri.FALSE, pr_review_state=None)
    v = evaluate(action, facts, cfg())
    assert v.decision == "block"
    assert v.rule == "review"


def test_policy_review_accepts_commented():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="COMMENTED")
    assert evaluate(action, facts, cfg(review_policy="review")).decision == "allow"


def test_policy_approval_rejects_commented():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state="COMMENTED")
    v = evaluate(action, facts, cfg(review_policy="approval"))
    assert v.decision == "block"
    assert v.rule == "review"


def test_policy_none_skips_review():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x", pr_review_state=None)
    assert evaluate(action, facts, cfg(review_policy="none")).decision == "allow"


def test_changes_requested_always_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="CHANGES_REQUESTED")
    v = evaluate(action, facts, cfg(review_policy="none"))
    assert v.decision == "block"


def test_unknown_pr_base_warns():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    assert evaluate(action, Facts(pr_base=None), cfg()).decision == "warn"


# --- Rule 6: capability ---------------------------------------------------

def test_missing_capability_warns_never_blocks():
    action = Action(kind="pr-merge", pr_number="5", strategy="squash")
    facts = Facts(pr_base="develop", pr_head="feature/x",
                  pr_review_state="APPROVED", capability=Tri.FALSE)
    assert evaluate(action, facts, cfg()).decision == "warn"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_rules.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.rules'`

- [ ] **Step 3: Implement**

`plugins/keel/keel/rules.py`:
```python
"""The rule engine. Pure: no I/O, no subprocess, no globals.

Rules key on (action, base, head, headIsFork, capability). There is no role.

Fail policy, applied uniformly: a fact that is Tri.UNKNOWN produces a 'warn',
never a 'block'. The hook is advisory; blocking on ignorance costs more trust
than it buys.
"""
from dataclasses import dataclass

from .facts import Tri


@dataclass(frozen=True)
class Verdict:
    decision: str  # "allow" | "warn" | "block"
    rule: str = ""
    message: str = ""


ALLOW = Verdict("allow")


def _block(rule, message):
    return Verdict("block", rule, message)


def _warn(rule, message):
    return Verdict("warn", rule, message)


def _protected(cfg):
    return {cfg.production, cfg.integration}


def _kind_of_branch(name, cfg):
    if name is None:
        return None
    if name.startswith(cfg.feature_prefix):
        return "feature"
    if name.startswith(cfg.release_prefix):
        return "release"
    if name.startswith(cfg.hotfix_prefix):
        return "hotfix"
    if name == cfg.production:
        return "production"
    if name == cfg.integration:
        return "integration"
    return "other"


# --- Rule 1: protected-branch writes -------------------------------------

def _rule_protected_write(action, facts, cfg):
    protected = _protected(cfg)

    if action.kind == "commit":
        if facts.branch is None:
            return _warn("protected-write",
                         "Could not determine the current branch; skipping the "
                         "protected-branch check.")
        if facts.branch in protected:
            return _block("protected-write",
                          f"'{facts.branch}' is protected. Start a branch with "
                          f"keel:start-work; changes reach it via PR.")
        return ALLOW

    if action.kind == "push":
        if not action.refs:
            # 'git push' with no refspec pushes the current branch.
            if facts.branch is None:
                return _warn("protected-write",
                             "Could not determine what this push targets.")
            targets = [facts.branch]
        else:
            # Tag refs are exempt -- but only the tag refs themselves. A branch
            # ref in the same command is still checked.
            targets = [r.dst for r in action.refs if not r.is_tag]
        hits = [t for t in targets if t in protected]
        if hits:
            return _block("protected-write",
                          f"This pushes directly to protected branch "
                          f"'{hits[0]}'. Open a PR instead (keel:finish-work).")
    return ALLOW


# --- Rule 2: valid PR edges ----------------------------------------------

def _valid_edge(head_kind, base, cfg):
    if cfg.is_trunk:
        return (head_kind in ("feature", "hotfix") and base == cfg.production)
    return (
        (head_kind == "feature" and base == cfg.integration)
        or (head_kind == "release" and base == cfg.production)
        or (head_kind == "hotfix" and base == cfg.production)
        or (head_kind == "production" and base == cfg.integration)  # back-merge
    )


def _rule_pr_edge(action, facts, cfg):
    head = action.head or facts.branch
    head_kind = _kind_of_branch(head, cfg)
    if action.base is None or head_kind is None:
        return _warn("pr-edge", "Could not determine this PR's base or head branch.")
    if not _valid_edge(head_kind, action.base, cfg):
        if cfg.is_trunk:
            expected = f"'{cfg.production}'"
        else:
            expected = (f"'{cfg.integration}' for feature work, "
                        f"'{cfg.production}' for releases and hotfixes")
        return _block("pr-edge",
                      f"'{head}' should not target '{action.base}'. "
                      f"Expected {expected}.")
    return ALLOW


# --- Rule 3: changelog ----------------------------------------------------

def _rule_changelog(action, facts, cfg):
    if not cfg.require_changelog:
        return ALLOW
    head_kind = _kind_of_branch(action.head or facts.branch, cfg)
    # Release and back-merge PRs carry no new user-facing change of their own.
    if head_kind not in ("feature", "hotfix"):
        return ALLOW
    if facts.changelog_ok is Tri.UNKNOWN:
        return _warn("changelog",
                     "Could not compare against the base branch, so the "
                     "CHANGELOG check was skipped. Run 'git fetch' and retry "
                     "if you want it enforced.")
    if facts.changelog_ok is Tri.FALSE:
        return _block("changelog",
                      "The Unreleased section of CHANGELOG.md has not gained "
                      "any content on this branch. Add an entry before opening "
                      "the PR.")
    return ALLOW


# --- Rule 4: merge strategy ----------------------------------------------

def _rule_merge_strategy(action, facts, cfg):
    if facts.pr_base is None:
        return _warn("merge-strategy", "Could not determine the PR's base branch.")
    if facts.pr_base == cfg.integration and not cfg.is_trunk:
        expected = cfg.merge_to_integration
    elif facts.pr_base == cfg.production:
        expected = cfg.merge_to_production
    else:
        return ALLOW
    if action.strategy is None:
        return _warn("merge-strategy",
                     f"No merge strategy given; '{cfg.production}' expects "
                     f"--{expected}.")
    if action.strategy != expected:
        return _block("merge-strategy",
                      f"PRs into '{facts.pr_base}' use --{expected}, "
                      f"not --{action.strategy}.")
    return ALLOW


# --- Rule 5: review policy -----------------------------------------------

def _rule_review(action, facts, cfg):
    if facts.pr_review_state == "CHANGES_REQUESTED":
        return _block("review",
                      "This PR has requested changes outstanding. "
                      "Address them first (keel:respond-to-review).")
    if cfg.review_policy == "none":
        return ALLOW
    if facts.pr_base is None:
        return _warn("review", "Could not determine the PR's base branch.")
    # Releases and back-merges carry already-reviewed content.
    head_kind = _kind_of_branch(facts.pr_head, cfg)
    if head_kind in ("release", "production"):
        return ALLOW
    accepted = ("APPROVED",) if cfg.review_policy == "approval" else ("APPROVED", "COMMENTED")
    if facts.pr_review_state is None:
        return _block("review",
                      "This PR has no review yet. Review it first "
                      "(keel:review).")
    if facts.pr_review_state not in accepted:
        return _block("review",
                      f"reviewPolicy is '{cfg.review_policy}', which requires an "
                      f"approving review; this PR is '{facts.pr_review_state}'.")
    return ALLOW


# --- Rule 6: capability ---------------------------------------------------

def _rule_capability(action, facts, cfg):
    if facts.capability is Tri.FALSE:
        return _warn("capability",
                     "You may not have merge permission on this repository; "
                     "this is likely to fail.")
    return ALLOW


RULES = {
    "commit": (_rule_protected_write,),
    "push": (_rule_protected_write,),
    "pr-create": (_rule_pr_edge, _rule_changelog),
    "pr-merge": (_rule_merge_strategy, _rule_review, _rule_capability),
}


def evaluate(action, facts, cfg):
    """Return the most severe verdict across the rules for this action."""
    worst = ALLOW
    for rule in RULES.get(action.kind, ()):
        verdict = rule(action, facts, cfg)
        if verdict.decision == "block":
            return verdict
        if verdict.decision == "warn" and worst.decision == "allow":
            worst = verdict
    return worst
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_rules.py -v`
Expected: PASS (28 passed)

- [ ] **Step 5: Commit**

```bash
git add plugins/keel/keel/rules.py plugins/keel/tests/test_rules.py
git commit -m "feat: rule engine keyed on action, base, head, fork, capability"
```

---

### Task 6: Git I/O

**Files:**
- Create: `plugins/keel/keel/gitio.py`
- Test: `plugins/keel/tests/test_gitio.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `GIT_TIMEOUT: float` (= `5.0`)
  - `run_git(args: list[str], cwd=None) -> str | None` — stdout stripped, or `None` on any failure/timeout
  - `repo_root(cwd=None) -> pathlib.Path | None`
  - `current_branch(cwd=None) -> str | None` — `None` when detached or unknown
  - `origin_slug(cwd=None) -> str | None` — lowercase `owner/repo`
  - `changelog_gained_content(base: str, cwd=None) -> bool | None`
  - `target_cwd(command: str, default: str) -> str` — honours `cd X &&` and `git -C X`

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_gitio.py`:
```python
import subprocess
from keel import gitio


def init_repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True,
                       capture_output=True, text=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    (tmp_path / "README.md").write_text("hi\n")
    git("add", "-A")
    git("commit", "-qm", "init")
    return tmp_path, git


def test_repo_root(tmp_path):
    repo, _ = init_repo(tmp_path)
    assert gitio.repo_root(cwd=repo).resolve() == repo.resolve()


def test_repo_root_outside_repo_is_none(tmp_path):
    assert gitio.repo_root(cwd=tmp_path) is None


def test_current_branch(tmp_path):
    repo, _ = init_repo(tmp_path)
    assert gitio.current_branch(cwd=repo) == "main"


def test_detached_head_is_none(tmp_path):
    repo, git = init_repo(tmp_path)
    sha = gitio.run_git(["rev-parse", "HEAD"], cwd=repo)
    git("checkout", "-q", sha)
    assert gitio.current_branch(cwd=repo) is None


def test_origin_slug_is_lowercased(tmp_path):
    repo, git = init_repo(tmp_path)
    git("remote", "add", "origin", "git@github.com:Owner/Repo.git")
    assert gitio.origin_slug(cwd=repo) == "owner/repo"


def test_origin_slug_https(tmp_path):
    repo, git = init_repo(tmp_path)
    git("remote", "add", "origin", "https://github.com/Owner/Repo.git")
    assert gitio.origin_slug(cwd=repo) == "owner/repo"


def test_changelog_gained_content_true(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    git("checkout", "-qb", "feature/x")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n\n- Added a thing\n")
    git("add", "-A"); git("commit", "-qm", "entry")
    assert gitio.changelog_gained_content("main", cwd=repo) is True


def test_changelog_whitespace_only_is_false(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    git("checkout", "-qb", "feature/x")
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n   \n")
    git("add", "-A"); git("commit", "-qm", "whitespace")
    assert gitio.changelog_gained_content("main", cwd=repo) is False


def test_changelog_missing_base_is_none(tmp_path):
    repo, _ = init_repo(tmp_path)
    assert gitio.changelog_gained_content("nonexistent-branch", cwd=repo) is None


def test_target_cwd_honours_cd():
    assert gitio.target_cwd("cd /other && git commit -m x", "/here") == "/other"


def test_target_cwd_honours_git_C():
    assert gitio.target_cwd("git -C /other commit -m x", "/here") == "/other"


def test_target_cwd_defaults():
    assert gitio.target_cwd("git commit -m x", "/here") == "/here"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_gitio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.gitio'`

- [ ] **Step 3: Implement**

`plugins/keel/keel/gitio.py`:
```python
"""All git subprocess I/O. Every call is timed out. Failures return None."""
import re
import shlex
import subprocess
from pathlib import Path

GIT_TIMEOUT = 5.0

_SLUG = re.compile(r"[:/]([^/:]+)/([^/]+?)(?:\.git)?/?$")
_UNRELEASED = re.compile(r"^#{1,3}\s*\[?unreleased\]?", re.IGNORECASE)


def run_git(args, cwd=None):
    try:
        proc = subprocess.run(
            ["git", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GIT_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def repo_root(cwd=None):
    out = run_git(["rev-parse", "--show-toplevel"], cwd=cwd)
    return Path(out) if out else None


def current_branch(cwd=None):
    out = run_git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd=cwd)
    return out or None


def origin_slug(cwd=None):
    url = run_git(["remote", "get-url", "origin"], cwd=cwd)
    if not url:
        return None
    match = _SLUG.search(url)
    if not match:
        return None
    return f"{match.group(1)}/{match.group(2)}".lower()


def _unreleased_body(text):
    """Return the Unreleased section's body, stripped of blank lines."""
    lines, collecting, body = text.splitlines(), False, []
    for line in lines:
        if _UNRELEASED.match(line.strip()):
            collecting = True
            continue
        if collecting and line.strip().startswith("#"):
            break
        if collecting:
            body.append(line)
    return "\n".join(b for b in body if b.strip())


def changelog_gained_content(base, cwd=None):
    """True if the Unreleased section grew relative to base. None if unknowable."""
    merge_base = run_git(["merge-base", "HEAD", base], cwd=cwd)
    if merge_base is None:
        return None
    before = run_git(["show", f"{merge_base}:CHANGELOG.md"], cwd=cwd) or ""
    root = repo_root(cwd=cwd)
    if root is None:
        return None
    path = root / "CHANGELOG.md"
    after = path.read_text() if path.is_file() else ""
    return _unreleased_body(after) != _unreleased_body(before)


def target_cwd(command, default):
    """Resolve the directory a command actually operates on."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return default
    for i, token in enumerate(tokens):
        if token == "-C" and i + 1 < len(tokens):
            return tokens[i + 1]
    if tokens and tokens[0] == "cd" and len(tokens) > 1:
        return tokens[1]
    return default
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_gitio.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add plugins/keel/keel/gitio.py plugins/keel/tests/test_gitio.py
git commit -m "feat: git I/O with timeouts and content-aware changelog check"
```

---

### Task 7: GitHub I/O

**Files:**
- Create: `plugins/keel/keel/ghio.py`
- Test: `plugins/keel/tests/test_ghio.py`

**Interfaces:**
- Consumes: `keel.facts.Tri`
- Produces:
  - `GH_TIMEOUT: float` (= `8.0`)
  - `pr_facts(number: str | None, cwd=None) -> dict | None` — one `gh pr view` call returning keys `base`, `head`, `is_fork`, `review_state`; `None` on failure
  - `capability(cwd=None) -> Tri`
  - `clear_cache()` — test helper

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_ghio.py`:
```python
import json
import pytest
from keel import ghio
from keel.facts import Tri


@pytest.fixture(autouse=True)
def clear():
    ghio.clear_cache()
    yield
    ghio.clear_cache()


class FakeProc:
    def __init__(self, stdout, returncode=0):
        self.stdout = stdout
        self.returncode = returncode
        self.stderr = ""


def test_pr_facts_parses_single_call(monkeypatch):
    calls = []

    def fake_run(args, **kw):
        calls.append(args)
        return FakeProc(json.dumps({
            "baseRefName": "develop",
            "headRefName": "feature/x",
            "isCrossRepository": True,
            "reviewDecision": "APPROVED",
            "reviews": [{"state": "APPROVED"}],
        }))

    monkeypatch.setattr(ghio.subprocess, "run", fake_run)
    facts = ghio.pr_facts("5")
    assert facts == {"base": "develop", "head": "feature/x",
                     "is_fork": Tri.TRUE, "review_state": "APPROVED"}
    assert len(calls) == 1, "must be a single gh call"


def test_pr_facts_is_cached(monkeypatch):
    calls = []
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: calls.append(args) or FakeProc(json.dumps(
                            {"baseRefName": "develop", "headRefName": "f",
                             "isCrossRepository": False, "reviewDecision": None,
                             "reviews": []})))
    ghio.pr_facts("5")
    ghio.pr_facts("5")
    assert len(calls) == 1


def test_commented_review_surfaces_when_no_decision(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(json.dumps({
        "baseRefName": "develop", "headRefName": "feature/x",
        "isCrossRepository": False, "reviewDecision": None,
        "reviews": [{"state": "COMMENTED"}],
    })))
    assert ghio.pr_facts("5")["review_state"] == "COMMENTED"


def test_changes_requested_wins_over_comment(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(json.dumps({
        "baseRefName": "develop", "headRefName": "feature/x",
        "isCrossRepository": False, "reviewDecision": "CHANGES_REQUESTED",
        "reviews": [{"state": "COMMENTED"}],
    })))
    assert ghio.pr_facts("5")["review_state"] == "CHANGES_REQUESTED"


def test_gh_failure_returns_none(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("", 1))
    assert ghio.pr_facts("5") is None


def test_gh_missing_returns_none(monkeypatch):
    def boom(args, **kw):
        raise OSError("gh not found")
    monkeypatch.setattr(ghio.subprocess, "run", boom)
    assert ghio.pr_facts("5") is None


def test_malformed_json_returns_none(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("{not json"))
    assert ghio.pr_facts("5") is None


@pytest.mark.parametrize("perm,expected", [
    ("ADMIN", Tri.TRUE), ("MAINTAIN", Tri.TRUE), ("WRITE", Tri.TRUE),
    ("READ", Tri.FALSE), ("TRIAGE", Tri.FALSE),
])
def test_capability_from_viewer_permission(monkeypatch, perm, expected):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(
        json.dumps({"viewerPermission": perm})))
    assert ghio.capability() is expected


def test_capability_never_requests_raw_jq_output(monkeypatch):
    # Regression: `-q .viewerPermission` makes gh emit a bare word, which is
    # not valid JSON, so json.loads always failed and this path never worked.
    seen = []
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: seen.append(args) or FakeProc(
                            json.dumps({"viewerPermission": "ADMIN"})))
    ghio.capability()
    assert "-q" not in seen[0], "capability() must parse JSON, not jq output"


def test_capability_from_permissions_object(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(
        json.dumps({"push": True, "maintain": False, "admin": False})))
    assert ghio.capability() is Tri.TRUE


def test_capability_false(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc(
        json.dumps({"push": False, "maintain": False, "admin": False})))
    assert ghio.capability() is Tri.FALSE


def test_capability_unknown_on_failure(monkeypatch):
    monkeypatch.setattr(ghio.subprocess, "run", lambda args, **kw: FakeProc("", 1))
    assert ghio.capability() is Tri.UNKNOWN


def test_every_call_passes_a_timeout(monkeypatch):
    seen = {}
    monkeypatch.setattr(ghio.subprocess, "run",
                        lambda args, **kw: seen.update(kw) or FakeProc("{}"))
    ghio.capability()
    assert "timeout" in seen and seen["timeout"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_ghio.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.ghio'`

- [ ] **Step 3: Implement**

`plugins/keel/keel/ghio.py`:
```python
"""All `gh` subprocess I/O.

One call per concern, always timed out, cached for the life of the process.
Any failure degrades to None/UNKNOWN -- never to a false confident answer.
"""
import json
import subprocess

from .facts import Tri

GH_TIMEOUT = 8.0

_PR_FIELDS = "baseRefName,headRefName,isCrossRepository,reviewDecision,reviews"
_cache = {}


def clear_cache():
    _cache.clear()


def _gh_json(args, cwd=None):
    try:
        proc = subprocess.run(
            ["gh", *args], cwd=cwd, capture_output=True, text=True,
            timeout=GH_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return None


def _review_state(data):
    """Collapse reviewDecision + reviews into one state string."""
    decision = data.get("reviewDecision")
    if decision in ("CHANGES_REQUESTED", "APPROVED"):
        return decision
    states = {r.get("state") for r in (data.get("reviews") or [])}
    if "CHANGES_REQUESTED" in states:
        return "CHANGES_REQUESTED"
    if "APPROVED" in states:
        return "APPROVED"
    if "COMMENTED" in states:
        return "COMMENTED"
    return None


def pr_facts(number, cwd=None):
    key = ("pr", number, cwd)
    if key in _cache:
        return _cache[key]
    args = ["pr", "view"]
    if number:
        args.append(str(number))
    args += ["--json", _PR_FIELDS]
    data = _gh_json(args, cwd=cwd)
    if data is None:
        _cache[key] = None
        return None
    result = {
        "base": data.get("baseRefName") or None,
        "head": data.get("headRefName") or None,
        "is_fork": Tri.of(data.get("isCrossRepository")),
        "review_state": _review_state(data),
    }
    _cache[key] = result
    return result


def capability(cwd=None):
    """Whether the current user can push/maintain this repository."""
    key = ("cap", cwd)
    if key in _cache:
        return _cache[key]
    # NB: no `-q` here. With `-q` gh emits a bare word like `ADMIN`, which is
    # not valid JSON, so json.loads would always fail and this path would
    # silently never work. Ask for the object and read the field ourselves.
    data = _gh_json(["repo", "view", "--json", "viewerPermission"], cwd=cwd)
    if isinstance(data, dict) and "viewerPermission" in data:
        perm = data.get("viewerPermission")
        result = Tri.of(perm in ("ADMIN", "MAINTAIN", "WRITE")) if perm else Tri.UNKNOWN
    elif isinstance(data, dict):
        # `gh api repos/{owner}/{repo}` shape: a permissions object.
        result = Tri.of(bool(data.get("push") or data.get("maintain")
                             or data.get("admin")))
    else:
        result = Tri.UNKNOWN
    _cache[key] = result
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_ghio.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: Commit**

```bash
git add plugins/keel/keel/ghio.py plugins/keel/tests/test_ghio.py
git commit -m "feat: batched, timed-out, cached gh I/O"
```

---

### Task 8: Render and the PreToolUse hook

**Files:**
- Create: `plugins/keel/keel/render.py`
- Create: `plugins/keel/hooks/guard.py`
- Create: `plugins/keel/hooks/hooks.json`
- Test: `plugins/keel/tests/test_render.py`

**Interfaces:**
- Consumes: `keel.rules.Verdict`, all prior modules.
- Produces:
  - `render(verdict: Verdict) -> dict` — the hook's stdout JSON payload
  - `plugins/keel/hooks/guard.py` executable as the `PreToolUse` entrypoint

- [ ] **Step 1: Write the failing tests**

`plugins/keel/tests/test_render.py`:
```python
from keel.render import render
from keel.rules import Verdict, ALLOW


def test_allow_produces_no_decision():
    out = render(ALLOW)
    assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out["hookSpecificOutput"]


def test_block_denies_with_reason():
    out = render(Verdict("block", "protected-write", "'main' is protected."))
    hso = out["hookSpecificOutput"]
    assert hso["permissionDecision"] == "deny"
    assert "'main' is protected." in hso["permissionDecisionReason"]
    assert "keel" in hso["permissionDecisionReason"]
    assert "protected-write" in hso["permissionDecisionReason"]


def test_warn_does_not_deny_but_surfaces_a_message():
    out = render(Verdict("warn", "changelog", "Could not compare."))
    assert "permissionDecision" not in out.get("hookSpecificOutput", {})
    assert "Could not compare." in out["systemMessage"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python3 -m pytest plugins/keel/tests/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'keel.render'`

- [ ] **Step 3: Implement render**

`plugins/keel/keel/render.py`:
```python
"""Turn a Verdict into the PreToolUse hook's stdout payload."""

DOCTOR = "Run keel:doctor to see the full picture."


def render(verdict):
    out = {"hookSpecificOutput": {"hookEventName": "PreToolUse"}}
    if verdict.decision == "block":
        out["hookSpecificOutput"]["permissionDecision"] = "deny"
        out["hookSpecificOutput"]["permissionDecisionReason"] = (
            f"[keel/{verdict.rule}] {verdict.message} {DOCTOR}"
        )
    elif verdict.decision == "warn":
        out["systemMessage"] = f"[keel/{verdict.rule}] {verdict.message}"
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python3 -m pytest plugins/keel/tests/test_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Write the hook entrypoint**

`plugins/keel/hooks/guard.py`:
```python
#!/usr/bin/env python3
"""PreToolUse entrypoint. Advisory: never crashes the tool call."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keel import ghio, gitio                    # noqa: E402
from keel.actions import classify               # noqa: E402
from keel.config import ConfigError, load_config  # noqa: E402
from keel.facts import Facts, Tri               # noqa: E402
from keel.render import render                  # noqa: E402
from keel.rules import evaluate                 # noqa: E402


def gather(action, cwd, cfg):
    branch = gitio.current_branch(cwd=cwd)
    changelog = Tri.UNKNOWN
    if action.kind == "pr-create":
        got = gitio.changelog_gained_content(cfg.integration, cwd=cwd)
        changelog = Tri.of(got)
    pr = ghio.pr_facts(action.pr_number, cwd=cwd) if action.kind == "pr-merge" else None
    return Facts(
        branch=branch,
        capability=ghio.capability(cwd=cwd) if action.kind == "pr-merge" else Tri.UNKNOWN,
        pr_base=(pr or {}).get("base"),
        pr_head=(pr or {}).get("head"),
        pr_is_fork=(pr or {}).get("is_fork", Tri.UNKNOWN),
        pr_review_state=(pr or {}).get("review_state"),
        changelog_ok=changelog,
    )


def main():
    try:
        event = json.load(sys.stdin)
    except (ValueError, OSError):
        return 0
    if event.get("tool_name") != "Bash":
        return 0

    command = (event.get("tool_input") or {}).get("command", "")
    actions = classify(command)
    if not actions:
        return 0

    cwd = gitio.target_cwd(command, event.get("cwd") or os.getcwd())
    root = gitio.repo_root(cwd=cwd)
    if root is None:
        return 0  # not a git repo; nothing to say

    try:
        cfg = load_config(root)
    except ConfigError as exc:
        # Loud, per the spec: a broken config must never silently disable keel.
        print(json.dumps({"systemMessage": f"[keel] {exc} keel is inactive "
                                           f"until this is fixed."}))
        return 0
    if cfg is None:
        return 0  # repo is not keel-managed

    for action in actions:
        verdict = evaluate(action, gather(action, cwd, cfg), cfg)
        if verdict.decision != "allow":
            print(json.dumps(render(verdict)))
            return 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - advisory hook must never break Bash
        print(json.dumps({"systemMessage": f"[keel] internal error, allowing: {exc}"}))
        sys.exit(0)
```

- [ ] **Step 6: Register the hook**

`plugins/keel/hooks/hooks.json`:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/guard.py",
            "timeout": 20,
            "statusMessage": "keel: checking"
          }
        ]
      }
    ]
  }
}
```

- [ ] **Step 7: Verify the hook end-to-end by hand**

```bash
cd /tmp && rm -rf keeltest && mkdir keeltest && cd keeltest
git init -q -b main && echo '{}' > .keel.json
echo '{"tool_name":"Bash","cwd":"/tmp/keeltest","tool_input":{"command":"git commit -m x"}}' \
  | python3 ~/Development/submtd/shipyard/plugins/keel/hooks/guard.py
```
Expected: JSON containing `"permissionDecision": "deny"` and `protected-write`.

```bash
echo '{"tool_name":"Bash","cwd":"/tmp/keeltest","tool_input":{"command":"git status"}}' \
  | python3 ~/Development/submtd/shipyard/plugins/keel/hooks/guard.py
```
Expected: no output, exit 0.

- [ ] **Step 8: Commit**

```bash
git add plugins/keel/keel/render.py plugins/keel/hooks plugins/keel/tests/test_render.py
git commit -m "feat: PreToolUse guard entrypoint with JSON permission decisions"
```

---

### Task 9: SessionStart orientation

**Files:**
- Create: `plugins/keel/hooks/orient.py`
- Modify: `plugins/keel/hooks/hooks.json` (add the `SessionStart` block)

**Interfaces:**
- Consumes: `keel.config`, `keel.gitio`
- Produces: a `SessionStart` hook emitting `additionalContext`

- [ ] **Step 1: Write the orientation entrypoint**

`plugins/keel/hooks/orient.py`:
```python
#!/usr/bin/env python3
"""SessionStart entrypoint: describe the repo's lifecycle in one short block."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from keel import gitio                            # noqa: E402
from keel.config import ConfigError, load_config  # noqa: E402


def orientation(cfg, branch):
    if cfg.is_trunk:
        flow = f"{cfg.feature_prefix}* -> PR -> {cfg.production} (tagged to release)"
    else:
        flow = (f"{cfg.feature_prefix}* -> PR -> {cfg.integration} -> "
                f"{cfg.release_prefix}* -> PR -> {cfg.production}")
    protected = sorted({cfg.production, cfg.integration})
    on_protected = branch in protected
    lines = [
        "This repository uses keel for its git lifecycle.",
        "",
        f"- Topology: {cfg.topology} ({flow})",
        f"- Protected: {', '.join(protected)} (changes reach them via PR)",
        f"- Review policy: {cfg.review_policy}",
        f"- Current branch: {branch or 'unknown (detached HEAD?)'}",
    ]
    if on_protected:
        lines += ["", f"You are on protected branch '{branch}'. Start work with "
                      f"the keel:start-work skill before making changes."]
    lines += ["", "Skills: keel:start-work, keel:finish-work, keel:respond-to-review, "
                  "keel:sync, keel:review, keel:land, keel:release, keel:ship, "
                  "keel:protect, keel:doctor.",
              "",
              "keel's hook is advisory: it catches mistakes early, but GitHub "
              "branch protection is the real boundary (see keel:protect)."]
    return "\n".join(lines)


def main():
    root = gitio.repo_root()
    if root is None:
        return 0
    try:
        cfg = load_config(root)
    except ConfigError as exc:
        print(json.dumps({"additionalContext": f"[keel] {exc} keel is inactive."}))
        return 0
    if cfg is None:
        return 0
    print(json.dumps({"additionalContext": orientation(cfg, gitio.current_branch())}))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:  # noqa: BLE001
        sys.exit(0)
```

- [ ] **Step 2: Add the SessionStart registration**

Replace `plugins/keel/hooks/hooks.json` with:
```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/guard.py",
            "timeout": 20,
            "statusMessage": "keel: checking"
          }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup",
        "hooks": [
          {
            "type": "command",
            "command": "python3 \"${CLAUDE_PLUGIN_ROOT}\"/hooks/orient.py",
            "timeout": 15
          }
        ]
      }
    ]
  }
}
```

The `startup` matcher is deliberate: the previous implementation had no matcher and re-injected orientation on every resume and compact.

- [ ] **Step 3: Verify by hand**

```bash
cd /tmp/keeltest && python3 ~/Development/submtd/shipyard/plugins/keel/hooks/orient.py
```
Expected: JSON with `additionalContext` mentioning `gitflow`, `main, develop`, and the protected-branch warning (the test repo is on `main`).

- [ ] **Step 4: Commit**

```bash
git add plugins/keel/hooks
git commit -m "feat: SessionStart orientation, scoped to startup only"
```

---

### Task 10: Contributor-loop skills

**Files:**
- Create: `plugins/keel/skills/start-work/SKILL.md`
- Create: `plugins/keel/skills/finish-work/SKILL.md`
- Create: `plugins/keel/skills/respond-to-review/SKILL.md`
- Create: `plugins/keel/skills/sync/SKILL.md`

**Interfaces:**
- Consumes: `.keel.json` semantics from Task 2; rule messages from Task 5.
- Produces: four invocable skills, `keel:start-work` etc.

- [ ] **Step 1: Write `start-work`**

`plugins/keel/skills/start-work/SKILL.md`:
```markdown
---
name: start-work
description: Use when beginning any new change - creates a correctly-named branch from an up-to-date base, choosing fork or same-repo based on the repo's config and your permissions.
---

# Starting work

## 1. Read the config

Read `.keel.json` at the repo root. You need `topology`, `branches`, `prefixes`,
and `contributions`. If the file is absent, this repo is not keel-managed - say
so and stop.

## 2. Decide the branch kind

Ask the user which applies if it is not obvious from their request:

- **feature** - normal work. Base branch is `integration` (or `production` under
  `trunk` topology).
- **hotfix** - an urgent fix to production. Base branch is `production`.

## 3. Decide fork vs same-repo

Run `gh repo view --json viewerPermission -q .viewerPermission`.

- `contributions` is `fork`, or you have `READ`/`TRIAGE` only -> work on a fork.
  Check for a fork with `gh repo fork --clone=false` (idempotent), ensure an
  `upstream` remote points at the canonical repo.
- Otherwise -> work directly in this clone.

## 4. Create the branch

Fetch first so you branch from current code:

    git fetch <remote> <base>
    git checkout -b <prefix><slug> <remote>/<base>

Derive `<slug>` from the user's description: lowercase, hyphenated, no more than
about five words.

## 5. Confirm

Tell the user the branch name, what it was based on, and that `CHANGELOG.md`
will need an Unreleased entry before the PR (unless `requireChangelog` is false).
```

- [ ] **Step 2: Write `finish-work`**

`plugins/keel/skills/finish-work/SKILL.md`:
```markdown
---
name: finish-work
description: Use when a change is complete and ready to become a pull request - runs checks, updates the changelog, and opens the PR against the correct base.
---

# Finishing a change

## 1. Verify it works

Run the project's tests and linter. If you cannot tell what they are, ask.
**Do not proceed on a failing suite.** If tests fail, stop and report - fixing
them is the work now.

If `superpowers:requesting-code-review` is available, use it for a self-review
pass before continuing. If not, review your own diff with `git diff` and look
for debug output, commented-out code, and unrelated changes.

## 2. Update CHANGELOG.md

Add an entry under `## Unreleased`, in the user's voice - what changed for
someone using this project, not which functions you touched.

keel checks that the Unreleased section *gained content*, so an empty edit will
not satisfy it.

## 3. Consider CLAUDE.md

Ask yourself: does this change alter anything documented in `CLAUDE.md` -
commands, architecture, conventions? Update it if so.

Do **not** edit `CLAUDE.md` just to have edited it. Most changes should not
touch it.

## 4. Commit and push

Write a conventional-commit message. Push the branch.

## 5. Open the PR

Determine the base from `.keel.json`: `integration` for feature branches,
`production` for hotfix and release branches (under `trunk`, everything targets
`production`).

    gh pr create --base <base> --title "..." --body "..."

Write a body that says what changed and why, and how to verify it.

## 6. Report

Give the user the PR URL and say what happens next: it needs a review before it
can land (`keel:review`, then `keel:land`).
```

- [ ] **Step 3: Write `respond-to-review`**

`plugins/keel/skills/respond-to-review/SKILL.md`:
```markdown
---
name: respond-to-review
description: Use when a pull request has review comments to address - reads the feedback, evaluates it, makes the changes, and replies.
---

# Responding to review feedback

## 1. Read the feedback

    gh pr view <number> --json reviews,comments
    gh pr diff <number>

## 2. Evaluate before implementing

If `superpowers:receiving-code-review` is available, use it.

Otherwise, for each comment decide: is it correct? Reviewers are sometimes
wrong, and agreeing with a wrong suggestion makes the code worse. Where you
disagree, say so with a reason rather than complying silently.

Group the comments into: **will fix**, **will not fix (with reason)**, and
**needs clarification**.

## 3. Confirm the plan

Show the user that grouping before you change anything. This is the step that
prevents a round of churn.

## 4. Make the changes

One commit per coherent group of fixes. Do not force-push over the reviewed
history - the reviewer needs to see what changed since their pass.

## 5. Update the changelog if behaviour changed

If review feedback altered user-facing behaviour, the `Unreleased` entry needs
to match.

## 6. Reply and re-request

Reply to each thread saying what you did or why you did not. Then:

    gh pr review <number> --comment --body "..."
    gh pr ready <number>   # if it was a draft
```

- [ ] **Step 4: Write `sync`**

`plugins/keel/skills/sync/SKILL.md`:
```markdown
---
name: sync
description: Use when a branch or fork has fallen behind its base, or before opening a PR after a delay - brings the branch up to date and resolves conflicts.
---

# Syncing a stale branch

## 1. Work out what is stale

Read `.keel.json` for the base branch. Then:

    git fetch --all --prune
    git log --oneline HEAD..<remote>/<base> | head -20

If that is empty, the branch is current - say so and stop.

## 2. If this is a fork, refresh the fork's copy of the base

    git fetch upstream <base>
    git checkout <base> && git merge --ff-only upstream/<base>
    git push origin <base>

If the fast-forward fails, the local base has diverged - reset it to upstream
rather than merging:

    git reset --hard upstream/<base>

## 3. Update the working branch

Rebase when the branch has not been reviewed yet - it keeps history readable:

    git checkout <branch>
    git rebase <remote>/<base>

**Merge instead of rebasing if the PR is already under review.** Rewriting
history mid-review destroys the reviewer's ability to see what changed:

    git merge <remote>/<base>

## 4. Resolve conflicts

Resolve each one, run the tests, then continue. If a conflict is in
`CHANGELOG.md`, keep both entries - they are usually independent.

## 5. Push

After a rebase you will need `--force-with-lease` (never plain `--force`):

    git push --force-with-lease

After a merge, a normal push works.
```

- [ ] **Step 5: Verify the skills are well-formed**

```bash
python3 - <<'PY'
import pathlib, re
for p in sorted(pathlib.Path("plugins/keel/skills").glob("*/SKILL.md")):
    text = p.read_text()
    assert text.startswith("---\n"), p
    fm = text.split("---")[1]
    assert re.search(r"^name:\s*\S+", fm, re.M), p
    assert re.search(r"^description:\s*\S+", fm, re.M), p
    name = re.search(r"^name:\s*(\S+)", fm, re.M).group(1)
    assert name == p.parent.name, f"{p}: name {name} != dir {p.parent.name}"
    print("ok", p.parent.name)
PY
```
Expected: `ok start-work`, `ok finish-work`, `ok respond-to-review`, `ok sync`

- [ ] **Step 6: Commit**

```bash
git add plugins/keel/skills
git commit -m "feat: contributor-loop skills"
```

---

### Task 11: Landing, release, and meta skills

**Files:**
- Create: `plugins/keel/skills/review/SKILL.md`
- Create: `plugins/keel/skills/land/SKILL.md`
- Create: `plugins/keel/skills/release/SKILL.md`
- Create: `plugins/keel/skills/ship/SKILL.md`
- Create: `plugins/keel/skills/protect/SKILL.md`
- Create: `plugins/keel/skills/doctor/SKILL.md`

**Interfaces:**
- Consumes: rule IDs emitted by Task 5 (`protected-write`, `pr-edge`, `changelog`, `merge-strategy`, `review`, `capability`) — `doctor` explains these by name.
- Produces: six invocable skills.

- [ ] **Step 1: Write `review`**

`plugins/keel/skills/review/SKILL.md`:
```markdown
---
name: review
description: Use when reviewing a pull request - reads the full diff, evaluates it against the project's standards, and posts a review.
---

# Reviewing a pull request

## 1. Read it properly

    gh pr view <number>
    gh pr diff <number>

Read the whole diff, not a summary of it. Check out the branch and run the
tests if the change is non-trivial.

## 2. Evaluate

If `superpowers:requesting-code-review` is available, use it for the analysis.

Otherwise assess, in this order:

1. **Correctness** - does it do what it claims? What input breaks it?
2. **Tests** - is the new behaviour covered? Would the tests fail if the
   implementation were wrong?
3. **Scope** - does the diff contain anything the PR does not claim to do?
4. **Changelog** - is the Unreleased entry accurate and user-facing?

## 3. Post the review

Be specific. "This breaks when `items` is empty" is useful; "consider edge
cases" is not.

    gh pr review <number> --request-changes --body "..."
    gh pr review <number> --approve --body "..."
    gh pr review <number> --comment --body "..."

If you are the PR's author, GitHub will not let you approve. Post a `--comment`
review instead. With `reviewPolicy: review` that satisfies keel; with
`reviewPolicy: approval` it does not, and someone else must approve.

## 4. Report

Tell the user the verdict and whether it is ready for `keel:land`.
```

- [ ] **Step 2: Write `land`**

`plugins/keel/skills/land/SKILL.md`:
```markdown
---
name: land
description: Use when an approved pull request should be merged - checks the gates and merges with the strategy the repo's config requires.
---

# Landing a pull request

## 1. Check it is ready

    gh pr view <number> --json baseRefName,headRefName,reviewDecision,reviews,mergeable

Confirm:
- there is a review, and no outstanding `CHANGES_REQUESTED`
- `mergeable` is not `CONFLICTING` - if it is, the author needs `keel:sync`
- CI is passing

## 2. Use the configured strategy

Read `mergeStrategy` from `.keel.json`:

- into `integration` -> `--squash` (one changelog-worthy change, one commit)
- into `production` -> `--merge` (a release must preserve its history)

```
gh pr merge <number> --squash --delete-branch
gh pr merge <number> --merge
```

Do not delete the branch on a `production` merge - release branches are
sometimes needed again.

## 3. Report

Say what merged, into what, and what the next step is - usually
`keel:release` once enough has accumulated.
```

- [ ] **Step 3: Write `release`**

`plugins/keel/skills/release/SKILL.md`:
```markdown
---
name: release
description: Use when preparing a release - picks the version, rolls the changelog, and opens the release pull request.
---

# Preparing a release

## 1. See what is unreleased

    git log --oneline <production>..<integration>

Read the `Unreleased` section of `CHANGELOG.md`.

## 2. Choose the version

Semantic versioning, judged from the changes:

- **patch** - fixes only. Proceed.
- **minor** - anything added. **Confirm with the user first.**
- **major** - anything removed or changed incompatibly. **Confirm with the
  user first, and say what breaks.**

Never pick minor or major without asking.

## 3. Create the release branch

    git fetch origin
    git checkout -b <releasePrefix><version> origin/<integration>

## 4. Roll the changelog

Rename `## Unreleased` to `## <version> - YYYY-MM-DD` and add a fresh empty
`## Unreleased` above it. Use the real current date.

## 5. Open the PR

    gh pr create --base <production> --title "release: <version>" --body "..."

The body should be the changelog section for this version - it becomes the
release notes.

keel does not require a changelog entry or a review on release PRs; the content
was reviewed on the way into `integration`.

## 6. Report

Give the user the PR URL and tell them `keel:ship` comes after it merges.
```

- [ ] **Step 4: Write `ship`**

`plugins/keel/skills/ship/SKILL.md`:
```markdown
---
name: ship
description: Use after a release pull request has merged - tags the release, publishes notes, and back-merges into the integration branch.
---

# Shipping a release

## 1. Confirm the release PR merged

    gh pr list --state merged --base <production> --limit 5

Stop if it has not merged yet - `keel:release` comes first.

## 2. Tag the merge commit

    git checkout <production>
    git pull origin <production>
    git tag -a v<version> -m "v<version>"
    git push origin v<version>

Push the tag by name. keel exempts tag refs from the protected-branch rule, but
only the tag refs themselves - `git push origin <production> --tags` still
pushes the branch and is still blocked.

## 3. Publish the release

    gh release create v<version> --title "v<version>" --notes "..."

Use the changelog section for this version as the notes.

## 4. Back-merge into integration

Skip this entirely under `trunk` topology - there is no integration branch.

    git checkout <integration>
    git pull origin <integration>
    gh pr create --base <integration> --head <production> \
      --title "chore: back-merge v<version>" --body "..."

The tag commit must reach `integration` or the next release will show phantom
differences. keel exempts this PR from the changelog and review gates.

## 5. Report

Give the user the release URL and confirm the back-merge PR is open.
```

- [ ] **Step 5: Write `protect`**

`plugins/keel/skills/protect/SKILL.md`:
```markdown
---
name: protect
description: Use to configure GitHub branch protection so the workflow is actually enforced server-side rather than only advised by the hook.
---

# Configuring real enforcement

keel's hook is advisory - it runs only inside Claude Code and only catches
honest mistakes. **This skill sets up the enforcement that actually holds.**

## 1. Check you can

    gh repo view --json viewerPermission -q .viewerPermission

You need `ADMIN`. If you do not have it, tell the user what to ask their
administrator for and stop.

## 2. Confirm before changing anything

Branch protection affects every contributor, not just this session. Show the
user exactly what you are about to apply and get explicit approval first.

## 3. Protect the production branch

Requires a PR, at least one approving review, and passing checks:

    gh api -X PUT repos/{owner}/{repo}/branches/<production>/protection \
      -H "Accept: application/vnd.github+json" \
      -f "required_pull_request_reviews[required_approving_review_count]=1" \
      -F "enforce_admins=false" \
      -F "required_status_checks[strict]=true" \
      -f "required_status_checks[contexts][]=test" \
      -F "restrictions=null"

Under `reviewPolicy: review` (solo maintainers), set the review count to `0` -
GitHub forbids self-approval, so requiring 1 would lock a solo maintainer out
of their own repository.

## 4. Protect the integration branch

Same call against `<integration>`, unless topology is `trunk`.

## 5. Add the changelog check

The hook's changelog rule only binds inside Claude Code. To make it real, the
repo needs a CI job that fails when a feature PR does not add an `Unreleased`
entry. Offer to write `.github/workflows/changelog.yml` if one does not exist.

## 6. Report

List what is now enforced server-side versus what remains advisory. Be explicit
that anything not in the former list can be bypassed.
```

- [ ] **Step 6: Write `doctor`**

`plugins/keel/skills/doctor/SKILL.md`:
```markdown
---
name: doctor
description: Use when keel blocked something unexpectedly, or to understand the current repo's lifecycle state - explains what keel sees and why it decided what it did.
---

# keel doctor

## 1. Gather the state

    git rev-parse --show-toplevel
    git symbolic-ref --short HEAD
    git remote -v
    gh repo view --json viewerPermission -q .viewerPermission
    cat .keel.json

## 2. Report what keel sees

- config topology, protected branches, review policy
- current branch, and which kind keel classifies it as
- your permission level
- whether `gh` is authenticated (`gh auth status`)

## 3. Explain the block

If keel denied something, the message carried a rule name in brackets. What
each one means:

- **`protected-write`** - the commit or push targets a protected branch. For a
  push, keel reads the *destination* refspec, so `git push origin HEAD:main`
  counts as targeting `main` even from a feature branch. Use `keel:start-work`.
- **`pr-edge`** - the PR's head and base are not a valid pair for this
  topology. Feature branches go to integration; releases and hotfixes go to
  production.
- **`changelog`** - the `Unreleased` section of `CHANGELOG.md` did not gain
  content on this branch. Whitespace does not count.
- **`merge-strategy`** - PRs into integration squash; PRs into production use a
  merge commit.
- **`review`** - no review yet, or changes are still requested, or
  `reviewPolicy` is `approval` and only a comment exists.
- **`capability`** - a warning only. keel thinks you may lack merge permission.

## 4. Explain a warning

Warnings mean keel could not determine something and let the action proceed.
The usual cause is a missing base ref - run `git fetch` and retry.

## 5. Say what keel does not do

If the user is surprised keel allowed something: the hook is advisory. It runs
only inside Claude Code, does not parse shell constructs adversarially, and is
not a security boundary. `keel:protect` configures the enforcement that is.
```

- [ ] **Step 7: Verify all ten skills are well-formed**

Run the same validation script from Task 10 Step 5.
Expected: ten `ok <name>` lines.

- [ ] **Step 8: Commit**

```bash
git add plugins/keel/skills
git commit -m "feat: landing, release, and meta skills"
```

---

### Task 12: Documentation and release

**Files:**
- Create: `README.md`
- Create: `CHANGELOG.md`
- Create: `LICENSE`
- Create: `.keel.json` (keel manages itself)

**Interfaces:**
- Consumes: everything.
- Produces: an installable, documented `v0.1.0`.

- [ ] **Step 1: Write the README**

`README.md` must cover, in this order: what keel is; the advisory-vs-enforced
distinction stated plainly near the top; install (`/plugin marketplace add
submtd/shipyard` then `/plugin install keel@shipyard`); a `.keel.json` reference
table with every field, its default, and its allowed values as implemented in
`keel/config.py`; the ten skills in lifecycle order with one line each; the six
rule names matching `keel/rules.py`; and a "what keel does not do" section
listing: it only runs inside Claude Code, it does not parse shell constructs
adversarially, and it is not a security boundary.

- [ ] **Step 2: Add `.keel.json` so keel manages itself**

```json
{
  "topology": "gitflow",
  "branches": { "production": "main", "integration": "develop" },
  "contributions": "both",
  "reviewPolicy": "review",
  "requireChangelog": true
}
```

- [ ] **Step 3: Add CHANGELOG.md and LICENSE**

`CHANGELOG.md`:
```markdown
# Changelog

## Unreleased

## 0.1.0 - 2026-07-20

### Added

- Initial release: rule engine, advisory PreToolUse guard, SessionStart
  orientation, and ten lifecycle skills.
```

`LICENSE`: MIT, copyright 2026 Steve Harmeyer.

- [ ] **Step 4: Verify the whole suite passes**

Run: `python3 -m pytest -v`
Expected: all tests pass. Record the count.

- [ ] **Step 5: Install the plugin locally and verify it loads**

```
/plugin marketplace add ~/Development/submtd/shipyard
/plugin install keel@shipyard
```

Then open a session in a test repo with a `.keel.json` and confirm: orientation
appears once at startup, and `git commit -m x` on `main` is denied with a
`[keel/protected-write]` message.

**If the skill frontmatter field for tool restriction matters, verify it here** —
check whether `tools:` or `allowed-tools:` is honoured, and only then add it to
the ten skills. This is the one item deliberately left unresolved in the plan.

- [ ] **Step 6: Commit**

```bash
git add README.md CHANGELOG.md LICENSE .keel.json
git commit -m "docs: README, changelog, license, and self-hosted keel config"
```

---

## Self-Review

**Spec coverage.** Every spec section maps to a task: hybrid enforcement → Tasks 8 + 11
(`protect`); action-keyed rules → Task 5; capability from GitHub → Task 7; `.keel.json` →
Task 2; the six rules → Task 5; dropped CLAUDE.md gate → Task 10 (`finish-work` step 3
prompts instead); runtime fixes → Tasks 6–9; ten skills → Tasks 10–11; tests + CI → Tasks 1–7.

**Regression coverage.** Each verified bug has a named test: `git push origin main --tags`
(Task 5, `test_mixed_tag_and_protected_branch_push_blocks`), `git push origin HEAD:main`
(Task 5, `test_push_to_protected_destination_blocks_from_feature_branch`), the phantom push
from a quoted message (Task 3, `test_quoted_separator_does_not_fabricate_actions`), the
same-repo review bypass (Task 5, `test_same_repo_pr_still_requires_review`), silent config
failure (Task 2, `test_malformed_json_raises_loudly`), slug case-sensitivity (Task 6,
`test_origin_slug_is_lowercased`), and five `gh` calls (Task 7, `test_pr_facts_parses_single_call`).

**Known gap, deliberate.** `Facts.pr_is_fork` is gathered and stored but no rule consumes it —
rules apply identically to fork and same-repo PRs, which is the point. It is retained because
`doctor` reports it and a future `contributions: fork` rule will need it.

**Out of scope, tracked for increment 2:** `keel:init`, `.github/` issue and PR templates,
CODEOWNERS, and the `changelog.yml` workflow that `protect` step 5 offers to write.
