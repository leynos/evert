"""Exercise compiler and linker preflight success and failure routes."""

import typing as typ

import pytest
from build_tools_script_support import (
    LINKER_VERSION,
    TOOLCHAIN,
    BuildToolsFixture,
    create_fixture,
    install_fake_linker,
    install_linker_pin,
    install_linker_wrapper,
    run_script,
    use_minimal_path,
    write_executable,
)

if typ.TYPE_CHECKING:
    from pathlib import Path


def _ready_fixture(tmp_path: Path) -> BuildToolsFixture:
    """Install the linker, pin and real wrapper into a controlled prefix."""
    fixture = create_fixture(tmp_path)
    linker = install_fake_linker(fixture.prefix)
    install_linker_pin(fixture.prefix)
    install_linker_wrapper(fixture.prefix)
    fixture.environment["CLANG_RESOLUTION"] = str(linker)
    fixture.environment["PATH"] = ":".join(
        (str(fixture.prefix / "bin"), str(fixture.fake_bin), "/usr/bin:/bin")
    )
    return fixture


def test_checker_accepts_the_pinned_toolchain_and_wrapper(tmp_path: Path) -> None:
    """The preflight accepts a rustup host and wrapper selecting the pinned linker."""
    fixture = _ready_fixture(tmp_path)

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode == 0, result.stderr
    assert (
        f"toolchain {TOOLCHAIN} is available for "
        f"{fixture.environment['RUSTUP_HOST']}" in result.stderr
    ), "checker should identify the pinned toolchain and selected host"
    assert f"`mold` linker {LINKER_VERSION}" in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("linker_state", "expected_message"),
    [
        pytest.param("missing", "missing or not executable", id="missing-linker"),
        pytest.param(
            "non-executable", "missing or not executable", id="non-executable-linker"
        ),
        pytest.param("wrong", "does not match the pin", id="wrong-linker-version"),
    ],
)
def test_checker_rejects_missing_or_wrong_linker(
    tmp_path: Path, linker_state: str, expected_message: str
) -> None:
    """A missing or incorrectly pinned linker blocks the development route."""
    fixture = _ready_fixture(tmp_path)
    linker = fixture.prefix / "bin/ld.mold"
    match linker_state:
        case "missing":
            linker.unlink()
        case "non-executable":
            linker.chmod(0o644)
        case _:
            install_fake_linker(fixture.prefix, reported_version="9.9.9")

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "linker problem must fail the preflight"
    assert expected_message in result.stderr, result.stderr


@pytest.mark.parametrize(
    ("pin_state", "expected_message"),
    [
        pytest.param("missing", "installed linker pin is missing", id="missing-pin"),
        pytest.param("wrong", "does not match repository pin", id="wrong-pin"),
    ],
)
def test_checker_rejects_missing_or_wrong_installed_pin(
    tmp_path: Path, pin_state: str, expected_message: str
) -> None:
    """The installed provenance pin must agree with the repository pin."""
    fixture = _ready_fixture(tmp_path)
    pin = fixture.prefix / "share/evert/mold/VERSION"
    if pin_state == "missing":
        pin.unlink()
    else:
        pin.write_text("9.9.9\n", encoding="utf-8")

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "invalid installed pin must fail"
    assert expected_message in result.stderr, result.stderr


def test_checker_requires_the_installed_wrapper_on_path(tmp_path: Path) -> None:
    """A different wrapper earlier on PATH cannot satisfy the preflight."""
    fixture = _ready_fixture(tmp_path)
    shadow_bin = tmp_path / "shadow-bin"
    write_executable(shadow_bin / "evert-clang-mold", "#!/bin/sh\nexit 0\n")
    fixture.environment["PATH"] = ":".join(
        (
            str(shadow_bin),
            str(fixture.prefix / "bin"),
            str(fixture.fake_bin),
            "/usr/bin:/bin",
        )
    )

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "shadow wrapper must fail provenance check"
    assert "PATH does not select the installed linker wrapper" in result.stderr, (
        result.stderr
    )


def test_checker_rejects_a_wrapper_that_resolves_another_linker(
    tmp_path: Path,
) -> None:
    """Clang's resolution output must name the pinned linker path."""
    fixture = _ready_fixture(tmp_path)
    fixture.environment["CLANG_RESOLUTION"] = str(fixture.root / "wrong-linker")

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "wrong linker resolution must fail"
    assert "does not resolve -fuse-ld=mold" in result.stderr, result.stderr


def test_checker_rejects_a_missing_wrapper(tmp_path: Path) -> None:
    """A valid linker and pin still require the installed wrapper."""
    fixture = _ready_fixture(tmp_path)
    (fixture.prefix / "bin/evert-clang-mold").unlink()

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "missing wrapper must fail the preflight"
    assert "pinned Clang linker wrapper is missing" in result.stderr, result.stderr


def test_checker_reports_missing_clang_from_an_isolated_path(tmp_path: Path) -> None:
    """The installed wrapper fails when no Clang executable is available."""
    fixture = _ready_fixture(tmp_path)
    use_minimal_path(fixture)

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "missing Clang must fail the preflight"
    assert "cannot resolve the pinned `mold` linker" in result.stderr, result.stderr


def test_checker_reports_missing_rustup_from_an_isolated_path(tmp_path: Path) -> None:
    """The preflight does not fall back to an ambient rustup installation."""
    fixture = _ready_fixture(tmp_path)
    use_minimal_path(fixture, include_rustup=False)

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode != 0, "missing rustup must fail the preflight"
    assert "rustup not found on PATH" in result.stderr, result.stderr


def test_checker_keeps_platform_linker_on_unsupported_host(tmp_path: Path) -> None:
    """The pinned linker prerequisite is skipped on an unsupported host."""
    fixture = create_fixture(tmp_path, rustup_host="x86_64-apple-darwin")
    fixture.environment["BUILD_TEST_UNAME_SYSTEM"] = "Darwin"

    result = run_script(fixture, "check-build-tools.sh")

    assert result.returncode == 0, result.stderr
    assert "are not required on Darwin" in result.stderr, result.stderr
