import json

import pytest

from rigging.detect import detect_stacks


@pytest.mark.parametrize("marker", ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"])
def test_python_marker_alone_detects_python(tmp_path, marker):
    (tmp_path / marker).write_text("")
    assert detect_stacks(tmp_path) == ("python",)


def test_package_json_alone_detects_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_stacks(tmp_path) == ("node",)


def test_python_marker_and_package_json_detects_both_in_registry_order(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    assert detect_stacks(tmp_path) == ("python", "node")


def test_empty_dir_detects_nothing(tmp_path):
    assert detect_stacks(tmp_path) == ()


def test_multiple_python_markers_still_single_python_entry(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "requirements.txt").write_text("")
    assert detect_stacks(tmp_path) == ("python",)


def test_returns_tuple(tmp_path):
    assert isinstance(detect_stacks(tmp_path), tuple)


def test_a_directory_named_like_a_marker_detects_nothing(tmp_path):
    """Markers are files. A *directory* named 'pyproject.toml' -- a vendored
    tree, an unpacked artifact, a stray mkdir -- satisfied .exists(), so a
    whole stack was scaffolded off a path holding no configuration at all."""
    (tmp_path / "pyproject.toml").mkdir()
    assert detect_stacks(tmp_path) == ()


# --- JS package manager selection (issue #24 / #26) -----------------------
#
# Every pnpm/yarn/bun repo has a package.json, so every one of them detected
# as "node". Rigging used to refuse all of them; now it selects the manager
# that is actually in charge and only refuses when the choice would be a
# guess (see the node_package_manager tests further down). These two remain
# genuinely refused because neither declares the information their setup
# action needs; bun needs no such declaration, so it is no longer among them.

from rigging.detect import unsupported_reasons


@pytest.mark.parametrize(
    "lockfile,marker",
    [
        ("pnpm-lock.yaml", "pnpm-lock.yaml"),
        ("yarn.lock", "yarn.lock"),
    ],
)
def test_foreign_lockfile_without_declared_version_makes_node_unsupported(tmp_path, lockfile, marker):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("")
    reasons = unsupported_reasons(tmp_path)
    assert set(reasons) == {"node"}
    reason = reasons["node"]
    # The reason has to be actionable on its own: it is the only diagnosis
    # the user sees, so it must name the marker and what to declare.
    assert marker in reason
    assert "packageManager" in reason


@pytest.mark.parametrize("lockfile", ["bun.lockb", "bun.lock"])
def test_bun_lockfile_alone_is_supported(tmp_path, lockfile):
    """bun needs no `packageManager` declaration the way pnpm/yarn do, so a
    bare bun lockfile is enough to select it -- unlike its pnpm/yarn
    siblings above, this is no longer a refusal."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("")
    assert unsupported_reasons(tmp_path) == {}


def test_node_still_detected_even_when_unsupported(tmp_path):
    """Silently dropping node from detection would leave the repo with no
    workflow and no statement about why -- the failure mode this rejects."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert detect_stacks(tmp_path) == ("node",)


def test_package_manager_field_naming_pnpm_is_supported(tmp_path):
    """A declared `packageManager` naming pnpm is exactly what pnpm/action-setup
    needs -- this used to be refused; it is now the positive case."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    assert unsupported_reasons(tmp_path) == {}


def test_package_manager_field_naming_npm_does_not_fire(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "npm@10"}')
    assert unsupported_reasons(tmp_path) == {}


def test_plain_npm_repo_with_lockfile_does_not_fire(tmp_path):
    (tmp_path / "package.json").write_text('{"scripts": {"test": "jest"}}')
    (tmp_path / "package-lock.json").write_text("{}")
    assert unsupported_reasons(tmp_path) == {}


def test_invalid_json_package_json_does_not_crash_and_is_no_signal(tmp_path):
    """A package.json we cannot parse is not evidence that some other package
    manager is in charge -- and crashing here would leave the repo with no
    scaffold AND no diagnosis, strictly worse than the bug being guarded."""
    (tmp_path / "package.json").write_text("{ this is not json ")
    assert unsupported_reasons(tmp_path) == {}
    assert detect_stacks(tmp_path) == ("node",)


def test_invalid_json_package_json_still_refused_when_a_foreign_lockfile_exists(tmp_path):
    (tmp_path / "package.json").write_text("{ this is not json ")
    (tmp_path / "yarn.lock").write_text("")
    assert set(unsupported_reasons(tmp_path)) == {"node"}


def test_package_json_that_is_a_top_level_array_is_no_signal(tmp_path):
    (tmp_path / "package.json").write_text("[1, 2, 3]")
    assert unsupported_reasons(tmp_path) == {}


def test_non_string_package_manager_field_is_no_signal(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": 7}')
    assert unsupported_reasons(tmp_path) == {}


def test_python_only_repo_is_unaffected(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    assert unsupported_reasons(tmp_path) == {}


def test_python_stack_is_never_reported_unsupported_beside_a_pnpm_repo(tmp_path):
    """Polyglot repo: python is still drivable, so init scaffolds it and
    omits node -- the reason names node only."""
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert detect_stacks(tmp_path) == ("python", "node")
    assert set(unsupported_reasons(tmp_path)) == {"node"}


def test_a_directory_named_like_a_lockfile_does_not_fire(tmp_path):
    """Same reasoning as detect_stacks' is_file check: a *directory* named
    yarn.lock records no dependency graph, so refusing off one would be as
    wrong as scaffolding off one."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "yarn.lock").mkdir()
    assert unsupported_reasons(tmp_path) == {}


def test_lockfile_without_package_json_reports_nothing(tmp_path):
    """node was never detected, so there is nothing to refuse."""
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert detect_stacks(tmp_path) == ()
    assert unsupported_reasons(tmp_path) == {}


def test_empty_repo_reports_nothing(tmp_path):
    assert unsupported_reasons(tmp_path) == {}


def test_returns_a_dict(tmp_path):
    assert isinstance(unsupported_reasons(tmp_path), dict)


# --- node_package_manager selection (issue #26) ---------------------------

from rigging.detect import node_package_manager


@pytest.mark.parametrize("lockfile,expected", [
    ("package-lock.json", "npm"),
    # pnpm is deliberately absent here: it needs a declared version too, and
    # has its own pair of tests below.
    ("bun.lockb", "bun"),
    ("bun.lock", "bun"),
])
def test_lockfile_selects_the_manager(tmp_path, lockfile, expected):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("")
    assert node_package_manager(tmp_path) == (expected, None)


def test_bare_package_json_is_npm(tmp_path):
    """npm ships with node, so no other manager's marker IS the signal."""
    (tmp_path / "package.json").write_text("{}")
    assert node_package_manager(tmp_path) == ("npm", None)


def test_package_manager_field_selects_when_no_lockfile(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    assert node_package_manager(tmp_path) == ("pnpm", None)


@pytest.mark.parametrize("declared,expected", [
    ("yarn@1.22.19", "yarn1"),
    ("yarn@3.6.4", "yarn-berry"),
    ("yarn@4.0.0", "yarn-berry"),
])
def test_yarn_major_selects_the_toolchain(tmp_path, declared, expected):
    (tmp_path / "package.json").write_text(json.dumps({"packageManager": declared}))
    (tmp_path / "yarn.lock").write_text("")
    assert node_package_manager(tmp_path) == (expected, None)


def test_yarn_lockfile_without_a_declared_major_is_refused(tmp_path):
    """Yarn 1 takes --frozen-lockfile and berry takes --immutable; each is an
    error on the other. yarn.lock does not say which, and guessing produces a
    workflow that dies on its install step -- the exact outcome the refusal
    machinery exists to prevent."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "yarn.lock" in reason
    assert "packageManager" in reason


def test_pnpm_without_a_declared_version_is_refused(tmp_path):
    """pnpm/action-setup reads its version from package.json's
    `packageManager` field and errors when that field is absent and no
    version is pinned. Selecting pnpm off the lockfile alone would render a
    job that dies on its setup step -- the exact failure this module exists
    to prevent."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "packageManager" in reason
    assert "pnpm-lock.yaml" in reason


def test_pnpm_with_a_declared_version_is_selected(tmp_path):
    """The field the refusal above asks for is exactly what makes it work."""
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert node_package_manager(tmp_path) == ("pnpm", None)


def test_two_manager_lockfiles_are_refused_naming_both(tmp_path):
    """Mid-migration or a stale file. Either answer is as likely wrong as
    right, so precedence would be a coin flip wearing a rule's clothing."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "pnpm-lock.yaml" in reason and "yarn.lock" in reason


def test_lockfile_disagreeing_with_declared_manager_is_refused(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    (tmp_path / "yarn.lock").write_text("")
    manager, reason = node_package_manager(tmp_path)
    assert manager is None
    assert "pnpm" in reason and "yarn.lock" in reason


def test_unparseable_package_json_is_not_a_refusal(tmp_path):
    """A package.json we cannot read is not evidence of anything. With a
    lockfile present the lockfile still decides."""
    (tmp_path / "package.json").write_text("{ not json")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert node_package_manager(tmp_path) == ("pnpm", None)


def test_no_package_json_reports_nothing(tmp_path):
    assert node_package_manager(tmp_path) == (None, None)
