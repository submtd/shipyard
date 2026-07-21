"""Dogfood: ballast configures shipyard's own pytest runner.

Shipyard's root `.ballast.json` is the durable record of this repo's pytest
configuration; the committed root `pytest.ini` is ballast's rendered output
from it. This test proves that relationship holds byte-for-byte, so a stale
`.ballast.json` or a stale `pytest.ini` (someone hand-edited one without the
other) is caught here rather than discovered later as a CI collection
mystery.
"""
from __future__ import annotations

from pathlib import Path

from ballast.config import load_config
from ballast.render import render

REPO = Path(__file__).resolve().parents[3]


def test_repo_ballast_json_loads():
    assert load_config(REPO) is not None


def test_render_of_repo_config_matches_committed_pytest_ini_byte_for_byte():
    config = load_config(REPO)
    rendered = render(config)
    on_disk = (REPO / "pytest.ini").read_text()
    assert rendered == on_disk


def test_rendered_testpaths_include_ballasts_own_tests():
    config = load_config(REPO)
    rendered = render(config)
    assert "plugins/ballast/tests" in rendered
