import pytest

from bosun.detect import detect_ecosystems


@pytest.mark.parametrize(
    "marker", ["pyproject.toml", "setup.py", "setup.cfg", "requirements.txt"]
)
def test_python_marker_alone_detects_python(tmp_path, marker):
    (tmp_path / marker).write_text("")
    assert detect_ecosystems(tmp_path) == ("python",)


def test_package_json_alone_detects_node(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert detect_ecosystems(tmp_path) == ("node",)


def test_python_marker_and_package_json_detects_both_in_registry_order(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "package.json").write_text("{}")
    assert detect_ecosystems(tmp_path) == ("python", "node")


def test_empty_dir_detects_nothing(tmp_path):
    assert detect_ecosystems(tmp_path) == ()


def test_multiple_python_markers_still_single_python_entry(tmp_path):
    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "requirements.txt").write_text("")
    assert detect_ecosystems(tmp_path) == ("python",)


def test_returns_tuple(tmp_path):
    assert isinstance(detect_ecosystems(tmp_path), tuple)


def test_github_actions_never_detected_even_with_workflows(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: ci\n")
    assert detect_ecosystems(tmp_path) == ()


def test_github_actions_never_detected_alongside_other_ecosystems(tmp_path):
    workflows = tmp_path / ".github" / "workflows"
    workflows.mkdir(parents=True)
    (workflows / "ci.yml").write_text("name: ci\n")
    (tmp_path / "package.json").write_text("{}")
    assert detect_ecosystems(tmp_path) == ("node",)
