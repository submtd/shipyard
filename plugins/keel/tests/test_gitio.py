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


def test_origin_slug_https_trailing_slash(tmp_path):
    repo, git = init_repo(tmp_path)
    git("remote", "add", "origin", "https://github.com/Owner/Repo/")
    assert gitio.origin_slug(cwd=repo) == "owner/repo"


def test_origin_slug_local_path_is_none(tmp_path):
    # Finding 5: a bare local filesystem remote must not yield a slug --
    # matching any two trailing path segments produced a confident, wrong
    # owner/repo (e.g. "repos/myproject").
    repo, git = init_repo(tmp_path)
    other = tmp_path.parent / "repos" / "myproject"
    git("remote", "add", "origin", str(other))
    assert gitio.origin_slug(cwd=repo) is None


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
