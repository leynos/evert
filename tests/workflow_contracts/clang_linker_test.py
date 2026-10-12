"""Exercise the installed Clang wrapper's linker selection and argument path."""

import typing as typ

import pytest
from build_tools_script_support import (
    LINKER_VERSION,
    create_fixture,
    install_fake_linker,
    install_linker_pin,
    install_linker_wrapper,
    use_minimal_path,
)
from command_runner import run_fixed_command

if typ.TYPE_CHECKING:
    from pathlib import Path


def test_wrapper_selects_pinned_linker_and_preserves_arguments(
    tmp_path: Path,
) -> None:
    """The wrapper adds its linker directory and forwards compiler arguments."""
    fixture = create_fixture(tmp_path)
    install_fake_linker(fixture.prefix)
    install_linker_pin(fixture.prefix)
    wrapper = install_linker_wrapper(fixture.prefix)
    arguments = ["-c", "source file.c", "-o", "output file.o"]

    result = run_fixed_command(
        [str(wrapper), *arguments],
        cwd=fixture.root,
        environment=fixture.environment,
    )

    assert result.returncode == 0, result.stderr
    expected = [f"-B{fixture.prefix / 'bin'}", *arguments]
    assert (
        fixture.clang_log.read_text(encoding="utf-8").splitlines() == expected
    ), "wrapper must add -B and preserve each compiler argument"


def test_wrapper_rejects_a_linker_that_disagrees_with_its_pin(
    tmp_path: Path,
) -> None:
    """The wrapper stops before Clang when the installed linker is unpinned."""
    fixture = create_fixture(tmp_path)
    install_fake_linker(fixture.prefix, reported_version="9.9.9")
    install_linker_pin(fixture.prefix, LINKER_VERSION)
    wrapper = install_linker_wrapper(fixture.prefix)

    result = run_fixed_command(
        [str(wrapper), "-c", "source.c"],
        cwd=fixture.root,
        environment=fixture.environment,
    )

    assert result.returncode != 0, "wrong linker version must stop the wrapper"
    assert "does not match pinned" in result.stderr, result.stderr
    assert not fixture.clang_log.exists(), "Clang must not run with an unpinned linker"


@pytest.mark.parametrize(
    ("linker_state", "expected_message"),
    [
        pytest.param("missing", "missing or not executable", id="missing-linker"),
        pytest.param(
            "non-executable", "missing or not executable", id="non-executable-linker"
        ),
    ],
)
def test_wrapper_rejects_missing_or_non_executable_linker(
    tmp_path: Path, linker_state: str, expected_message: str
) -> None:
    """The wrapper stops before Clang when its pinned linker cannot execute."""
    fixture = create_fixture(tmp_path)
    linker = install_fake_linker(fixture.prefix)
    install_linker_pin(fixture.prefix)
    if linker_state == "missing":
        linker.unlink()
    else:
        linker.chmod(0o644)
    wrapper = install_linker_wrapper(fixture.prefix)

    result = run_fixed_command(
        [str(wrapper), "-c", "source.c"],
        cwd=fixture.root,
        environment=fixture.environment,
    )

    assert result.returncode != 0, "an unavailable linker must stop the wrapper"
    assert expected_message in result.stderr, result.stderr
    assert not fixture.clang_log.exists(), "Clang must not run without its linker"


@pytest.mark.parametrize(
    ("pin_state", "expected_message"),
    [
        pytest.param("missing", "cannot read linker version pin", id="missing-pin"),
        pytest.param("invalid", "invalid linker version pin", id="invalid-pin"),
    ],
)
def test_wrapper_rejects_missing_or_invalid_linker_pin(
    tmp_path: Path, pin_state: str, expected_message: str
) -> None:
    """The wrapper requires a readable single-line semantic version pin."""
    fixture = create_fixture(tmp_path)
    install_fake_linker(fixture.prefix)
    pin = install_linker_pin(fixture.prefix)
    if pin_state == "missing":
        pin.unlink()
    else:
        pin.write_text("not-a-version\n", encoding="utf-8")
    wrapper = install_linker_wrapper(fixture.prefix)

    result = run_fixed_command(
        [str(wrapper), "-c", "source.c"],
        cwd=fixture.root,
        environment=fixture.environment,
    )

    assert result.returncode != 0, "an invalid pin must stop the wrapper"
    assert expected_message in result.stderr, result.stderr
    assert not fixture.clang_log.exists(), "Clang must not run with an invalid pin"


def test_wrapper_reports_missing_clang_from_an_isolated_path(
    tmp_path: Path,
) -> None:
    """The wrapper fails clearly when Clang is absent from its child PATH."""
    fixture = create_fixture(tmp_path)
    install_fake_linker(fixture.prefix)
    install_linker_pin(fixture.prefix)
    wrapper = install_linker_wrapper(fixture.prefix)
    use_minimal_path(fixture)

    result = run_fixed_command(
        [str(wrapper), "-c", "source.c"],
        cwd=fixture.root,
        environment=fixture.environment,
    )

    assert result.returncode != 0, "missing Clang must stop the wrapper"
    assert "clang not found on PATH" in result.stderr, result.stderr
    assert not fixture.clang_log.exists(), "missing Clang cannot write its argument log"
