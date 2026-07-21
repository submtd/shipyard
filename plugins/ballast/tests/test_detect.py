import pytest

from ballast.detect import detect_stacks


@pytest.mark.parametrize("marker", ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"])
def test_python_marker_alone_detects_python(tmp_path, marker):
    (tmp_path / marker).write_text("")
    assert detect_stacks(tmp_path) == ("python",)


def test_node_only_repo_detects_nothing(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_stacks(tmp_path) == ()


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
