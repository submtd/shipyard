"""Drift guard: shipyard's own dependabot.yml must be exactly bosun's
rendered output.

Mirrors rigging/tests/test_dogfood.py, ballast/tests/test_dogfood.py, and
hull/tests/test_dogfood.py: the committed root `.bosun.json` is the durable
record, and the committed `.github/dependabot.yml` is bosun's rendered
output from it. This test proves that relationship holds byte-for-byte, and
ties the golden fixture (`golden/shipyard.yml`, authored by hand) to the
actual committed file so the two can never silently drift apart.

Regenerate with:
    python3 -c "import sys, os; sys.path.insert(0,'plugins/bosun'); \
from bosun.config import load_config; from bosun.plan import build_plan; \
from bosun.render import render; from pathlib import Path; \
os.makedirs('.github', exist_ok=True); \
open('.github/dependabot.yml','w').write(render(build_plan(load_config(Path('.')))))"
"""
from __future__ import annotations

from pathlib import Path

from bosun.config import load_config
from bosun.plan import build_plan
from bosun.render import render

REPO = Path(__file__).resolve().parents[3]


def _rendered() -> str:
    return render(build_plan(load_config(REPO)))


def test_repo_bosun_json_loads():
    assert load_config(REPO) is not None


def test_dependabot_yml_matches_rendered_output_byte_for_byte():
    committed = (REPO / ".github/dependabot.yml").read_text()
    assert _rendered() == committed


def test_dependabot_yml_has_github_actions_entry():
    assert 'package-ecosystem: "github-actions"' in _rendered()


def test_dependabot_yml_is_declarative_only():
    rendered = _rendered()
    assert "${{" not in rendered
    assert "run:" not in rendered


def test_golden_fixture_matches_committed_dependabot_yml():
    golden = (REPO / "plugins/bosun/tests/golden/shipyard.yml").read_text()
    committed = (REPO / ".github/dependabot.yml").read_text()
    assert golden == committed
