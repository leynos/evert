"""Build isolated command fixtures for the build-tool shell contracts."""

import dataclasses
import hashlib
import io
import os
import shutil
import tarfile
from pathlib import Path

from command_runner import CommandResult, run_fixed_command

REPOSITORY = Path(__file__).resolve().parents[2]
SCRIPTS = REPOSITORY / "scripts"
LINKER_VERSION = "2.41.0"
LINKER_NAME = "mold"
TOOLCHAIN = "nightly-2026-10-11"
HOST_TRIPLE = "x86_64-unknown-linux-gnu"
ARCHIVE_NAME = f"{LINKER_NAME}-{LINKER_VERSION}-x86_64-linux.tar.gz"
EXECUTABLE_MODE = 0o755
SYSTEM_PATH = "/usr/bin:/bin"


@dataclasses.dataclass(frozen=True, slots=True)
class BuildToolsFixture:
    """Paths and child environment used by isolated script tests."""

    root: Path
    environment: dict[str, str]
    fake_bin: Path
    prefix: Path
    rustup_log: Path
    curl_log: Path
    clang_log: Path


def write_executable(path: Path, contents: str) -> None:
    """Write a small executable shim into a test-owned directory."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    path.chmod(EXECUTABLE_MODE)


def create_fixture(
    tmp_path: Path,
    *,
    rustup_host: str = HOST_TRIPLE,
) -> BuildToolsFixture:
    """Create isolated pins, paths and command shims for a script run."""
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    prefix = tmp_path / "build-tools"
    (tmp_path / "home").mkdir()
    rustup_log = tmp_path / "rustup.log"
    curl_log = tmp_path / "curl.log"
    clang_log = tmp_path / "clang.log"
    system_install = shutil.which("install")
    if system_install is None:
        raise FileNotFoundError("install")
    version_file = tmp_path / f"{LINKER_NAME}-VERSION"
    version_file.write_text(f"{LINKER_VERSION}\n", encoding="utf-8")
    sums_file = tmp_path / f"{LINKER_NAME}-SHA256SUMS"
    sums_file.write_text("", encoding="utf-8")
    toolchain_file = tmp_path / "rust-toolchain.toml"
    toolchain_file.write_text(
        f'[toolchain]\nchannel = "{TOOLCHAIN}"\n'
        'components = ["clippy", "rustfmt"]\n',
        encoding="utf-8",
    )
    _write_uname(fake_bin)
    _write_rustup(fake_bin)
    _write_curl(fake_bin)
    _write_clang(fake_bin)

    environment = os.environ.copy()
    for name in (
        "BUILD_TOOLS_PREFIX",
        "GITHUB_ACTIONS",
        "RUNNER_TOOL_CACHE",
        "RUSTUP_TOOLCHAIN",
        "RUSTFLAGS",
        "CARGO_ENCODED_RUSTFLAGS",
    ):
        environment.pop(name, None)
    environment.update({
        "BUILD_TOOLS_PREFIX": str(prefix),
        "HOME": str(tmp_path / "home"),
        "SYSTEM_INSTALL": system_install,
        "LINKER_VERSION_FILE": str(version_file),
        "LINKER_SHA256SUMS_FILE": str(sums_file),
        "RUST_TOOLCHAIN_FILE": str(toolchain_file),
        "RUSTUP_HOST": rustup_host,
        "RUSTUP_LOG": str(rustup_log),
        "CURL_LOG": str(curl_log),
        "CLANG_LOG": str(clang_log),
        "PATH": os.pathsep.join((str(fake_bin), SYSTEM_PATH)),
    })
    return BuildToolsFixture(
        tmp_path, environment, fake_bin, prefix, rustup_log, curl_log, clang_log
    )


def run_script(
    fixture: BuildToolsFixture, script_name: str, *arguments: str
) -> CommandResult:
    """Run one repository build-tool script through the shared command runner."""
    return run_fixed_command(
        ["bash", str(SCRIPTS / script_name), *arguments],
        cwd=REPOSITORY,
        environment=fixture.environment,
    )


def create_linker_archive(
    path: Path, *, reported_version: str = LINKER_VERSION
) -> str:
    """Create a checksum-ready archive with one executable ``ld.mold``."""
    payload = f"#!/bin/sh\nprintf '{LINKER_NAME} {reported_version}\\n'\n".encode()
    archive_path = f"{LINKER_NAME}-fixture/bin/ld.mold"
    details = tarfile.TarInfo(archive_path)
    details.mode = EXECUTABLE_MODE
    details.size = len(payload)
    with tarfile.open(path, "w:gz") as archive:
        archive.addfile(details, io.BytesIO(payload))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_checksum_file(fixture: BuildToolsFixture, digest: str) -> None:
    """Set the fixture checksum entry for its pinned linker archive."""
    checksum_file = Path(fixture.environment["LINKER_SHA256SUMS_FILE"])
    checksum_file.write_text(f"{digest}  {ARCHIVE_NAME}\n", encoding="utf-8")


def install_fake_linker(
    prefix: Path, *, reported_version: str = LINKER_VERSION
) -> Path:
    """Create a version-reporting fake linker at the controlled prefix."""
    linker = prefix / "bin" / "ld.mold"
    write_executable(
        linker,
        f"#!/bin/sh\nprintf '{LINKER_NAME} {reported_version}\\n'\n",
    )
    return linker


def install_linker_pin(prefix: Path, version: str = LINKER_VERSION) -> Path:
    """Write the installed version marker expected by the checker and wrapper."""
    pin = prefix / "share/evert/mold/VERSION"
    pin.parent.mkdir(parents=True, exist_ok=True)
    pin.write_text(f"{version}\n", encoding="utf-8")
    return pin


def install_linker_wrapper(prefix: Path) -> Path:
    """Copy the repository wrapper into the fixture's controlled prefix."""
    wrapper = prefix / "bin" / "evert-clang-mold"
    write_executable(
        wrapper,
        (SCRIPTS / "clang-linker.sh").read_text(encoding="utf-8"),
    )
    return wrapper


def use_minimal_path(
    fixture: BuildToolsFixture, *, include_rustup: bool = True
) -> Path:
    """Set PATH to required shell utilities without ambient Clang or rustup."""
    minimal_bin = fixture.root / "minimal-bin"
    minimal_bin.mkdir(exist_ok=True)
    required_names = ("awk", "bash", "dirname", "grep")
    required_sources = {
        name: source
        for name in required_names
        if (source := shutil.which(name)) is not None
    }
    missing_name = next(
        (name for name in required_names if name not in required_sources), None
    )
    if missing_name is not None:
        raise FileNotFoundError(missing_name)
    for name, source in required_sources.items():
        (minimal_bin / name).symlink_to(source)
    fixture_names = ("uname", "rustup") if include_rustup else ("uname",)
    fixture_sources = {
        name: source
        for name in fixture_names
        if (source := fixture.fake_bin / name).exists()
    }
    for name, source in fixture_sources.items():
        (minimal_bin / name).symlink_to(source)
    fixture.environment["PATH"] = os.pathsep.join(
        (str(fixture.prefix / "bin"), str(minimal_bin))
    )
    return minimal_bin


def _write_uname(fake_bin: Path) -> None:
    """Make host-dependent branches deterministic for these Linux contracts."""
    write_executable(
        fake_bin / "uname",
        "#!/bin/sh\n"
        'case "${1:-}" in\n'
        "  -s) printf '%s\\n' \"${BUILD_TEST_UNAME_SYSTEM:-Linux}\" ;;\n"
        "  -m) printf '%s\\n' \"${BUILD_TEST_UNAME_MACHINE:-x86_64}\" ;;\n"
        "  *) exit 2 ;;\n"
        "esac\n",
    )


def _write_rustup(fake_bin: Path) -> None:
    """Create a rustup shim that reports a configured host and logs installs."""
    write_executable(
        fake_bin / "rustup",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$RUSTUP_LOG"\n'
        'case "${1:-}" in\n'
        "  run) printf 'host: %s\\n' \"$RUSTUP_HOST\" ;;\n"
        "  show) printf 'Default host: %s\\n' \"$RUSTUP_HOST\" ;;\n"
        '  toolchain) exit "${RUSTUP_INSTALL_STATUS:-0}" ;;\n'
        "  *) exit 2 ;;\n"
        "esac\n",
    )


def _write_curl(fake_bin: Path) -> None:
    """Create a curl shim that copies a prepared archive to ``--output``."""
    write_executable(
        fake_bin / "curl",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$CURL_LOG"\n'
        'if [ "${CURL_EXIT_STATUS:-0}" -ne 0 ]; then\n'
        '  exit "$CURL_EXIT_STATUS"\n'
        "fi\n"
        "output=\n"
        'while [ "$#" -gt 0 ]; do\n'
        '  if [ "$1" = --output ]; then shift; output=$1; fi\n'
        '  shift\n'
        "done\n"
        'cp "$ARCHIVE_FIXTURE" "$output"\n',
    )


def _write_clang(fake_bin: Path) -> None:
    """Create a Clang shim that captures arguments and controls resolution."""
    write_executable(
        fake_bin / "clang",
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$@" > "$CLANG_LOG"\n'
        'if [ "${CLANG_EXIT_STATUS:-0}" -ne 0 ]; then exit "$CLANG_EXIT_STATUS"; fi\n'
        'printf \'%s\\n\' "${CLANG_RESOLUTION:-}"\n',
    )
