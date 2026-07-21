"""Render a DependabotPlan to deterministic dependabot.yml YAML.

Pure module: no subprocess, no os, no networking. Hand-rolled emitter (no
`yaml` dependency) so we control quoting exactly -- `_quote` is ported
unchanged from hull's and rigging's render.py (see those modules'
docstrings for the full quoting rationale). Every scalar VALUE we emit is
double-quoted, which is what keeps an ecosystem id, directory, or interval
from ever being read back by a YAML loader as anything but a string. The
top-level `version:` is the one exception: Dependabot requires the bare
integer literal `2`, not the string `"2"`.

dependabot.yml is purely declarative -- there is no `run:`/`uses:` step and
no `${{ }}` expression syntax anywhere in this schema (`directory` is
always fixed at `"/"` by plan.build_plan, never user-supplied text passed
through unescaped). So unlike hull and rigging there is no injection
surface here, and nothing analogous to `iter_run_blocks` to port. The
declarative-only invariant (no `${{`, no `run:` line) is asserted directly
in test_render.py.
"""
from __future__ import annotations

from bosun.plan import DependabotPlan, Update


def _quote(value: str) -> str:
    """Render `value` as a double-quoted YAML scalar, escaping ``\\`` and ``"``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _update_lines(update: Update) -> list[str]:
    return [
        f"  - package-ecosystem: {_quote(update.package_ecosystem)}",
        f"    directory: {_quote(update.directory)}",
        "    schedule:",
        f"      interval: {_quote(update.interval)}",
    ]


def render(plan: DependabotPlan) -> str:
    """Render `plan` to deterministic dependabot.yml text.

    Same plan in -> byte-identical text out, every call.
    """
    lines = [
        f"version: {plan.version}",
        "updates:",
    ]
    for update in plan.updates:
        lines.extend(_update_lines(update))
    return "\n".join(lines) + "\n"
