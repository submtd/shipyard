from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
TEMPLATES = REPO / "plugins" / "keel" / "templates"

# Every template file keel:init's SKILL.md (section 4) copies into a target
# repo, plus keel.scaffold.LIFECYCLE_FILES' template-backed entries. Listed
# explicitly (not derived from LIFECYCLE_FILES) so the set is easy to read
# and to keep in sync by hand -- `test_all_templates_are_nonempty` below only
# catches emptiness in files that exist; this catches a shipped template
# being deleted outright, which would otherwise pass vacuously.
EXPECTED_TEMPLATES = [
    "CHANGELOG.md",
    "CODEOWNERS",
    "PULL_REQUEST_TEMPLATE.md",
    "ISSUE_TEMPLATE/bug_report.md",
    "ISSUE_TEMPLATE/feature_request.md",
    "changelog.yml",
    "check_changelog.py",
]


def test_expected_templates_all_exist():
    missing = [name for name in EXPECTED_TEMPLATES if not (TEMPLATES / name).is_file()]
    assert not missing, f"missing expected template file(s): {missing}"


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


def test_changelog_workflow_references_the_changelog_script():
    # Pins the workflow-invokes-the-script invariant: the two are a linked
    # pair (SKILL.md section 3), and a scaffolded changelog.yml that doesn't
    # actually call check_changelog.py would be a silently broken gate.
    text = (TEMPLATES / "changelog.yml").read_text()
    assert "scripts/check_changelog.py" in text


def test_codeowners_template_has_no_active_rule():
    """The template shipped `*  @REPLACE-WITH-OWNER` as a LIVE rule. GitHub
    resolves owners and rejects the whole file as invalid when one does not
    exist -- and once keel:protect turns on code-owner review, every PR in
    the scaffolded repo becomes unmergeable until someone notices. A
    scaffold must be inert until edited, so every non-comment line here has
    to be commented out."""
    rules = [
        line for line in (TEMPLATES / "CODEOWNERS").read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not rules, f"CODEOWNERS template ships active rule(s): {rules}"
