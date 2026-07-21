"""Render a ballast Config to deterministic pytest.ini text.

Pure module: no subprocess, no os, no networking -- stdlib only.
"""
from __future__ import annotations

from ballast.config import Config


def render(config: Config) -> str:
    """Render `config` to deterministic pytest.ini text.

    Same config in -> byte-identical text out, every call.

    Increment 1 has exactly one stack (python); its `PytestConfig` is
    rendered into the single `[pytest]` table. (Grabbing the first --
    and only -- value keeps this from hard-coding the stack id, so a
    later increment that adds more stacks doesn't have to touch this
    line just to keep inc-1's single-stack behavior working.)
    """
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
