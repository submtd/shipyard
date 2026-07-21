"""Render a ballast Config to deterministic pytest.ini text.

Pure module: no subprocess, no os, no networking -- stdlib only.
"""
from __future__ import annotations

from ballast.config import Config


def render(config: Config) -> str:
    """Render `config` to deterministic pytest.ini text.

    Same config in -> byte-identical text out, every call.

    Increment 1 has exactly one stack (python); its `PytestConfig` is
    rendered into the single `[pytest]` table. Grabbing the first value
    keeps this from hard-coding the stack id -- but a pytest.ini has only
    one `[pytest]` table, so a second stack has nowhere to go. Raise
    rather than render the first and silently discard the rest: config.py
    and scaffold.py are both generic over STACK_IDS, so registering a
    second stack would otherwise turn this line into silent data loss in
    the one module nobody would think to revisit.
    """
    if len(config.stacks) != 1:
        raise ValueError(
            f"render() supports exactly one stack per pytest.ini "
            f"(got {len(config.stacks)}: "
            f"{', '.join(sorted(config.stacks)) or 'none'})."
        )
    pytest_config = next(iter(config.stacks.values()))

    addopts_tokens = (f"--import-mode={pytest_config.import_mode}",) + pytest_config.add_opts
    lines = [
        "[pytest]",
        f"addopts = {' '.join(addopts_tokens)}",
        "testpaths =",
    ]
    for path in pytest_config.test_paths:
        lines.append(f"    {path}")

    if pytest_config.python_path:
        lines.append("pythonpath =")
        for path in pytest_config.python_path:
            lines.append(f"    {path}")

    return "\n".join(lines) + "\n"
