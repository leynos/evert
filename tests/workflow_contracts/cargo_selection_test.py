"""Exercise Cargo's discovered target configuration on the supported host."""

from __future__ import annotations

import os
import platform
import shlex
import subprocess
import tempfile
from pathlib import Path

import pytest

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TARGET_ROOT = REPOSITORY_ROOT / "target" / "cargo-selection-contract"
REQUIRED_RUSTFLAGS = {
    "-Zthreads=8",
    "-Clinker=evert-clang-mold",
    "-Clink-arg=-fuse-ld=mold",
}
LINUX_TARGET = "x86_64-unknown-linux-gnu"


def _is_supported_host() -> bool:
    """Return whether this runner must prove the GNU/Linux development route."""
    return platform.system() == "Linux" and platform.machine().lower() in {
        "x86_64",
        "amd64",
    }


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
        result = subprocess.run(
            [
                "make",
                "--no-print-directory",
                "--silent",
                "--eval",
                prefix_rule,
                prefix_target,
            ],
            cwd=REPOSITORY_ROOT,
            check=False,
            capture_output=True,
            text=True,
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
                f"the Make-selected linker wrapper is missing or not executable: {wrapper}"
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


def _evert_rustc_command(output: str) -> tuple[list[str], str]:
    """Extract the verbose rustc arguments for the root `evert` library."""
    for line in output.splitlines():
        marker = "Running `"
        if marker not in line or not line.rstrip().endswith("`"):
            continue
        rendered_command = line.split(marker, maxsplit=1)[1].rstrip()[:-1]
        try:
            command = shlex.split(rendered_command)
        except ValueError:
            continue
        for rustc_index, executable in enumerate(command):
            if Path(executable).name != "rustc":
                continue
            arguments = command[rustc_index + 1 :]
            for index, argument in enumerate(arguments[:-1]):
                if argument == "--crate-name" and arguments[index + 1] == "evert":
                    return arguments, line
    raise AssertionError("verbose Cargo output has no rustc command for crate `evert`")


@pytest.mark.parametrize(
    ("case_id", "target_args"),
    [
        pytest.param("bare", (), id="bare-cargo"),
        pytest.param(
            "explicit-target",
            ("--target", LINUX_TARGET),
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
            "the development target-table contract applies to native Linux x86_64"
        )

    tools_bin = _check_prerequisites()
    TARGET_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"{case_id}-", dir=TARGET_ROOT) as scratch:
        command = ["cargo", "check", "--locked", "--lib", "-vv", *target_args]
        try:
            result = subprocess.run(
                command,
                cwd=REPOSITORY_ROOT,
                env=_cargo_environment(Path(scratch), tools_bin),
                check=False,
                capture_output=True,
                text=True,
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
    try:
        rustc_arguments, rendered_command = _evert_rustc_command(output)
    except AssertionError as error:
        pytest.fail(f"{error}\nCargo output:\n{output[-12000:]}", pytrace=False)

    missing_flags = REQUIRED_RUSTFLAGS.difference(rustc_arguments)
    assert not missing_flags, (
        f"Cargo {case_id} rustc invocation omitted required target flags "
        f"{sorted(missing_flags)}:\n{rendered_command}"
    )
    assert not any(
        argument.startswith("-Zcodegen-backend=cranelift") for argument in rustc_arguments
    ), f"Cargo {case_id} selected the unsupported Cranelift backend:\n{rendered_command}"
