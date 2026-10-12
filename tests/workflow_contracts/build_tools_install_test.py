"""Exercise fresh archive installation and controlled-prefix reuse."""

import hashlib
from pathlib import Path

import pytest
from build_tools_script_support import (
    ARCHIVE_NAME,
    LINKER_NAME,
    LINKER_VERSION,
    TOOLCHAIN,
    BuildToolsFixture,
    create_fixture,
    create_linker_archive,
    install_fake_linker,
    install_linker_pin,
    run_script,
    write_checksum_file,
    write_executable,
)
from command_runner import run_fixed_command


def _prepare_archive(
    fixture: BuildToolsFixture,
    tmp_path: Path,
    *,
    reported_version: str = LINKER_VERSION,
) -> None:
    """Attach a valid version-reporting archive and matching checksum."""
    archive = tmp_path / ARCHIVE_NAME
    digest = create_linker_archive(archive, reported_version=reported_version)
    fixture.environment["ARCHIVE_FIXTURE"] = str(archive)
    write_checksum_file(fixture, digest)


def test_installer_downloads_and_installs_the_verified_archive(
    tmp_path: Path,
) -> None:
    """The real installer downloads, verifies and installs its pinned linker."""
    fixture = create_fixture(tmp_path)
    _prepare_archive(fixture, tmp_path)

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode == 0, result.stderr
    assert f"verified {ARCHIVE_NAME}" in result.stderr, result.stderr
    assert f"installed `mold` linker {LINKER_VERSION}" in result.stderr, result.stderr
    installed = fixture.prefix / "bin/ld.mold"
    assert installed.is_file(), "verified archive must install ld.mold"
    version_result = run_fixed_command(
        [str(installed), "--version"],
        cwd=fixture.root,
        environment=fixture.environment,
    )
    assert version_result.stdout == f"{LINKER_NAME} {LINKER_VERSION}\n", version_result
    wrapper = fixture.prefix / "bin/evert-clang-mold"
    assert wrapper.is_file(), "installer must install its wrapper"
    assert wrapper.stat().st_mode & 0o111, "installer wrapper must be executable"
    pin = fixture.prefix / "share/evert/mold/VERSION"
    assert pin.read_text(encoding="utf-8") == f"{LINKER_VERSION}\n", (
        "wrapper pin must match the linker pin"
    )
    curl_arguments = fixture.curl_log.read_text(encoding="utf-8")
    assert ARCHIVE_NAME in curl_arguments, curl_arguments
    rustup_arguments = fixture.rustup_log.read_text(encoding="utf-8")
    assert (
        f"toolchain install {TOOLCHAIN} --profile minimal"
        " --component clippy --component rustfmt"
    ) in rustup_arguments, rustup_arguments


def test_installer_rejects_checksum_mismatch_before_extraction(
    tmp_path: Path,
) -> None:
    """A downloaded archive with the wrong checksum never reaches extraction."""
    fixture = create_fixture(tmp_path)
    _prepare_archive(fixture, tmp_path)
    write_checksum_file(fixture, "0" * 64)

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "checksum mismatch must fail"
    assert "checksum mismatch" in result.stderr, result.stderr
    assert not (fixture.prefix / "bin/ld.mold").exists(), (
        "unverified archive must not be extracted"
    )


def test_installer_rejects_an_archive_that_cannot_be_extracted(
    tmp_path: Path,
) -> None:
    """A checksum-valid non-archive reports the extraction boundary failure."""
    fixture = create_fixture(tmp_path)
    archive = tmp_path / ARCHIVE_NAME
    archive.write_bytes(b"not a gzip archive")
    fixture.environment["ARCHIVE_FIXTURE"] = str(archive)
    write_checksum_file(fixture, hashlib.sha256(archive.read_bytes()).hexdigest())

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "an invalid archive must fail"
    assert f"failed to unpack {ARCHIVE_NAME}" in result.stderr, result.stderr


def test_installer_rejects_wrong_version_from_downloaded_archive(
    tmp_path: Path,
) -> None:
    """A checksum-valid archive still must report the pinned linker version."""
    fixture = create_fixture(tmp_path)
    _prepare_archive(fixture, tmp_path, reported_version="9.9.9")

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "wrong installed version must fail"
    assert f"reports 9.9.9; expected {LINKER_VERSION}" in result.stderr, (
        result.stderr
    )


def test_installer_reuses_a_matching_controlled_prefix(tmp_path: Path) -> None:
    """A matching linker and pin avoid a download outside setup-rust cache."""
    fixture = create_fixture(tmp_path)
    install_fake_linker(fixture.prefix)
    install_linker_pin(fixture.prefix)

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode == 0, result.stderr
    assert "reusing verified `mold` linker" in result.stderr, result.stderr
    assert not fixture.curl_log.exists(), "verified prefix must not download"
    assert (fixture.prefix / "bin/evert-clang-mold").is_file(), (
        "installer must still refresh the wrapper"
    )


def test_installer_reports_download_failure(tmp_path: Path) -> None:
    """A failed curl request stops before checksum or extraction work."""
    fixture = create_fixture(tmp_path)
    _prepare_archive(fixture, tmp_path)
    fixture.environment["CURL_EXIT_STATUS"] = "47"

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "curl failure must fail"
    assert f"failed to download {ARCHIVE_NAME}" in result.stderr, result.stderr
    assert not (fixture.prefix / "bin/ld.mold").exists(), (
        "failed download must not install a linker"
    )


@pytest.mark.parametrize(
    ("failed_destination", "expected_message"),
    [
        pytest.param(
            "evert-clang-mold",
            "failed to install the linker wrapper",
            id="wrapper-write",
        ),
        pytest.param(
            "VERSION",
            "failed to install the linker version pin",
            id="pin-write",
        ),
    ],
)
def test_installer_reports_wrapper_or_pin_write_failure(
    tmp_path: Path, failed_destination: str, expected_message: str
) -> None:
    """A failed install command preserves the destination-specific diagnostic."""
    fixture = create_fixture(tmp_path)
    _prepare_archive(fixture, tmp_path)
    write_executable(
        fixture.fake_bin / "install",
        "#!/bin/sh\n"
        'case "$4" in\n'
        '  *"$INSTALL_FAIL_SUFFIX") exit 49 ;;\n'
        "esac\n"
        'exec "$SYSTEM_INSTALL" "$@"\n',
    )
    fixture.environment["INSTALL_FAIL_SUFFIX"] = failed_destination

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "failed file installation must fail the installer"
    assert expected_message in result.stderr, result.stderr


def test_installer_skips_linker_on_an_unsupported_host(tmp_path: Path) -> None:
    """An unsupported host gets the pinned toolchain without the Linux linker."""
    fixture = create_fixture(tmp_path, rustup_host="x86_64-apple-darwin")
    fixture.environment["BUILD_TEST_UNAME_SYSTEM"] = "Darwin"

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode == 0, result.stderr
    assert not fixture.curl_log.exists(), "unsupported host must not download linker"
    assert not (fixture.prefix / "bin/evert-clang-mold").exists(), (
        "unsupported host must not install the Linux wrapper"
    )


def test_installer_rejects_invalid_toolchain_components(tmp_path: Path) -> None:
    """Malformed rust-toolchain components fail before rustup installation."""
    fixture = create_fixture(tmp_path)
    toolchain_file = Path(fixture.environment["RUST_TOOLCHAIN_FILE"])
    toolchain_file.write_text(
        f'[toolchain]\nchannel = "{TOOLCHAIN}"\ncomponents = ["bad component"]\n',
        encoding="utf-8",
    )

    result = run_script(fixture, "install-build-tools.sh")

    assert result.returncode != 0, "invalid component must fail"
    assert "invalid component" in result.stderr, result.stderr
    rustup_arguments = fixture.rustup_log.read_text(encoding="utf-8")
    assert "toolchain install" not in rustup_arguments, rustup_arguments
