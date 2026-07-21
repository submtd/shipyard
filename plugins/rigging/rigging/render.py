"""Render a CiPlan to deterministic GitHub Actions YAML.

Pure module: no subprocess, no os, no networking. Hand-rolled emitter (no
`yaml` dependency) so we control quoting exactly -- every scalar VALUE we
emit is double-quoted, which is what keeps a version like "3.10" from ever
being read back by a YAML loader as the float 3.1. Structural keys (job
ids, `uses`/`with`/`run`/`matrix` etc.) are left bare.
"""
from __future__ import annotations

import re

from rigging.plan import CiPlan

# Matches a single-line `- run: "<body>"` step as emitted by `render`.
_RUN_LINE_RE = re.compile(r'^\s*- run: "(.*)"\s*$')

# Reverses the escaping `_quote` applies: a backslash followed by any
# character is that character, unescaped.
_UNESCAPE_RE = re.compile(r'\\(.)')


def _quote(value: str) -> str:
    """Render `value` as a double-quoted YAML scalar, escaping ``\\`` and ``"``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _step_lines(step) -> list[str]:
    if step.run is not None:
        return [f"      - run: {_quote(step.run)}"]

    lines = [f"      - uses: {_quote(step.uses)}"]
    if step.with_:
        lines.append("        with:")
        for key, value in step.with_.items():
            lines.append(f"          {key}: {_quote(value)}")
    return lines


def _job_lines(job) -> list[str]:
    versions = ", ".join(_quote(version) for version in job.versions)
    lines = [
        f"  {job.id}:",
        f"    runs-on: {_quote(job.runs_on)}",
        "    strategy:",
        "      matrix:",
        f"        {job.matrix_var}: [{versions}]",
        "    steps:",
    ]
    for step in job.steps:
        lines.extend(_step_lines(step))
    return lines


def render(plan: CiPlan) -> str:
    """Render `plan` to deterministic GitHub Actions workflow YAML.

    Same plan in -> byte-identical text out, every call.
    """
    lines = [
        f"name: {plan.name}",
        "on: [push, pull_request]",
        "permissions:",
        "  contents: read",
        "jobs:",
    ]
    for job in plan.jobs:
        lines.extend(_job_lines(job))
    return "\n".join(lines) + "\n"


def iter_run_blocks(yaml_text: str) -> list[str]:
    """Return every `- run:` step body (unquoted), in document order.

    Increment 1 only emits single-line `run:` steps, so a per-line regex
    match is sufficient.
    """
    blocks = []
    for line in yaml_text.splitlines():
        match = _RUN_LINE_RE.match(line)
        if match:
            blocks.append(_UNESCAPE_RE.sub(lambda m: m.group(1), match.group(1)))
    return blocks
