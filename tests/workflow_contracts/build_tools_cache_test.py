"""Exercise setup-rust's linker cache through the real Make installer route."""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess


REPOSITORY = Path(__file__).resolve().parents[2]


def _cache_environment(
    tmp_path: Path, *, marker: bool = True, reported_version: str = "2.41.0"
) -> tuple[dict[str, str], Path, Path, str]:
    """Create setup-rust's checksum-shaped cache and isolated command fakes."""
    version = (REPOSITORY / "tools/mold/VERSION").read_text(encoding="utf-8").strip()
    archive = f"mold-{version}-x86_64-linux.tar.gz"
    checksums = (REPOSITORY / "tools/mold/SHA256SUMS").read_text(encoding="utf-8")
    digest = next(
        line.split()[0]
        for line in checksums.splitlines()
        if len(line.split()) == 2 and line.split()[1] == archive
    )
    assert re.fullmatch(r"[0-9a-fA-F]{64}", digest)

    tool_cache = tmp_path / "runner-tool-cache"
    prefix = tool_cache / "mold" / f"{version}-{digest}" / "x86_64"
    linker = prefix / "bin/ld.mold"
    linker.parent.mkdir(parents=True)
    linker.write_text(
        f"#!/bin/sh\nprintf 'mold {reported_version}\\n'\n", encoding="utf-8"
    )
    linker.chmod(0o755)
    if marker:
        Path(f"{prefix}.complete").touch()

    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    rustup_log = tmp_path / "rustup.log"
    rustup = fake_bin / "rustup"
    rustup.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(rustup_log)!r}).open('a').write(' '.join(sys.argv[1:]) + '\\n')\n"
        "if sys.argv[1:3] == ['run', 'nightly-2026-05-28']:\n"
        "    print('host: x86_64-unknown-linux-gnu')\n"
        "elif sys.argv[1:3] == ['toolchain', 'install']:\n"
        "    pass\n"
        "else:\n"
        "    raise SystemExit(2)\n",
        encoding="utf-8",
    )
    rustup.chmod(0o755)
    curl_log = tmp_path / "curl.log"
    curl = fake_bin / "curl"
    curl.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"pathlib.Path({str(curl_log)!r}).write_text('invoked\\n')\n"
        "raise SystemExit(91)\n",
        encoding="utf-8",
    )
    curl.chmod(0o755)

    inherited_path = os.environ.get("PATH", "/usr/bin:/bin")
    environment = os.environ.copy()
    environment.update(
        {
            "GITHUB_ACTIONS": "true",
            "RUNNER_TOOL_CACHE": str(tool_cache),
            "HOME": str(tmp_path / "home"),
            "PATH": os.pathsep.join((str(prefix / "bin"), str(fake_bin), inherited_path)),
        }
    )
    environment.pop("BUILD_TOOLS_PREFIX", None)
    (tmp_path / "home").mkdir()
    return environment, prefix, curl_log, version


def _run_make_install(environment: dict[str, str]) -> subprocess.CompletedProcess[str]:
    """Run the actual Make target with captured diagnostics."""
    return subprocess.run(
        ["make", "--no-print-directory", "install-build-tools"],
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_make_installer_reuses_verified_setup_rust_cache(tmp_path: Path) -> None:
    environment, prefix, curl_log, version = _cache_environment(tmp_path)

    result = _run_make_install(environment)

    assert result.returncode == 0, result.stderr
    assert f"reusing setup-rust's verified linker {version}" in result.stderr
    assert (prefix / "bin/evert-clang-mold").is_file()
    assert (prefix / "share/evert/mold/VERSION").read_text(encoding="utf-8") == f"{version}\n"
    assert not curl_log.exists(), "verified cache reuse must not download the linker"
    assert "toolchain install nightly-2026-05-28" in (tmp_path / "rustup.log").read_text(
        encoding="utf-8"
    )


def test_make_installer_rejects_cache_without_completion_marker(tmp_path: Path) -> None:
    environment, _, curl_log, _ = _cache_environment(tmp_path, marker=False)

    result = _run_make_install(environment)

    assert result.returncode != 0
    assert "failed provenance checks" in result.stderr
    assert not curl_log.exists(), "an invalid setup-rust cache must fail closed"


def test_make_installer_rejects_cache_with_wrong_linker_version(tmp_path: Path) -> None:
    environment, _, curl_log, _ = _cache_environment(
        tmp_path, reported_version="9.9.9"
    )

    result = _run_make_install(environment)

    assert result.returncode != 0
    assert "failed provenance checks" in result.stderr
    assert not curl_log.exists(), "a cache with a wrong linker version must fail closed"


def test_make_requires_setup_rust_linker_on_path(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    environment = os.environ.copy()
    environment.update(
        {
            "GITHUB_ACTIONS": "true",
            "RUNNER_TOOL_CACHE": str(tmp_path / "runner-tool-cache"),
            "PATH": os.pathsep.join((str(fake_bin), os.environ.get("PATH", "/usr/bin:/bin"))),
        }
    )
    environment.pop("BUILD_TOOLS_PREFIX", None)

    result = subprocess.run(
        ["make", "--no-print-directory", "--dry-run", "install-build-tools"],
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert "setup-rust must put its verified linker on PATH before Make runs" in result.stderr


def test_make_parses_darwin_ci_without_linker_on_path(tmp_path: Path) -> None:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    for executable in ("bash", "uname"):
        executable_path = shutil.which(executable)
        assert executable_path is not None
        (fake_bin / executable).symlink_to(executable_path)
    make = shutil.which("make")
    assert make is not None
    environment = os.environ.copy()
    inherited_paths = os.environ.get("PATH", "/usr/bin:/bin").split(os.pathsep)
    system_path_without_pinned_linker = [
        path
        for path in inherited_paths
        if path and not (Path(path) / "ld.mold").exists()
    ]
    environment.update(
        {
            "GITHUB_ACTIONS": "true",
            "HOME": str(tmp_path / "home"),
            "PATH": os.pathsep.join((str(fake_bin), *system_path_without_pinned_linker)),
        }
    )
    environment.pop("BUILD_TOOLS_PREFIX", None)
    environment.pop("MAKEFLAGS", None)
    environment.pop("MFLAGS", None)
    assert shutil.which("ld.mold", path=environment["PATH"]) is None

    result = subprocess.run(
        [
            make,
            "--no-print-directory",
            "--dry-run",
            "check-fmt",
            "BUILD_HOST_OS=Darwin",
            "BUILD_HOST_ARCH=x86_64",
            "CARGO=probe-cargo",
            "MDTABLEFIX=probe-mdtablefix",
        ],
        cwd=REPOSITORY,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert "probe-cargo fmt --all -- --check" in result.stdout
    assert "probe-mdtablefix --check" in result.stdout


def test_make_fmt_uses_repository_pinned_rustfmt() -> None:
    toolchain = (REPOSITORY / "rust-toolchain.toml").read_text(encoding="utf-8")
    assert 'channel = "nightly-2026-05-28"' in toolchain

    result = subprocess.run(
        [
            "make",
            "--no-print-directory",
            "--dry-run",
            "fmt",
            "BUILD_HOST_OS=Darwin",
            "BUILD_HOST_ARCH=x86_64",
            "CARGO=probe-cargo",
            "MDTABLEFIX=probe-mdtablefix",
            "MDLINT=probe-markdownlint",
        ],
        cwd=REPOSITORY,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.splitlines() == [
        "probe-cargo fmt --all",
        (
            "probe-mdtablefix --in-place --git --include-untracked "
            "--wrap --renumber --breaks --ellipsis --fences"
        ),
        'probe-markdownlint --fix "**/*.md"',
    ]
