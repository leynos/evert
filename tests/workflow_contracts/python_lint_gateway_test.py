"""Contract tests that hold the Python lint gateway's three parts together.

The gateway is configured in three places: the ``Makefile`` pins each tool and
names the source roots, ``pyproject.toml`` carries the rule configuration, and
the Python files in the repository must all sit under those roots. If any one
drifts, a Python file can escape the lints without a failing check.
"""

import re
import tomllib
from pathlib import Path

import pytest
from workflow_contract_support import fresh_documents, steps

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPOSITORY_ROOT / "Makefile"
PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"

# Ruff skips these directories by default. The repository adds its uv caches
# and Cargo output through `extend-exclude` in pyproject.toml, which this
# module reads instead of copying so the two cannot disagree.
DEFAULT_EXCLUDES = frozenset({".git", ".venv", "venv", "node_modules", "__pycache__"})

GATEWAY_COMMANDS = ("RUFF", "PYLINT", "DF12_PYLINT", "AMBRLEAKS", "INTERROGATE")
PINNED_TOOLS = (
    "RUFF_VERSION",
    "PYLINT_VERSION",
    "INTERROGATE_VERSION",
    "TY_VERSION",
)


def _makefile_lines() -> list[str]:
    """Return the Makefile source, one entry per physical line."""
    return MAKEFILE.read_text(encoding="utf-8").splitlines()


def _makefile_variable(name: str) -> str:
    """Return the value assigned to a Makefile variable.

    Parameters
    ----------
    name
        The variable to look up, for example ``PYTHON_BASELINE``.

    Returns
    -------
    str
        The assigned value with surrounding whitespace removed.
    """
    assignment = re.compile(rf"{re.escape(name)}\s*[:?]?=\s*(?P<value>.+?)\s*")
    for line in _makefile_lines():
        match = assignment.fullmatch(line)
        if match is not None:
            return match["value"]
    return pytest.fail(f"Makefile does not assign {name}", pytrace=False)


def _recipe(target: str) -> str:
    """Return the tab-indented recipe lines that follow a Makefile target.

    Parameters
    ----------
    target
        The target whose recipe to return, for example ``lint-python``.

    Returns
    -------
    str
        The recipe lines joined by newlines.
    """
    lines = _makefile_lines()
    start = next(
        (index for index, line in enumerate(lines) if line.startswith(f"{target}:")),
        None,
    )
    if start is None:
        return pytest.fail(f"Makefile does not define {target}", pytrace=False)
    recipe: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() and not line.startswith("\t"):
            break
        recipe.append(line)
    return "\n".join(recipe)


def _pyproject_setting(*path: str) -> object:
    """Return a nested ``pyproject.toml`` value, failing when it is absent.

    Parameters
    ----------
    *path
        The table and key names leading to the value.

    Returns
    -------
    object
        The configured value.
    """
    value: object = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    for key in path:
        if not isinstance(value, dict) or key not in value:
            pytest.fail(f"pyproject.toml is missing [{'.'.join(path)}]", pytrace=False)
        value = value[key]
    return value


def _excluded_names() -> frozenset[str]:
    """Return the directory names no Python linter walks."""
    configured = _pyproject_setting("tool", "ruff", "extend-exclude")
    if not isinstance(configured, list):
        pytest.fail("tool.ruff.extend-exclude must be a list", pytrace=False)
    return DEFAULT_EXCLUDES | frozenset(str(name) for name in configured)


def _python_files() -> list[Path]:
    """Return every Python file the linters should see, relative to the root."""
    excluded = _excluded_names()
    found: list[Path] = []
    for directory, subdirectories, files in REPOSITORY_ROOT.walk():
        subdirectories[:] = [name for name in subdirectories if name not in excluded]
        found.extend(
            (directory / name).relative_to(REPOSITORY_ROOT)
            for name in files
            if name.endswith(".py")
        )
    return sorted(found)


def test_python_baseline_agrees_across_gateway_files() -> None:
    """The Makefile baseline must equal Ruff's target and Pylint's version."""
    baseline = _makefile_variable("PYTHON_BASELINE")
    major, minor = baseline.split(".")
    ruff_target = _pyproject_setting("tool", "ruff", "target-version")
    pylint_version = _pyproject_setting("tool", "pylint", "main", "py-version")
    assert ruff_target == f"py{major}{minor}", (
        f"Makefile PYTHON_BASELINE {baseline} disagrees with "
        f"tool.ruff.target-version {ruff_target!r}"
    )
    assert pylint_version == baseline, (
        f"Makefile PYTHON_BASELINE {baseline} disagrees with "
        f"tool.pylint.main.py-version {pylint_version!r}"
    )


def test_every_python_file_sits_under_a_lint_root() -> None:
    """Python outside the Makefile's source roots would escape every linter."""
    roots = _makefile_variable("PYTHON_SOURCE_ROOTS").split()
    escaped = [
        str(path)
        for path in _python_files()
        if not any(path.is_relative_to(root) for root in roots)
    ]
    assert not escaped, (
        "Python files outside PYTHON_SOURCE_ROOTS escape the lint gateway: "
        + ", ".join(escaped)
    )


def test_lint_depends_on_the_python_gateway() -> None:
    """`make lint`, which CI runs, must reach the Python linters."""
    declaration = next(
        (line for line in _makefile_lines() if line.startswith("lint:")),
        None,
    )
    assert declaration is not None, "Makefile does not define lint"
    prerequisites = declaration.removeprefix("lint:").split("##", 1)[0].split()
    assert "lint-python" in prerequisites, (
        f"lint must depend on lint-python, found {prerequisites}"
    )


@pytest.mark.parametrize("command", GATEWAY_COMMANDS)
def test_lint_python_recipe_runs_every_gateway_tool(command: str) -> None:
    """Each tool in the gateway must be invoked by the `lint-python` recipe."""
    assert f"$({command})" in _recipe("lint-python"), (
        f"lint-python must run $({command})"
    )


@pytest.mark.parametrize("variable", PINNED_TOOLS)
def test_gateway_tool_versions_are_exact(variable: str) -> None:
    """A floating tool version lets rule sets drift between runs."""
    value = _makefile_variable(variable)
    assert re.fullmatch(r"\d+\.\d+\.\d+", value), (
        f"{variable} must pin one exact release, found {value!r}"
    )


def test_df12_lints_are_pinned_to_a_commit() -> None:
    """The df12 house lints must come from a commit, never a tag or branch.

    A commit resolves from uv's cache without the network, so the gate keeps
    working offline, and nothing that moves a tag can change what runs.
    """
    reference = _makefile_variable("DF12_PYTHON_LINTS_REF")
    assert re.fullmatch(r"[0-9a-f]{40}", reference), (
        f"DF12_PYTHON_LINTS_REF must be a full commit hash, found {reference!r}"
    )


@pytest.mark.parametrize("prerequisite", ["typecheck-python", "typecheck-rust"])
def test_typecheck_reaches_both_type_checks(prerequisite: str) -> None:
    """`make typecheck`, which CI runs, must run the Python and Rust checks."""
    declaration = next(
        (line for line in _makefile_lines() if line.startswith("typecheck:")),
        None,
    )
    assert declaration is not None, "Makefile does not define typecheck"
    prerequisites = declaration.removeprefix("typecheck:").split("##", 1)[0].split()
    assert prerequisite in prerequisites, (
        f"typecheck must depend on {prerequisite}, found {prerequisites}"
    )


@pytest.mark.parametrize(
    "fragment",
    [
        pytest.param("ty check", id="runs-ty"),
        pytest.param("--from ty==$(TY_VERSION)", id="pinned-ty"),
        pytest.param("--python $(PYTHON_BASELINE)", id="interpreter-baseline"),
        pytest.param("--python-version $(PYTHON_BASELINE)", id="language-baseline"),
        pytest.param("$(PYTHON_SOURCES)", id="same-roots-as-the-linters"),
    ],
)
def test_typecheck_python_recipe_holds_its_contract(fragment: str) -> None:
    """The `typecheck-python` recipe must keep the baseline, pin, and roots."""
    assert fragment in _recipe("typecheck-python"), (
        f"typecheck-python must contain `{fragment}`"
    )


def test_ci_runs_the_typecheck_gate() -> None:
    """A pull request must not merge without the Python and Rust type checks."""
    commands = [
        run
        for step in steps("ci.yml", fresh_documents()["ci.yml"])
        if isinstance(run := step.get("run"), str)
    ]
    assert "make typecheck" in commands, "ci.yml must run `make typecheck`"
