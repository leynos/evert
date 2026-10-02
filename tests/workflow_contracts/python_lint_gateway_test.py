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
from workflow_contract_support import fresh_documents, jobs, steps

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
MAKEFILE = REPOSITORY_ROOT / "Makefile"
PYPROJECT = REPOSITORY_ROOT / "pyproject.toml"

# Ruff skips these directories by default. The repository adds its uv caches
# and Cargo output through `extend-exclude` in pyproject.toml, which this
# module reads instead of copying so the two cannot disagree.
DEFAULT_EXCLUDES = frozenset(
    {
        ".git",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        "vendor",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
    }
)

GATEWAY_COMMANDS = ("RUFF", "PYLINT", "AMBRLEAKS", "INTERROGATE")
PINNED_TOOLS = (
    "RUFF_VERSION",
    "PYLINT_VERSION",
    "PYTEST_VERSION",
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
    continued = ""
    for physical_line in _makefile_lines():
        line = continued + physical_line.lstrip()
        if line.endswith("\\"):
            continued = line[:-1] + " "
            continue
        continued = ""
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
    assert baseline == "3.14", (
        f"Python lint baseline must be CPython 3.14, found {baseline}"
    )
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
    required_roots = {".github", "tests", "scripts", "benches", "benchmarks"}
    assert required_roots <= set(roots), (
        "PYTHON_SOURCE_ROOTS must cover workflows/actions, tests, scripts, and "
        f"benchmarks; missing {sorted(required_roots - set(roots))}"
    )
    escaped = [
        str(path)
        for path in _python_files()
        if not any(path.is_relative_to(root) for root in roots)
    ]
    assert not escaped, (
        "Python files outside PYTHON_SOURCE_ROOTS escape the lint gateway: "
        + ", ".join(escaped)
    )


@pytest.mark.parametrize(
    ("target", "prerequisite"),
    [
        pytest.param("all", "typecheck", id="all-requires-typecheck"),
        pytest.param("lint", "lint-python", id="lint-requires-lint-python"),
        pytest.param(
            "typecheck",
            "typecheck-python",
            id="typecheck-requires-python-check",
        ),
        pytest.param(
            "typecheck",
            "typecheck-rust",
            id="typecheck-requires-rust-check",
        ),
    ],
)
def test_make_target_requires_gateway_prerequisite(
    target: str, prerequisite: str
) -> None:
    """Each aggregate Make target must retain its gateway prerequisite."""
    declaration = next(
        (line for line in _makefile_lines() if line.startswith(f"{target}:")),
        None,
    )
    assert declaration is not None, f"Makefile does not define {target}"
    prerequisites = (
        declaration.removeprefix(f"{target}:").split("##", 1)[0].split()
    )
    assert prerequisite in prerequisites, (
        f"{target} must depend on {prerequisite}, found {prerequisites}"
    )


@pytest.mark.parametrize("command", GATEWAY_COMMANDS)
def test_lint_python_recipe_runs_every_gateway_tool(command: str) -> None:
    """Each tool in the gateway must be invoked by the `lint-python` recipe."""
    assert f"$({command})" in _recipe("lint-python"), (
        f"lint-python must run $({command})"
    )


def test_pylint_keeps_defaults_and_adds_df12_messages() -> None:
    """The house plugin augments Pylint defaults instead of replacing them."""
    recipe = _makefile_variable("PYLINT")
    messages = _makefile_variable("DF12_PYLINT_MESSAGES")
    pylint_config = _pyproject_setting("tool", "pylint", "messages control")
    assert isinstance(pylint_config, dict), "Pylint message settings must be a mapping"
    assert "disable" not in pylint_config, (
        "Pylint defaults must remain active; do not configure a disable list"
    )
    pylint_command = re.search(
        r"(?!.*--disable=all).*pylint.*--load-plugins=df12_python_lints"
        r".*--enable=\$\(DF12_PYLINT_MESSAGES\)",
        recipe,
        re.DOTALL,
    )
    assert pylint_command is not None, (
        "Pylint must retain its defaults, load df12, and enable its messages"
    )
    expected_messages = {
        "R9101",
        "C9102",
        "R9103",
        "R9104",
        "C9105",
        "C9106",
        "C9107",
        "R9108",
        "R9109",
        "R9110",
        "R9111",
        "R9112",
        "C9112",
    }
    assert set(messages.split(",")) == expected_messages, (
        f"DF12 message configuration must be {sorted(expected_messages)}, "
        f"found {messages!r}"
    )
    assert "--managed-python --python $(PYTHON_BASELINE)" in recipe, (
        "Pylint must run with the managed baseline interpreter"
    )


@pytest.mark.parametrize("workflow", ["ci.yml", "audit.yml"])
def test_workflow_python_interpreter_matches_the_gateway(workflow: str) -> None:
    """Workflow-owned Python steps must use the gateway's CPython baseline."""
    document = fresh_documents()[workflow]
    workflow_jobs = jobs(workflow, document)
    assert workflow_jobs, f"{workflow} must define at least one job"
    baseline = _makefile_variable("PYTHON_BASELINE")
    setup_python: dict[str, object] | None = None
    for step in steps(workflow, document):
        uses = step.get("uses")
        if isinstance(uses, str) and uses.startswith("actions/setup-python@"):
            setup_python = step
            break
    assert setup_python is not None, f"{workflow} must set up Python explicitly"
    with_args = setup_python.get("with")
    assert isinstance(with_args, dict), f"{workflow} Python setup needs inputs"
    assert with_args.get("python-version") == baseline, (
        f"{workflow} setup-python must use Makefile baseline {baseline}"
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
