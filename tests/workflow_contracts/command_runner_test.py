"""Hold the properties that make the process helper safe to exempt from lints.

The helper is exempt from Ruff's subprocess rules because it never uses a
shell, never rewrites its arguments, and resolves the executable itself. These
tests fail if a change gives up any of those properties.
"""

import stat
import sys
from pathlib import Path

import pytest
from command_runner import run_fixed_command

REPOSITORY = Path(__file__).resolve().parents[2]
FAILING_STATUS = 3


def test_captures_output_and_status() -> None:
    """A finished command reports its status and decoded streams."""
    program = "import sys; print('out'); print('err', file=sys.stderr)"
    result = run_fixed_command([sys.executable, "-c", program], cwd=REPOSITORY)
    assert (result.returncode, result.stdout, result.stderr) == (
        0,
        "out\n",
        "err\n",
    ), f"unexpected result {result}"


def test_returns_a_failing_status_without_raising() -> None:
    """Callers judge the exit status themselves."""
    result = run_fixed_command(
        [sys.executable, "-c", f"raise SystemExit({FAILING_STATUS})"], cwd=REPOSITORY
    )
    assert result.returncode == FAILING_STATUS, f"unexpected result {result}"


def test_arguments_reach_the_child_without_shell_interpretation() -> None:
    """Shell metacharacters stay literal, so nothing can be injected."""
    hostile = "value; echo injected && true | cat"
    result = run_fixed_command(
        [sys.executable, "-c", "import sys; print(sys.argv[1])", hostile],
        cwd=REPOSITORY,
    )
    assert result.stdout == f"{hostile}\n", f"argument was altered: {result.stdout!r}"


def test_runs_in_the_requested_directory(tmp_path: Path) -> None:
    """The working directory is the one the caller asked for."""
    result = run_fixed_command(
        [sys.executable, "-c", "import os; print(os.getcwd())"], cwd=tmp_path
    )
    assert Path(result.stdout.strip()).resolve() == tmp_path.resolve(), (
        f"ran in {result.stdout!r}"
    )


def test_resolves_the_executable_on_the_childs_path(tmp_path: Path) -> None:
    """A tool directory prepended to the child's PATH takes effect."""
    tool = tmp_path / "pinned-tool"
    tool.write_text("#!/bin/sh\necho pinned\n", encoding="utf-8")
    tool.chmod(stat.S_IRWXU)
    result = run_fixed_command(
        ["pinned-tool"], cwd=tmp_path, environment={"PATH": str(tmp_path)}
    )
    assert result.stdout == "pinned\n", f"tool was not found: {result}"


def test_a_missing_executable_raises_file_not_found() -> None:
    """An absent tool surfaces as the OSError subclass callers already catch."""
    with pytest.raises(FileNotFoundError, match="no-such-tool"):
        run_fixed_command(
            ["no-such-tool"], cwd=REPOSITORY, environment={"PATH": "/nonexistent"}
        )
