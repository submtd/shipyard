"""Pure helpers for ballast:init. No subprocess, no os -- the skill gathers
signals and does I/O; this module maps data to data and reads the
filesystem via pathlib only.

`propose_config`'s signal shape
--------------------------------
`signals["stacks"]` is a non-empty list/tuple of registry stack ids (from
`detect.detect_stacks`; increment 1: `["python"]`).

Optional `signals["configs"]` is a dict of stack id -> a dict of overrides,
using the same camelCase keys `.ballast.json` itself uses: `testPaths`,
`pythonPath`, `importMode`, `addOpts`. A stack absent from
`signals["configs"]` (or whose override dict omits a field) emits nothing
for that field, so `config.load_config` fills in the registry default when
it loads the file back.

Every field is validated against `config.py`'s own domains --
`stacks.STACK_IDS`, `config.IMPORT_MODES`, `config._valid_path` (which
wraps `config.PATH_RE` plus the leading-'/'/'..' structural rules), and
`config.FLAG_RE` -- imported and reused rather than re-implemented, so
scaffold and config can never drift apart on what counts as valid. Valid
signals in -> a dict guaranteed to load via `config.load_config` (enforced
by test). Invalid signals raise `ValueError` -- naming the bad field --
before anything is returned, so a caller can never persist a config that
ballast itself would reject.
"""
from __future__ import annotations

from pathlib import Path

from ballast import stacks
from ballast.config import FLAG_RE, IMPORT_MODES, _valid_path

#: Files ballast:init may write/detect, in the order it reports them.
CONFIG_FILES = [".ballast.json", "pytest.ini"]


def _valid_path_list(value, stack_id, field, *, allow_empty):
    if not isinstance(value, (list, tuple)) or (not allow_empty and not value):
        empty_note = "" if allow_empty else "non-empty "
        raise ValueError(
            f"signals['configs'][{stack_id!r}][{field!r}] must be a "
            f"{empty_note}list of relative path strings (got {value!r})."
        )
    paths = []
    for entry in value:
        if not _valid_path(entry):
            raise ValueError(
                f"signals['configs'][{stack_id!r}][{field!r}] entries must "
                f"be relative path strings with no whitespace, no leading "
                f"'/', and no '..' segment (got {entry!r})."
            )
        paths.append(entry)
    return paths


def _valid_flag_list(value, stack_id):
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"signals['configs'][{stack_id!r}]['addOpts'] must be a list "
            f"of flag tokens (got {value!r})."
        )
    opts = []
    for entry in value:
        if not isinstance(entry, str) or not FLAG_RE.fullmatch(entry):
            raise ValueError(
                f"signals['configs'][{stack_id!r}]['addOpts'] entries must "
                f"be non-empty tokens with no whitespace (got {entry!r})."
            )
        opts.append(entry)
    return opts


def propose_config(signals):
    """Map detected repository signals to a `.ballast.json` dict. See the
    module docstring for the shape of `signals`."""
    stack_ids = signals.get("stacks")
    if not isinstance(stack_ids, (tuple, list)) or not stack_ids:
        raise ValueError(
            f"signals['stacks'] must be a non-empty list/tuple of stack "
            f"ids (got {stack_ids!r})."
        )

    configs_by_id = signals.get("configs")
    if configs_by_id is None:
        configs_by_id = {}
    elif not isinstance(configs_by_id, dict):
        raise ValueError(
            f"signals['configs'] must be a dict of stack id -> override "
            f"dict (got {configs_by_id!r})."
        )

    stacks_out = {}
    for stack_id in stack_ids:
        if stack_id not in stacks.STACK_IDS:
            raise ValueError(
                f"signals['stacks'] contains unknown stack id {stack_id!r}. "
                f"Allowed ids: {', '.join(stacks.STACK_IDS)}."
            )

        overrides = configs_by_id.get(stack_id)
        if overrides is None:
            stacks_out[stack_id] = {}
            continue
        if not isinstance(overrides, dict):
            raise ValueError(
                f"signals['configs'][{stack_id!r}] must be a dict (got "
                f"{overrides!r})."
            )

        stack_config = {}

        test_paths = overrides.get("testPaths")
        if test_paths is not None:
            stack_config["testPaths"] = _valid_path_list(
                test_paths, stack_id, "testPaths", allow_empty=False
            )

        python_path = overrides.get("pythonPath")
        if python_path is not None:
            stack_config["pythonPath"] = _valid_path_list(
                python_path, stack_id, "pythonPath", allow_empty=True
            )

        import_mode = overrides.get("importMode")
        if import_mode is not None:
            if import_mode not in IMPORT_MODES:
                raise ValueError(
                    f"signals['configs'][{stack_id!r}]['importMode'] must "
                    f"be one of {IMPORT_MODES} (got {import_mode!r})."
                )
            stack_config["importMode"] = import_mode

        add_opts = overrides.get("addOpts")
        if add_opts is not None:
            stack_config["addOpts"] = _valid_flag_list(add_opts, stack_id)

        stacks_out[stack_id] = stack_config

    return {"stacks": stacks_out}


def classify_files(root, candidates):
    """Classify each candidate (a repo-relative path string) as present/absent."""
    root = Path(root)
    return {
        name: ("present" if (root / name).exists() else "absent")
        for name in candidates
    }
