"""Drift guard: shipyard's own ci.yml must be exactly rigging's rendered output.

Regenerate with:
    python3 -c "import sys; sys.path.insert(0,'plugins/rigging'); \
from rigging.config import load_config; from rigging.plan import build_plan; \
from rigging.render import render; from pathlib import Path; \
open('.github/workflows/ci.yml','w').write(render(build_plan(load_config(Path('.')))))"
"""
from __future__ import annotations

from pathlib import Path

from rigging.config import load_config
from rigging.plan import build_plan
from rigging.render import render
from rigging.scaffold import CI_FILES

REPO = Path(__file__).resolve().parents[3]


def _rendered() -> str:
    return render(build_plan(load_config(REPO)))


def test_ci_yml_matches_rendered_output_byte_for_byte():
    # Derived from the config rather than hardcoded, so this guard stays
    # pinned to whatever workflow filename the config actually names (see
    # CI_FILES: `.github/workflows/<cfg.name>.yml`), not a name assumed to
    # be "ci".
    cfg = load_config(REPO)
    committed = (REPO / CI_FILES(cfg.name)[1]).read_text()
    assert render(build_plan(cfg)) == committed


def test_ci_yml_runs_pytest():
    assert "python -m pytest" in _rendered()
