"""Drift guard: shipyard's own security.yml must be exactly hull's rendered output.

Mirrors rigging/tests/test_dogfood.py and ballast/tests/test_dogfood.py: the
committed root `.hull.json` is the durable record, and the committed
`.github/workflows/security.yml` is hull's rendered output from it. This
test proves that relationship holds byte-for-byte, and re-affirms (on the
actual committed file, not just a tmp_path fixture) the injection-safety
guarantee that plugins/hull/tests/test_injection.py enforces structurally:
the only `${{ }}` expression anywhere in the output is the whitelisted
`${{ secrets.GITHUB_TOKEN }}` form.

Regenerate with:
    python3 -c "import sys, os; sys.path.insert(0,'plugins/hull'); \
from hull.config import load_config; from hull.plan import build_plan; \
from hull.render import render; from pathlib import Path; \
os.makedirs('.github/workflows', exist_ok=True); \
open('.github/workflows/security.yml','w').write(render(build_plan(load_config(Path('.')))))"
"""
from __future__ import annotations

import re
from pathlib import Path

from hull.config import load_config
from hull.plan import build_plan
from hull.render import render

REPO = Path(__file__).resolve().parents[3]

WHITELIST_RE = re.compile(r"^\$\{\{\s*secrets\.GITHUB_TOKEN\s*\}\}$")
EXPRESSION_RE = re.compile(r"\$\{\{.*?\}\}")


def _rendered() -> str:
    return render(build_plan(load_config(REPO)))


def test_repo_hull_json_loads():
    assert load_config(REPO) is not None


def test_security_yml_matches_rendered_output_byte_for_byte():
    committed = (REPO / ".github/workflows/security.yml").read_text()
    assert _rendered() == committed


def test_security_yml_uses_the_registrys_gitleaks_pin():
    # Was named ..._v2 and hardcoded a v2 SHA; the name outlived the pin.
    # Reading the ref from the registry keeps this true across upgrades
    # while still asserting the committed file uses what hull renders.
    from hull.scanners import REGISTRY

    assert REGISTRY["gitleaks"].action_ref in _rendered()


def test_security_yml_only_whitelisted_expression():
    expressions = EXPRESSION_RE.findall(_rendered())
    assert expressions, "expected at least one ${{ }} expression"
    for expr in expressions:
        assert WHITELIST_RE.fullmatch(expr), (
            f"expression {expr!r} is not the whitelisted "
            f"'${{{{ secrets.GITHUB_TOKEN }}}}' form"
        )
