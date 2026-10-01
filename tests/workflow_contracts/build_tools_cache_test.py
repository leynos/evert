"""Exercise setup-rust's linker cache through the real Make installer route."""

import os
import re
import shutil
import sys
from pathlib import Path

from command_runner import CommandResult, run_fixed_command

REPOSITORY = Path(__file__).resolve().parents[2]
SHA256_HEX_DIGITS = 64
DIGEST_AND_NAME_FIELDS = 2
EXECUTABLE_MODE = 0o755
DEFAULT_PATH = "/usr/bin:/bin"
PINNED_NIGHTLY = "nightly-2026-05-28"
PROBE_ARGUMENTS = [
    "BUILD_HOST_OS=Darwin",
    "BUILD_HOST_ARCH=x86_64",
    "CARGO=probe-cargo",
    "MDTABLEFIX=probe-mdtablefix",
]
LINKER_MISSING_MESSAGE = (
    "setup-rust must put its verified Linux linker on PATH before Make runs"
)
PYTHON_SHEBANG = f"#!{sys.executable}\n"


def _run(
    arguments: list[str], environment: dict[str, str] | None = None
) -> CommandResult:
    """Run a command in the repository root without raising on failure."""
    return run_fixed_command(arguments, cwd=REPOSITORY, environment=environment)


def _linker_version_and_digest() -> tuple[str, str]:
    """Read the pinned `mold` version and archive checksum from the repository."""
    version = (REPOSITORY / "tools/mold/VERSION").read_text(encoding="utf-8").strip()
    archive = f"mold-{version}-x86_64-linux.tar.gz"
    checksums = (REPOSITORY / "tools/mold/SHA256SUMS").read_text(encoding="utf-8")
    digest = next(
        fields[0]
        for fields in (line.split() for line in checksums.splitlines())
        if len(fields) == DIGEST_AND_NAME_FIELDS and fields[1] == archive
    )
    assert re.fullmatch(f"[0-9a-fA-F]{{{SHA256_HEX_DIGITS}}}", digest), digest
    return version, digest


def _write_executable(path: Path, text: str) -> None:
    """Write an executable script, creating nothing but the file itself."""
    path.write_text(text, encoding="utf-8")
    path.chmod(EXECUTABLE_MODE)


def _install_fake_linker(prefix: Path, reported_version: str, *, marker: bool) -> None:
    """Create the cached linker and, optionally, setup-rust's completion marker."""
    linker = prefix / "bin/ld.mold"
    linker.parent.mkdir(parents=True)
    _write_executable(linker, f"#!/bin/sh\nprintf 'mold {reported_version}\\n'\n")
    if marker:
        Path(f"{prefix}.complete").touch()


def _install_fake_commands(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Create fake ``rustup`` and ``curl`` commands that log their invocation.

    Returns
    -------
    tuple[Path, Path, Path]
        The fake bin directory, the curl log, and the rustup log.
    """
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    rustup_log = tmp_path / "rustup.log"
    curl_log = tmp_path / "curl.log"
    _write_executable(
        fake_bin / "rustup",
        PYTHON_SHEBANG + "import pathlib, sys\n"
        f"log = pathlib.Path({str(rustup_log)!r})\n"
        "log.open('a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        f"if sys.argv[1:3] == ['run', {PINNED_NIGHTLY!r}]:\n"
        "    print('host: x86_64-unknown-linux-gnu')\n"
        "elif sys.argv[1:3] == ['toolchain', 'install']:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit(2)\n",
    )
    _write_executable(
        fake_bin / "curl",
        PYTHON_SHEBANG + "import pathlib, sys\n"
        f"pathlib.Path({str(curl_log)!r}).write_text('invoked\\n')\n"
        "raise SystemExit(91)\n",
    )
    return fake_bin, curl_log, rustup_log


def _cache_environment(
    tmp_path: Path, *, marker: bool = True, reported_version: str = "2.41.0"
) -> tuple[dict[str, str], Path, Path, str]:
    """Create setup-rust's checksum-shaped cache and isolated command fakes."""
    version, digest = _linker_version_and_digest()
    tool_cache = tmp_path / "runner-tool-cache"
    prefix = tool_cache / "mold" / f"{version}-{digest}" / "x86_64"
    _install_fake_linker(prefix, reported_version, marker=marker)
    fake_bin, curl_log, _ = _install_fake_commands(tmp_path)

    inherited_path = os.environ.get("PATH", DEFAULT_PATH)
    environment = os.environ.copy()
    environment.update({
        "GITHUB_ACTIONS": "true",
        "RUNNER_TOOL_CACHE": str(tool_cache),
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join((str(prefix / "bin"), str(fake_bin), inherited_path)),
    })
    environment.pop("BUILD_TOOLS_PREFIX", None)
    (tmp_path / "home").mkdir()
    return environment, prefix, curl_log, version


def _run_make_install(environment: dict[str, str]) -> CommandResult:
    """Run the actual Make target with captured diagnostics."""
    return _run(["make", "--no-print-directory", "install-build-tools"], environment)


def test_make_installer_reuses_verified_setup_rust_cache(tmp_path: Path) -> None:
    """A verified setup-rust cache is reused without downloading the linker."""
    environment, prefix, curl_log, version = _cache_environment(tmp_path)

    result = _run_make_install(environment)

    assert result.returncode == 0, result.stderr
    assert f"reusing setup-rust's verified linker {version}" in result.stderr, (
        result.stderr
    )
    assert (prefix / "bin/evert-clang-mold").is_file(), "launcher must be installed"
    recorded_version = prefix / "share/evert/mold/VERSION"
    assert recorded_version.read_text(encoding="utf-8") == f"{version}\n", (
        "installed version record must match the pinned version"
    )
    assert not curl_log.exists(), "verified cache reuse must not download the linker"
    rustup_log = (tmp_path / "rustup.log").read_text(encoding="utf-8")
    assert f"toolchain install {PINNED_NIGHTLY}" in rustup_log, rustup_log


def test_make_installer_rejects_cache_without_completion_marker(
    tmp_path: Path,
) -> None:
    """A cache lacking setup-rust's completion marker fails closed."""
    environment, _, curl_log, _ = _cache_environment(tmp_path, marker=False)

    result = _run_make_install(environment)

    assert result.returncode != 0, "installer must fail"
    assert "failed provenance checks" in result.stderr, result.stderr
    assert not curl_log.exists(), "an invalid setup-rust cache must fail closed"


def test_make_installer_rejects_cache_with_wrong_linker_version(
    tmp_path: Path,
) -> None:
    """A cached linker reporting the wrong version fails closed."""
    environment, _, curl_log, _ = _cache_environment(tmp_path, reported_version="9.9.9")

    result = _run_make_install(environment)

    assert result.returncode != 0, "installer must fail"
    assert "failed provenance checks" in result.stderr, result.stderr
    assert not curl_log.exists(), "a cache with a wrong linker version must fail closed"


def test_make_requires_setup_rust_linker_on_path(tmp_path: Path) -> None:
    """Make refuses to proceed when setup-rust's linker is not on PATH."""
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    environment = os.environ.copy()
    environment.update({
        "GITHUB_ACTIONS": "true",
        "RUNNER_TOOL_CACHE": str(tmp_path / "runner-tool-cache"),
        "PATH": os.pathsep.join((str(fake_bin), os.environ.get("PATH", DEFAULT_PATH))),
    })
    environment.pop("BUILD_TOOLS_PREFIX", None)

    result = _run(
        ["make", "--no-print-directory", "--dry-run", "install-build-tools"],
        environment,
    )

    assert result.returncode != 0, "installer must fail"
    assert LINKER_MISSING_MESSAGE in result.stderr, result.stderr


def _darwin_environment(tmp_path: Path) -> dict[str, str]:
    """Build an environment whose PATH has Make but no pinned linker."""
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for executable in ("bash", "uname"):
        executable_path = shutil.which(executable)
        assert executable_path is not None, f"{executable} must be installed"
        (fake_bin / executable).symlink_to(executable_path)
    inherited_paths = os.environ.get("PATH", DEFAULT_PATH).split(os.pathsep)
    system_path_without_pinned_linker = [
        path
        for path in inherited_paths
        if path and not (Path(path) / "ld.mold").exists()
    ]
    environment = os.environ.copy()
    environment.update({
        "GITHUB_ACTIONS": "true",
        "HOME": str(tmp_path / "home"),
        "PATH": os.pathsep.join((str(fake_bin), *system_path_without_pinned_linker)),
    })
    for inherited in ("BUILD_TOOLS_PREFIX", "MAKEFLAGS", "MFLAGS"):
        environment.pop(inherited, None)
    assert shutil.which("ld.mold", path=environment["PATH"]) is None, (
        "PATH must not provide the pinned linker"
    )
    return environment


def test_make_parses_darwin_ci_without_linker_on_path(tmp_path: Path) -> None:
    """Darwin CI parses the Makefile without needing the Linux linker."""
    make = shutil.which("make")
    assert make is not None, "make must be installed"
    environment = _darwin_environment(tmp_path)

    result = _run(
        [make, "--no-print-directory", "--dry-run", "check-fmt", *PROBE_ARGUMENTS],
        environment,
    )

    assert result.returncode == 0, result.stderr
    assert "probe-cargo fmt --all -- --check" in result.stdout, result.stdout
    assert "probe-mdtablefix --check" in result.stdout, result.stdout


def test_make_fmt_uses_repository_pinned_rustfmt() -> None:
    """`make fmt` formats with the repository's pinned nightly toolchain."""
    toolchain = (REPOSITORY / "rust-toolchain.toml").read_text(encoding="utf-8")
    assert f'channel = "{PINNED_NIGHTLY}"' in toolchain, toolchain

    result = _run([
        "make",
        "--no-print-directory",
        "--dry-run",
        "fmt",
        *PROBE_ARGUMENTS,
        "MDLINT=probe-markdownlint",
    ])

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "probe-cargo fmt --all",
        (
            "probe-mdtablefix --in-place --git --include-untracked "
            "--wrap --renumber --breaks --ellipsis --fences"
        ),
        'probe-markdownlint --fix "**/*.md"',
    ], result.stdout
