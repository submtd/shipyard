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
