"""Start the fixed toolchain commands that some contracts must run for real.

A few contracts can only be proved by executing the repository's own tools,
such as the Make installer or the `cargo check` flag selection. This module is
the single place the contract tests start a process, so the one deliberate
exemption from Ruff's subprocess rules (`suspicious-subprocess-import` and
`subprocess-without-shell-equals-true`) is configured in `pyproject.toml`
against this file alone, rather than spread across the test modules.

The exemption is safe because the helper only runs a fixed argument list. It
never uses a shell, and it resolves the executable to an absolute path before
running it. Callers must pass literal commands, never workflow or user input.
"""

import os
import shutil
import subprocess
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc
    from pathlib import Path


class CommandResult(typ.NamedTuple):
    """Exit status and decoded output streams of a finished command."""

    returncode: int
    stdout: str
    stderr: str


def run_fixed_command(
    command: cabc.Sequence[str],
    *,
    cwd: Path,
    environment: cabc.Mapping[str, str] | None = None,
) -> CommandResult:
    """Run a literal command without a shell and capture its output.

    The executable is looked up on the ``PATH`` the child will see, so a test
    that prepends a pinned tool directory to ``environment`` finds that tool,
    exactly as the child's own lookup would.

    Parameters
    ----------
    command
        The executable followed by its arguments; passed to the process as
        given, never interpreted by a shell.
    cwd
        The directory to run the command in.
    environment
        The child's environment; the current environment when omitted.

    Returns
    -------
    CommandResult
        The exit status and the decoded standard output and error. A non-zero
        status is returned, not raised.

    Raises
    ------
    FileNotFoundError
        If the executable cannot be found on the child's ``PATH``.

    Examples
    --------
    >>> import sys
    >>> from pathlib import Path
    >>> result = run_fixed_command(
    ...     [sys.executable, "-c", "print('ok')"], cwd=Path.cwd()
    ... )
    >>> result.stdout.strip()
    'ok'
    """
    search_path = (environment if environment is not None else os.environ).get("PATH")
    executable = shutil.which(command[0], path=search_path)
    if executable is None:
        message = f"cannot find `{command[0]}` on PATH"
        raise FileNotFoundError(message)
    completed = subprocess.run(
        [executable, *command[1:]],
        cwd=cwd,
        env=None if environment is None else dict(environment),
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return CommandResult(completed.returncode, completed.stdout, completed.stderr)
