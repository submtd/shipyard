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


# --- unsupported JS toolchains (issue #24) --------------------------------
#
# Every pnpm/yarn/bun repo has a package.json, so every one of them detected
# as "node" and was handed an `npm ci` workflow that died on its first step.
# Detection still reports node; the reason is surfaced separately, and the
# init skill is what stops on it.

from rigging.detect import unsupported_reasons


@pytest.mark.parametrize(
    "lockfile,manager",
    [
        ("pnpm-lock.yaml", "pnpm"),
        ("yarn.lock", "yarn"),
        ("bun.lockb", "bun"),
        ("bun.lock", "bun"),
    ],
)
def test_foreign_lockfile_makes_node_unsupported(tmp_path, lockfile, manager):
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / lockfile).write_text("")
    reasons = unsupported_reasons(tmp_path)
    assert set(reasons) == {"node"}
    reason = reasons["node"]
    # The reason has to be actionable on its own: it is the only diagnosis
    # the user sees, so it must name the marker, the manager it implies, the
    # steps that cannot work, and the refusal itself.
    assert lockfile in reason
    assert manager in reason
    assert "npm ci" in reason
    assert "npm test" in reason
    assert "will not scaffold a workflow that cannot pass" in reason


def test_node_still_detected_even_when_unsupported(tmp_path):
    """Silently dropping node from detection would leave the repo with no
    workflow and no statement about why -- the failure mode this rejects."""
    (tmp_path / "package.json").write_text("{}")
    (tmp_path / "pnpm-lock.yaml").write_text("")
    assert detect_stacks(tmp_path) == ("node",)


def test_package_manager_field_naming_pnpm_makes_node_unsupported(tmp_path):
    (tmp_path / "package.json").write_text('{"packageManager": "pnpm@9.12.0"}')
    reasons = unsupported_reasons(tmp_path)
    assert set(reasons) == {"node"}
    assert "packageManager" in reasons["node"]
    assert "pnpm" in reasons["node"]


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
