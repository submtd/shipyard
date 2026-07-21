import json
import re
from pathlib import Path

import pytest

from ballast.config import Config, PytestConfig, load_config
from ballast.render import render

GOLDEN = Path(__file__).parent / "golden"

# Matches an INI section header line, e.g. "[pytest]". Used by the
# structural-safety test to prove render() never emits a second table no
# matter what a stack's PytestConfig contains.
_SECTION_HEADER_RE = re.compile(r"^\[.*\]$")


def write(tmp_path, data):
    (tmp_path / ".ballast.json").write_text(json.dumps(data))
    return tmp_path


def read_golden(name):
    return (GOLDEN / name).read_text()


def test_defaults_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    assert render(cfg) == read_golden("defaults.ini")


def test_monorepo_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "testPaths": [
                    "plugins/keel/tests",
                    "plugins/rigging/tests",
                    "plugins/stow/tests",
                    "plugins/ballast/tests",
                    "plugins/hull/tests",
                    "plugins/bosun/tests",
                    "tests",
                ],
                "pythonPath": [
                    "plugins/keel",
                    "plugins/rigging",
                    "plugins/stow",
                    "plugins/ballast",
                    "plugins/hull",
                    "plugins/bosun",
                ],
            }
        }
    }))
    assert render(cfg) == read_golden("monorepo.ini")


def test_monorepo_golden_matches_shipyards_committed_pytest_ini():
    # This is the byte-identity that Task 7's dogfood depends on: the
    # committed root pytest.ini must be exactly what render() produces for
    # the equivalent config. Pinned here so a golden-fixture drift is
    # caught in ballast's own suite, not discovered later in Task 7.
    root_pytest_ini = Path(__file__).parents[3] / "pytest.ini"
    assert read_golden("monorepo.ini") == root_pytest_ini.read_text()


def test_addopts_matches_golden_byte_for_byte(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "addOpts": ["-q", "--strict-markers"],
            }
        }
    }))
    assert render(cfg) == read_golden("addopts.ini")


def test_pythonpath_omitted_when_empty(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    out = render(cfg)
    assert "pythonpath" not in out


def test_pythonpath_present_when_set(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"pythonPath": ["plugins/keel"]}}
    }))
    out = render(cfg)
    assert "pythonpath =\n    plugins/keel\n" in out


@pytest.mark.parametrize("mode", ["importlib", "prepend", "append"])
def test_all_import_modes_render(tmp_path, mode):
    cfg = load_config(write(tmp_path, {
        "stacks": {"python": {"importMode": mode}}
    }))
    out = render(cfg)
    assert f"addopts = --import-mode={mode}\n" in out


def test_add_opts_tokens_appended_after_import_mode_flag(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "importMode": "prepend",
                "addOpts": ["-q", "--strict-markers", "--cov=x"],
            }
        }
    }))
    out = render(cfg)
    assert (
        "addopts = --import-mode=prepend -q --strict-markers --cov=x\n" in out
    )


def test_render_is_deterministic(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "testPaths": ["tests", "more/tests"],
                "pythonPath": ["src"],
                "addOpts": ["-q"],
            }
        }
    }))
    assert render(cfg) == render(cfg)


def test_construct_config_directly_without_a_config_file():
    cfg = Config(stacks={
        "python": PytestConfig(
            test_paths=("tests",),
            python_path=(),
            import_mode="importlib",
            add_opts=(),
        )
    })
    assert render(cfg) == read_golden("defaults.ini")


# --- structural safety -----------------------------------------------------
#
# render() must never emit more than the single leading [pytest] table, and
# every testpaths/pythonpath entry must land on its own line -- a value
# containing an embedded newline would otherwise let a malicious or buggy
# path smuggle a second section header (or a bogus key) into the file.


def _section_header_lines(text):
    return [line for line in text.splitlines() if _SECTION_HEADER_RE.match(line)]


@pytest.mark.parametrize("golden_name", ["defaults.ini", "monorepo.ini", "addopts.ini"])
def test_only_one_section_header_in_golden_outputs(golden_name):
    text = read_golden(golden_name)
    assert _section_header_lines(text) == ["[pytest]"]


def test_only_one_section_header_for_arbitrary_config(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "testPaths": ["tests", "more/tests", "plugins/x/tests"],
                "pythonPath": ["plugins/x", "plugins/y"],
                "importMode": "append",
                "addOpts": ["-q", "--strict-markers"],
            }
        }
    }))
    out = render(cfg)
    assert _section_header_lines(out) == ["[pytest]"]


def test_output_ends_with_exactly_one_trailing_newline(tmp_path):
    cfg = load_config(write(tmp_path, {"stacks": {"python": {}}}))
    out = render(cfg)
    assert out.endswith("\n")
    assert not out.endswith("\n\n")


def test_every_line_is_a_single_ini_token_no_embedded_newlines(tmp_path):
    cfg = load_config(write(tmp_path, {
        "stacks": {
            "python": {
                "testPaths": ["tests", "more/tests"],
                "pythonPath": ["src", "lib"],
                "addOpts": ["-q"],
            }
        }
    }))
    out = render(cfg)
    # splitlines() already guarantees this structurally (a "\n" inside any
    # rendered field would just split into more lines rather than smuggling
    # content mid-line), but assert explicitly that reconstructing via "\n"
    # round-trips, proving no stray line terminator variant (\r, \r\n) crept
    # in either.
    assert "\n".join(out.splitlines()) + "\n" == out


# --- the rendered file must actually work --------------------------------


def test_every_rendered_value_line_survives_shlex_split():
    """The property the charset rules exist to guarantee, asserted directly.

    pytest shlex-splits addopts/testpaths/pythonpath, so an unbalanced quote
    anywhere in the rendered file is fatal before collection. The golden and
    dogfood tests compare text and cannot see this; this one tokenizes the
    rendered output the same way pytest will.
    """
    import shlex

    cfg = Config(stacks={"python": PytestConfig(
        test_paths=("tests", "pkg/tests"),
        python_path=("src",),
        import_mode="importlib",
        add_opts=("-q", "--strict-markers", "--cov=src"),
    )})
    for line in render(cfg).splitlines():
        if not line.strip() or line.startswith("["):
            continue
        value = line.split("=", 1)[1] if "=" in line else line
        shlex.split(value)  # raises ValueError if a quote is unbalanced


def test_render_refuses_a_multi_stack_config_instead_of_dropping_stacks():
    """render() reads only the first stack. Today STACK_IDS == ("python",)
    so that's unreachable -- but config.py and scaffold.py are both written
    generically over STACK_IDS, so the day a second stack is registered this
    line becomes silent data loss in the one module nobody would think to
    change. Its docstring advertised the opposite ("a later increment that
    adds more stacks doesn't have to touch this line"). Fail loudly instead;
    it's free now and expensive later.
    """
    cfg = Config(stacks={
        "python": PytestConfig(("tests",), (), "importlib", ()),
        "node": PytestConfig(("spec",), (), "importlib", ()),
    })
    with pytest.raises(ValueError) as e:
        render(cfg)
    assert "one stack" in str(e.value)
