"""Exercise Cargo's discovered target configuration on the supported host."""

import os
import platform
import shlex
import tempfile
from itertools import pairwise
from pathlib import Path, PurePosixPath

import pytest
from command_runner import run_fixed_command

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = REPOSITORY_ROOT / "target" / "cargo-selection-contract"
REQUIRED_RUSTFLAGS = {
    "-Zthreads=8",
    "-Clinker=evert-clang-mold",
    "-Clink-arg=-fuse-ld=mold",
}
LINUX_TARGETS = {
    "amd64": "x86_64-unknown-linux-gnu",
    "arm64": "aarch64-unknown-linux-gnu",
    "aarch64": "aarch64-unknown-linux-gnu",
    "x86_64": "x86_64-unknown-linux-gnu",
}


def _native_linux_target() -> str | None:
    """Return the target triple covered by this Linux host, if supported."""
    if platform.system() != "Linux":
        return None
    return LINUX_TARGETS.get(platform.machine().lower())


def _is_supported_host() -> bool:
    """Return whether this runner must prove the GNU/Linux development route."""
    return _native_linux_target() is not None


def _prerequisite_failure(output: str) -> str:
    """Give a direct repair command when the pinned toolchain is unavailable."""
    detail = output.strip() or "the build-tools preflight produced no details"
    return (
        "The development build prerequisites are missing or invalid. "
        "Run `make install-build-tools` and retry.\n"
        f"`make check-build-tools` reported:\n{detail}"
    )


def _check_prerequisites() -> Path:
    """Return the linker bin directory selected by Make's successful preflight."""
    prefix_target = "print-cargo-selection-tools-prefix"
    prefix_rule = (
        f".PHONY: {prefix_target}\n"
        f"{prefix_target}: check-build-tools\n"
        "\t@printf '%s\\n' \"$$BUILD_TOOLS_PREFIX\"\n"
    )
    try:
        result = run_fixed_command(
            [
                "make",
                "--no-print-directory",
                "--silent",
                "--eval",
                prefix_rule,
                prefix_target,
            ],
            cwd=REPOSITORY_ROOT,
        )
    except OSError as error:
        pytest.fail(
            _prerequisite_failure(f"could not run `make check-build-tools`: {error}"),
            pytrace=False,
        )
    output = f"{result.stdout}{result.stderr}"
    if result.returncode != 0:
        pytest.fail(_prerequisite_failure(output), pytrace=False)

    prefix_lines = result.stdout.splitlines()
    if len(prefix_lines) != 1 or not prefix_lines[0]:
        pytest.fail(
            _prerequisite_failure(
                f"Make did not report one effective BUILD_TOOLS_PREFIX.\n{output}"
            ),
            pytrace=False,
        )

    tools_bin = Path(prefix_lines[0]) / "bin"
    wrapper = tools_bin / "evert-clang-mold"
    if not wrapper.is_file() or not os.access(wrapper, os.X_OK):
        pytest.fail(
            _prerequisite_failure(
                "the Make-selected linker wrapper is missing or not "
                f"executable: {wrapper}"
            ),
            pytrace=False,
        )
    return tools_bin


def _cargo_environment(target_dir: Path, tools_bin: Path) -> dict[str, str]:
    """Isolate Cargo defaults while retaining the user's shared package cache."""
    environment = os.environ.copy()
    for name in (
        "CARGO_BUILD_TARGET",
        "CARGO_ENCODED_RUSTFLAGS",
        "RUSTFLAGS",
        "RUSTUP_TOOLCHAIN",
        "RUSTC",
        "RUSTC_WRAPPER",
        "RUSTC_WORKSPACE_WRAPPER",
    ):
        environment.pop(name, None)
    # Make's PATH export is process-local. Reapply its validated prefix here;
    # this only locates the linker wrapper, while Cargo still discovers the
    # repository config and receives no injected flags.
    environment["PATH"] = os.pathsep.join(
        part for part in (str(tools_bin), environment.get("PATH", "")) if part
    )
    environment["CARGO_TARGET_DIR"] = str(target_dir)
    environment["CARGO_TERM_COLOR"] = "never"
    return environment


def _evert_rustc_command(output: str) -> tuple[list[str], str] | None:
    """Extract the verbose rustc arguments for the root `evert` library.

    Returns
    -------
    tuple[list[str], str] | None
        The rustc arguments and the rendered Cargo line, or ``None`` when the
        output holds no rustc invocation for `evert`.

    Examples
    --------
    >>> _evert_rustc_command("Running `rustc --crate-name evert`")[0]
    ['--crate-name', 'evert']
    """
    for line in output.splitlines():
        command = _cargo_running_tokens(line)
        if command is None:
            continue
        arguments = _evert_rustc_arguments(command)
        if arguments is not None:
            return arguments, line
    return None


def _cargo_running_tokens(line: str) -> list[str] | None:
    """Split a Cargo ``Running `...` `` line without starting a process.

    Returns
    -------
    list[str] | None
        Shell tokens, including an empty list for an empty command, or
        ``None`` when the line is malformed.

    Examples
    --------
    >>> _cargo_running_tokens('Running `rustc --crate-name evert`')
    ['rustc', '--crate-name', 'evert']
    >>> _cargo_running_tokens('ordinary Cargo output') is None
    True
    """
    marker = "Running `"
    if marker not in line or not line.rstrip().endswith("`"):
        return None
    rendered_command = line.split(marker, maxsplit=1)[1].rstrip()[:-1]
    try:
        return shlex.split(rendered_command)
    except ValueError:
        return None


def _evert_rustc_arguments(command: list[str]) -> list[str] | None:
    """Return the first rustc suffix containing adjacent Evert crate tokens.

    Returns
    -------
    list[str] | None
        The first matching rustc suffix, or ``None`` when no suffix matches.

    Examples
    --------
    >>> _evert_rustc_arguments(['rustc', '--crate-name', 'evert', '--emit', 'metadata'])
    ['--crate-name', 'evert', '--emit', 'metadata']
    >>> _evert_rustc_arguments(['rustc', '--crate-name=evert']) is None
    True
    """
    for rustc_index, executable in enumerate(command):
        if Path(executable).name != "rustc":
            continue
        arguments = command[rustc_index + 1 :]
        if any(
            first == "--crate-name" and second == "evert"
            for first, second in pairwise(arguments)
        ):
            return arguments
    return None


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        pytest.param("ordinary output", None, id="unrelated-line"),
        pytest.param("Running `rustc --crate-name evert", None, id="unclosed-backtick"),
        pytest.param('Running `rustc --crate-name "evert`', None, id="bad-shell-quote"),
        pytest.param("Running ``", [], id="empty-running-command"),
        pytest.param(
            "prefix Running `echo` Running `rustc --crate-name evert`",
            ["echo`", "Running", "`rustc", "--crate-name", "evert"],
            id="split-at-first-marker",
        ),
        pytest.param(
            'Running `"/opt/rust tool/bin/rustc" --crate-name evert '
            '--out-dir "target/debug build"`',
            [
                "/opt/rust tool/bin/rustc",
                "--crate-name",
                "evert",
                "--out-dir",
                "target/debug build",
            ],
            id="quoted-path-and-argument",
        ),
    ],
)
def test_cargo_running_tokens_preserves_shell_tokenization(
    line: str, expected: list[str] | None
) -> None:
    """The host-independent parser preserves Cargo's marker and shlex rules."""
    assert _cargo_running_tokens(line) == expected, line


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        pytest.param([], None, id="empty-command"),
        pytest.param(["rustc", "--emit", "metadata"], None, id="missing-crate-name"),
        pytest.param(["rustc", "--crate-name"], None, id="trailing-crate-option"),
        pytest.param(["rustc", "--crate-name", "dependency"], None, id="other-crate"),
        pytest.param(
            ["rustc", "--crate-name=evert"], None, id="equals-form-not-accepted"
        ),
        pytest.param(
            ["rustc", "--crate-name", "other", "flag", "evert"],
            None,
            id="non-adjacent-pair",
        ),
        pytest.param(
            ["rustc.exe", "--crate-name", "evert"], None, id="windows-executable"
        ),
        pytest.param(
            ["rustc", "--crate-name", "dependency", "--crate-name", "evert", "-v"],
            ["--crate-name", "dependency", "--crate-name", "evert", "-v"],
            id="later-crate-name-pair",
        ),
        pytest.param(
            ["rustc", "--help", "/tool/rustc", "--crate-name", "evert"],
            ["--help", "/tool/rustc", "--crate-name", "evert"],
            id="first-rustc-suffix-can-match-after-later-rustc",
        ),
    ],
)
def test_evert_rustc_arguments_matches_adjacent_crate_tokens(
    command: list[str], expected: list[str] | None
) -> None:
    """Only rustc suffixes with adjacent separate crate-name tokens match."""
    assert _evert_rustc_arguments(command) == expected, command


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        pytest.param("", None, id="empty-output"),
        pytest.param("unrelated Cargo output\n", None, id="no-running-line"),
        pytest.param(
            "Running `rustc --crate-name dependency --emit metadata`\n"
            f"Running `{PurePosixPath('/', 'usr', 'bin', 'rustc')} "
            "--crate-name evert --emit link`",
            (
                ["--crate-name", "evert", "--emit", "link"],
                (
                    f"Running `{PurePosixPath('/', 'usr', 'bin', 'rustc')} "
                    "--crate-name evert --emit link`"
                ),
            ),
            id="dependency-before-evert",
        ),
        pytest.param(
            "Running `env RUSTC_WRAPPER=cache sccache rustc --crate-name evert -v`",
            (
                ["--crate-name", "evert", "-v"],
                "Running `env RUSTC_WRAPPER=cache sccache rustc --crate-name evert -v`",
            ),
            id="environment-and-wrapper-prefix",
        ),
        pytest.param(
            " malformed\n  Running `rustc --crate-name evert`  \n"
            "Running `rustc --crate-name evert --later`",
            (
                ["--crate-name", "evert"],
                "  Running `rustc --crate-name evert`  ",
            ),
            id="malformed-before-first-match-and-original-line",
        ),
    ],
)
def test_evert_rustc_command_selects_first_parsed_match(
    output: str, expected: tuple[list[str], str] | None
) -> None:
    """Output scanning preserves exact arguments and the first original line."""
    assert _evert_rustc_command(output) == expected, output


@pytest.mark.parametrize(
    ("case_id", "target_args"),
    [
        pytest.param("bare", (), id="bare-cargo"),
        pytest.param(
            "explicit-target",
            ("--target", _native_linux_target() or "x86_64-unknown-linux-gnu"),
            id="explicit-linux-target",
        ),
    ],
)
def test_native_cargo_check_selects_the_linux_development_flags(
    case_id: str,
    target_args: tuple[str, ...],
) -> None:
    """Bare and explicit-target Cargo checks must pass all defaults to Evert."""
    if not _is_supported_host():
        pytest.skip(
            "the development target-table contract applies to native Linux "
            "x86_64 and aarch64"
        )

    tools_bin = _check_prerequisites()
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{case_id}-", dir=TARGET_ROOT) as scratch:
        command = ["cargo", "check", "--locked", "--lib", "-vv", *target_args]
        try:
            result = run_fixed_command(
                command,
                cwd=REPOSITORY_ROOT,
                environment=_cargo_environment(Path(scratch), tools_bin),
            )
        except OSError as error:
            pytest.fail(
                _prerequisite_failure(str(error)),
                pytrace=False,
            )

    output = f"{result.stdout}{result.stderr}"
    assert result.returncode == 0, (
        f"`{' '.join(command)}` failed from the repository root:\n{output[-12000:]}"
    )
    evert_command = _evert_rustc_command(output)
    if evert_command is None:
        pytest.fail(
            "verbose Cargo output has no rustc command for crate `evert`\n"
            f"Cargo output:\n{output[-12000:]}",
            pytrace=False,
        )
    rustc_arguments, rendered_command = evert_command

    missing_flags = REQUIRED_RUSTFLAGS.difference(rustc_arguments)
    assert not missing_flags, (
        f"Cargo {case_id} rustc invocation omitted required target flags "
        f"{sorted(missing_flags)}:\n{rendered_command}"
    )
    assert not any(
        argument.startswith("-Zcodegen-backend=cranelift")
        for argument in rustc_arguments
    ), (
        f"Cargo {case_id} selected the unsupported Cranelift backend:\n"
        f"{rendered_command}"
    )
