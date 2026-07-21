import subprocess
from pathlib import Path

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


# --- Important 6: base ref falls back to origin/<base> when the bare local
# branch does not exist (a fresh clone that only ever checked out the
# feature branch never has 'develop' locally). ------------------------------

def test_changelog_gained_content_falls_back_to_origin_base(tmp_path):
    upstream = tmp_path / "upstream"
    upstream.mkdir()

    def git_up(*args):
        subprocess.run(["git", *args], cwd=upstream, check=True,
                       capture_output=True, text=True)
    git_up("init", "-q", "-b", "main")
    git_up("config", "user.email", "t@example.com")
    git_up("config", "user.name", "T")
    (upstream / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
    git_up("add", "-A")
    git_up("commit", "-qm", "init")

    clone = tmp_path / "clone"
    subprocess.run(["git", "clone", "-q", str(upstream), str(clone)],
                   check=True, capture_output=True, text=True)

    def git(*args):
        subprocess.run(["git", *args], cwd=clone, check=True,
                       capture_output=True, text=True)
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "T")
    git("checkout", "-qb", "feature/x")
    (clone / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Added a thing\n"
    )
    git("add", "-A")
    git("commit", "-qm", "entry")
    # Simulate a clone that only ever checked out the feature branch: drop
    # the local 'main' created automatically by `git clone`, leaving only
    # 'origin/main'.
    git("branch", "-D", "main")

    assert gitio.run_git(["rev-parse", "--verify", "--quiet", "main"], cwd=clone) is None
    assert gitio.changelog_gained_content("main", cwd=clone) is True


# --- Finding 1: nested subheadings inside Unreleased -----------------------

def test_unreleased_body_keeps_a_changelog_layout():
    text = (
        "# Changelog\n\n"
        "## [Unreleased]\n\n"
        "### Added\n"
        "- A genuinely new feature\n"
    )
    body = gitio._unreleased_body(text)
    assert "A genuinely new feature" in body
    assert body.strip() != ""


def test_unreleased_body_flat_bullets():
    text = "## Unreleased\n\n- Added a thing\n- Fixed a bug\n"
    body = gitio._unreleased_body(text)
    assert "Added a thing" in body
    assert "Fixed a bug" in body


def test_unreleased_body_deeper_nesting():
    text = (
        "### Unreleased\n\n"
        "#### Added\n"
        "- Something new\n"
    )
    body = gitio._unreleased_body(text)
    assert "Something new" in body


def test_unreleased_body_stops_at_same_level_release_heading():
    text = (
        "## [Unreleased]\n\n"
        "### Added\n"
        "- A genuinely new feature\n\n"
        "## 1.0.0\n\n"
        "### Added\n"
        "- Old release content\n"
    )
    body = gitio._unreleased_body(text)
    assert "A genuinely new feature" in body
    assert "Old release content" not in body


def test_changelog_gained_content_keep_a_changelog_layout(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## [Unreleased]\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    git("checkout", "-qb", "feature/x")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## [Unreleased]\n\n### Added\n- A genuinely new feature\n"
    )
    git("add", "-A"); git("commit", "-qm", "entry")
    assert gitio.changelog_gained_content("main", cwd=repo) is True


# --- Finding 2: compare HEAD, not the working tree -------------------------

def test_changelog_gained_content_ignores_uncommitted_edits(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    git("checkout", "-qb", "feature/x")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Added a thing\n"
    )
    git("add", "-A"); git("commit", "-qm", "entry")
    # Now edit the working tree further WITHOUT committing.
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Added a thing\n- Uncommitted extra\n"
    )
    # HEAD already gained content relative to main, so this should still be
    # True (from the committed entry), and must not vary based on the
    # uncommitted edit.
    assert gitio.changelog_gained_content("main", cwd=repo) is True

    # Reset to prove the uncommitted edit itself is not what satisfies it:
    # start a fresh branch with NO committed changelog change at all, then
    # make an uncommitted-only edit -- the gate must not see it.
    git("checkout", "-q", "--", "CHANGELOG.md")
    git("checkout", "-q", "main")
    git("checkout", "-qb", "feature/y")
    (repo / "CHANGELOG.md").write_text(
        "# Changelog\n\n## Unreleased\n\n- Uncommitted only, never committed\n"
    )
    assert gitio.changelog_gained_content("main", cwd=repo) is False


# --- Finding 3: failed git show is not silently empty ----------------------

def test_changelog_gained_content_none_when_base_ref_unresolvable(tmp_path):
    repo, git = init_repo(tmp_path)
    # merge-base succeeds trivially against HEAD itself only if it resolves;
    # simulate a merge-base result that doesn't correspond to a real commit
    # by pointing "base" at a bogus but syntactically valid-looking ref.
    # (merge_base itself would already be None here in the ordinary case;
    # this test targets the show-failure path directly.)
    before = gitio._changelog_at_ref("deadbeefdeadbeefdeadbeefdeadbeefdeadbeef", cwd=repo)
    assert before is None


def test_changelog_at_ref_absent_file_is_empty_string(tmp_path):
    repo, git = init_repo(tmp_path)
    # No CHANGELOG.md committed at all -- legitimately absent, not a failure.
    assert gitio._changelog_at_ref("HEAD", cwd=repo) == ""


def test_changelog_at_ref_present_file_returns_content(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n\n## Unreleased\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    assert "Unreleased" in gitio._changelog_at_ref("HEAD", cwd=repo)


# --- Finding 4: changelog_present -------------------------------------------

def test_changelog_present_true(tmp_path):
    repo, git = init_repo(tmp_path)
    (repo / "CHANGELOG.md").write_text("# Changelog\n")
    git("add", "-A"); git("commit", "-qm", "changelog")
    assert gitio.changelog_present(cwd=repo) is True


def test_changelog_present_false_when_absent(tmp_path):
    repo, _ = init_repo(tmp_path)
    assert gitio.changelog_present(cwd=repo) is False


def test_changelog_present_none_outside_repo(tmp_path):
    assert gitio.changelog_present(cwd=tmp_path) is None


def test_target_cwd_honours_cd():
    assert gitio.target_cwd("cd /other && git commit -m x", "/here") == "/other"


def test_target_cwd_honours_git_C():
    assert gitio.target_cwd("git -C /other commit -m x", "/here") == "/other"


def test_target_cwd_defaults():
    assert gitio.target_cwd("git commit -m x", "/here") == "/here"


# --- Critical 1: -C/-c AFTER the subcommand is a commit flag, not a cwd
# override. `git commit -C HEAD~1` reuses HEAD~1's message; it must not be
# mistaken for the global `-C <path>` flag. ---------------------------------

def test_target_cwd_ignores_dash_cap_c_after_subcommand():
    assert gitio.target_cwd("git commit -C HEAD~1 -m x", "/here") == "/here"


def test_target_cwd_ignores_dash_c_after_subcommand():
    assert gitio.target_cwd("git commit -c HEAD~1", "/here") == "/here"


def test_target_cwd_honours_git_dir_before_subcommand():
    # Resolves to the work tree, not to the .git directory itself -- see
    # test_target_cwd_maps_a_git_dir_to_its_work_tree.
    assert gitio.target_cwd("git --git-dir /other/.git commit -m x", "/here") == "/other"


def test_target_cwd_honours_work_tree_before_subcommand():
    assert gitio.target_cwd("git --work-tree /other commit -m x", "/here") == "/other"


# --- Resolution defects: each one silently disabled the guard. An
# unresolvable cwd makes repo_root() return None, and the hook then returns
# without evaluating a single rule -- no block, no message, nothing. ------


def test_target_cwd_resolves_a_relative_cd_against_the_default():
    """`cd packages/api && git commit` is the normal monorepo shape. Returned
    bare, 'packages/api' is not a directory relative to the hook's process
    cwd, so the guard silently switched off for every such command."""
    assert gitio.target_cwd(
        "cd packages/api && git commit -m x", "/repo") == "/repo/packages/api"


def test_target_cwd_leaves_an_absolute_cd_alone():
    assert gitio.target_cwd("cd /other && git commit -m x", "/repo") == "/other"


def test_target_cwd_expands_a_tilde():
    home = str(Path.home())
    assert gitio.target_cwd("cd ~/work/repo && git commit -m x", "/repo") == \
        f"{home}/work/repo"


def test_target_cwd_honours_the_equals_form_of_git_dir():
    """`--git-dir=<path>` is as common as the space-separated form; git
    itself accepts both. Only the space form was recognised."""
    assert gitio.target_cwd(
        "git --git-dir=/other/.git commit -m x", "/repo") == "/other"


def test_target_cwd_does_not_invent_an_equals_form_for_short_flags():
    """git's own parser accepts `--git-dir=<path>` but not `-C=<path>` -- for
    `-C` the path must be a separate argument. Accepting `-C=/other` here
    would resolve a path git never used."""
    assert gitio.target_cwd("git -C=/other commit -m x", "/repo") == "/repo"


def test_target_cwd_maps_a_git_dir_to_its_work_tree():
    """--git-dir names the .git directory, but git cannot run `rev-parse
    --show-toplevel` from inside one -- so returning it unchanged failed the
    guard open just as surely as returning nothing."""
    assert gitio.target_cwd(
        "git --git-dir /other/.git commit -m x", "/repo") == "/other"


def test_target_cwd_leaves_a_bare_repo_git_dir_alone():
    """A bare repo's git dir is not named '.git' and has no work tree above
    it; stripping a component would point somewhere unrelated."""
    assert gitio.target_cwd(
        "git --git-dir /srv/repo.git commit -m x", "/repo") == "/srv/repo.git"


def test_target_cwd_prefers_work_tree_over_git_dir():
    """When both are given, the work tree is the directory commands act on."""
    assert gitio.target_cwd(
        "git --git-dir /other/.git --work-tree /wt commit -m x", "/repo") == "/wt"


def test_target_cwd_ignores_a_cd_it_cannot_resolve():
    """`cd -` is the previous directory, which we have no way to know. Better
    to evaluate against the default than to invent a path."""
    assert gitio.target_cwd("cd - && git commit -m x", "/repo") == "/repo"
