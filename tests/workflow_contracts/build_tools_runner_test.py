"""Test the runner shapes recognized by build-tool workflow contracts."""

import pytest
from build_tools_runner import linux_runner_status


@pytest.mark.parametrize(
    ("runner", "job", "expected"),
    [
        pytest.param("ubuntu-latest", {}, True, id="scalar-linux"),
        pytest.param(["self-hosted", "Linux", "X64"], {}, True, id="label-list"),
        pytest.param(
            {"group": "shared", "labels": ["ubuntu-24.04", "x64"]},
            {},
            True,
            id="group-with-label-list",
        ),
        pytest.param(
            "${{ matrix.os }}",
            {"strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}}},
            True,
            id="matrix-includes-linux",
        ),
        pytest.param("windows-latest", {}, False, id="scalar-windows"),
        pytest.param({"group": "unknown"}, {}, None, id="group-without-labels"),
        pytest.param(
            "${{ matrix.runner }}",
            {"strategy": {"matrix": {"runner": ["ubuntu-latest", "custom"]}}},
            None,
            id="matrix-with-unknown-runner",
        ),
    ],
)
def test_runner_shapes_are_classified_or_left_unknown(
    runner: object, job: dict[str, object], *, expected: bool | None
) -> None:
    """Recognized runners distinguish Linux, non-Linux, and uncertainty."""
    assert linux_runner_status(runner, job) is expected, runner
