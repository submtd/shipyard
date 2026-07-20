from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "plugins" / "keel" / "templates"


def test_all_templates_are_nonempty():
    for path in TEMPLATES.rglob("*"):
        if path.is_file():
            assert path.read_text().strip(), f"{path} is empty"


def test_changelog_template_has_unreleased_section():
    text = (TEMPLATES / "CHANGELOG.md").read_text()
    assert "## [Unreleased]" in text


def test_check_changelog_template_matches_repos_own_copy():
    # One source of truth: the template init ships must be byte-identical to the
    # copy this repo runs in CI, so a fix to one can't silently diverge.
    template = (TEMPLATES / "check_changelog.py").read_text()
    live = (REPO / "scripts" / "check_changelog.py").read_text()
    assert template == live, "templates/check_changelog.py has drifted from scripts/check_changelog.py"


def test_changelog_workflow_template_matches_repos_own_copy():
    template = (TEMPLATES / "changelog.yml").read_text()
    live = (REPO / ".github" / "workflows" / "changelog.yml").read_text()
    assert template == live, "templates/changelog.yml has drifted from .github/workflows/changelog.yml"
