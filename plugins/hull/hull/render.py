"""Render a ScanPlan to deterministic GitHub Actions YAML.

Pure module: no subprocess, no os, no networking. Hand-rolled emitter (no
`yaml` dependency) so we control quoting exactly -- ported from rigging's
render.py (`_quote` and `iter_run_blocks` are unchanged; see that module's
docstring for the full version-string/`name:` quoting rationale). Every
scalar VALUE we emit is double-quoted, which is what keeps a fetch-depth
like "0" from ever being read back by a YAML loader as anything but a
string, and the workflow's own `name:` from ever being read back as an
int/bool/null or (e.g. a bare "-") failing to parse at all. Structural keys
(job ids, `uses`/`with`/`env` etc.) are left bare.

There are no `run` steps in this increment -- every step in a hull plan is
either a `uses:` action, optionally followed by `with:` and/or `env:`
blocks (see hull.plan/hull.scanners). `iter_run_blocks` is still ported in
full so it's ready the day a scanner does add one, and so test_injection.py
can scan for it structurally rather than by convention. Per the
injection-safety invariant enforced elsewhere (scanners.py's registry test
and test_injection.py), a `run` body must never contain `${{`.
"""
from __future__ import annotations

import re

from hull.plan import Job, ScanPlan
from hull.scanners import Step

# Matches a single-line `- run: "<body>"` step as emitted by `render`.
_RUN_LINE_RE = re.compile(r'^\s*- run: "(.*)"\s*$')

# Matches the opening marker of a block-scalar `- run: |` step as emitted by
# `render`. Captures the marker's own leading whitespace so the body's
# indentation (always deeper) can be detected relative to it.
_RUN_BLOCK_MARKER_RE = re.compile(r'^(\s*)- run: \|\s*$')

# Reverses the escaping `_quote` applies: a backslash followed by any
# character is that character, unescaped.
_UNESCAPE_RE = re.compile(r'\\(.)')

# Body lines of a block-scalar `run:` are indented 4 spaces beyond the
# `- run: |` marker line's own indentation.
_RUN_BLOCK_BODY_EXTRA_INDENT = 4


def _quote(value: str) -> str:
    """Render `value` as a double-quoted YAML scalar, escaping ``\\`` and ``"``."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _step_lines(step: Step) -> list[str]:
    if step.run is not None:
        if "\n" in step.run:
            marker_indent = " " * 6
            body_indent = " " * (6 + _RUN_BLOCK_BODY_EXTRA_INDENT)
            lines = [f"{marker_indent}- run: |"]
            for script_line in step.run.split("\n"):
                lines.append(f"{body_indent}{script_line}")
            return lines
        return [f"      - run: {_quote(step.run)}"]

    lines = []
    if step.name:
        lines.append(f"      - name: {_quote(step.name)}")
        lines.append(f"        uses: {_quote(step.uses)}")
    else:
        uses_line = f"      - uses: {_quote(step.uses)}"
        if step.uses_version:
            uses_line += f"  # {step.uses_version}"
        lines.append(uses_line)
    if step.name and step.uses_version:
        lines[-1] += f"  # {step.uses_version}"
    if step.with_:
        lines.append("        with:")
        for key, value in step.with_.items():
            lines.append(f"          {key}: {_quote(value)}")
    if step.env:
        lines.append("        env:")
        for key, value in step.env.items():
            lines.append(f"          {key}: {_quote(value)}")
    return lines


def _job_lines(job: Job) -> list[str]:
    lines = [
        f"  {job.id}:",
        f"    runs-on: {_quote(job.runs_on)}",
        "    steps:",
    ]
    for step in job.steps:
        lines.extend(_step_lines(step))
    return lines


def render(plan: ScanPlan) -> str:
    """Render `plan` to deterministic GitHub Actions workflow YAML.

    Same plan in -> byte-identical text out, every call.
    """
    branches = ", ".join(_quote(branch) for branch in plan.push_branches)
    lines = [
        f"name: {_quote(plan.name)}",
        "on:",
        "  push:",
        f"    branches: [{branches}]",
        "  pull_request:",
        "permissions:",
        *(f"  {scope}" for scope in plan.permissions),
        "jobs:",
    ]
    for job in plan.jobs:
        lines.extend(_job_lines(job))
    return "\n".join(lines) + "\n"


def iter_run_blocks(yaml_text: str) -> list[str]:
    """Return every `- run:` step body, in document order.

    `render` emits two forms and this extracts both:

    - single-line `- run: "<body>"` -- the quoting `_quote` applied is
      reversed and the unquoted body is returned.
    - block-scalar `- run: |` followed by indented lines -- every
      contiguous line indented at least as deeply as the first body line is
      collected, dedented by that indentation, and returned as one
      newline-joined string (so injection scanning sees the whole run body,
      not just its first line).

    A block ends at the first line that is blank or indented less than the
    body's own indentation.
    """
    blocks: list[str] = []
    lines = yaml_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        single = _RUN_LINE_RE.match(line)
        if single:
            blocks.append(_UNESCAPE_RE.sub(lambda m: m.group(1), single.group(1)))
            i += 1
            continue

        block_marker = _RUN_BLOCK_MARKER_RE.match(line)
        if block_marker:
            marker_indent = len(block_marker.group(1))
            body_indent = None
            body_lines: list[str] = []
            i += 1
            while i < len(lines):
                candidate = lines[i]
                if not candidate.strip():
                    break
                candidate_indent = len(candidate) - len(candidate.lstrip(" "))
                if candidate_indent <= marker_indent:
                    break
                if body_indent is None:
                    body_indent = candidate_indent
                if candidate_indent < body_indent:
                    break
                body_lines.append(candidate[body_indent:])
                i += 1
            blocks.append("\n".join(body_lines))
            continue

        i += 1
    return blocks
