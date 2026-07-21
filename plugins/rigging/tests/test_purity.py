"""Enforces the engine-purity invariant via AST, so it survives contributors
rather than being verified only out-of-band (by review, by memory, etc.).

Two things are pinned down:

1. The pure rule-engine modules (config, stacks, detect, plan, render,
   scaffold) must never import subprocess, os, or any networking module.
   All I/O lives outside these modules -- they take facts already gathered
   and decide; they must not be able to gather anything themselves.
2. Every subprocess.run(...) call anywhere in the plugin package passes a
   `timeout=` keyword argument, so a hung git/gh process can never hang the
   (advisory, time-boxed) hook indefinitely.
"""
import ast
from pathlib import Path

import pytest

PLUGIN_ROOT = Path(__file__).resolve().parents[1]
RIGGING_PKG = PLUGIN_ROOT / "rigging"
HOOKS_DIR = PLUGIN_ROOT / "hooks"

#: Modules that are ALLOWED to do I/O. Everything in the package
#: must be in exactly one of these two lists -- see the coverage
#: test at the bottom of this file.
IO_MODULES = ()

PURE_MODULES = ("config", "stacks", "detect", "plan", "render", "scaffold")

FORBIDDEN_IN_PURE_MODULES = {
    "subprocess", "os",
    "socket", "http", "urllib", "requests", "ftplib", "smtplib", "telnetlib",
}


def _module_path(name):
    return RIGGING_PKG / f"{name}.py"


def _imported_top_level_names(tree):
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module.split(".")[0])
    return names


@pytest.mark.parametrize("module_name", PURE_MODULES)
def test_pure_module_imports_no_subprocess_or_network(module_name):
    path = _module_path(module_name)
    tree = ast.parse(path.read_text(), filename=str(path))
    imported = _imported_top_level_names(tree)
    offenders = imported & FORBIDDEN_IN_PURE_MODULES
    assert not offenders, (
        f"{path} imports {offenders}, but engine-purity requires all I/O "
        f"to live outside the pure engine modules."
    )


def _all_source_files():
    files = list(RIGGING_PKG.glob("*.py"))
    files += list(HOOKS_DIR.glob("*.py"))
    return files


def _subprocess_run_calls(tree):
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            is_subprocess_run = (
                isinstance(func, ast.Attribute)
                and func.attr == "run"
                and isinstance(func.value, ast.Name)
                and func.value.id == "subprocess"
            )
            if is_subprocess_run:
                calls.append(node)
    return calls


@pytest.mark.parametrize("path", _all_source_files(), ids=lambda p: p.name)
def test_every_subprocess_run_call_passes_timeout(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    calls = _subprocess_run_calls(tree)
    for call in calls:
        kw_names = {kw.arg for kw in call.keywords if kw.arg is not None}
        has_timeout = "timeout" in kw_names or any(
            kw.arg is None for kw in call.keywords  # **kwargs passthrough
        )
        assert has_timeout, (
            f"{path}:{call.lineno}: subprocess.run(...) call has no "
            f"timeout= argument."
        )


def test_pure_modules_list_covers_every_module_in_the_package():
    """PURE_MODULES is hand-maintained, so a new module was guarded by
    nobody: adding `<pkg>/foo.py` with `import subprocess` passed purity
    silently. Anything not on the explicit I/O allowlist must be listed.
    """
    on_disk = {p.stem for p in RIGGING_PKG.glob("*.py")} - {"__init__"}
    covered = set(PURE_MODULES) | set(IO_MODULES)
    missing = sorted(on_disk - covered)
    assert not missing, (
        f"new module(s) {missing} are neither in PURE_MODULES nor declared "
        f"as I/O modules in IO_MODULES -- add them to one"
    )
