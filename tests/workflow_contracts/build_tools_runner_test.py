"""Test the runner shapes recognized by build-tool workflow contracts."""

from copy import deepcopy

import pytest
from build_tools_runner import (
    _matrix_axis_values,
    _matrix_include_values,
    linux_runner_status,
)


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


@pytest.mark.parametrize(
    ("job", "runner"),
    [
        pytest.param({}, "${{ matrix.os }}", id="missing-strategy"),
        pytest.param({"strategy": None}, "${{ matrix.os }}", id="null-strategy"),
        pytest.param({"strategy": []}, "${{ matrix.os }}", id="non-mapping-strategy"),
        pytest.param({"strategy": {}}, "${{ matrix.os }}", id="missing-matrix"),
        pytest.param(
            {"strategy": {"matrix": None}},
            "${{ matrix.os }}",
            id="null-matrix",
        ),
        pytest.param(
            {"strategy": {"matrix": []}},
            "${{ matrix.os }}",
            id="non-mapping-matrix",
        ),
    ],
)
def test_missing_or_malformed_matrix_containers_are_unknown(
    job: dict[str, object], runner: str
) -> None:
    """Unsupported strategy and matrix shapes fail closed."""
    assert linux_runner_status(runner, job) is None, job


@pytest.mark.parametrize(
    ("matrix", "expected"),
    [
        pytest.param({}, None, id="missing-axis"),
        pytest.param({"os": []}, None, id="empty-axis"),
        pytest.param({"os": "ubuntu-latest"}, True, id="scalar-string-axis"),
        pytest.param({"os": ["ubuntu-latest"]}, True, id="single-list-axis"),
        pytest.param(
            {"os": ["ubuntu-latest", "windows-latest"]}, True, id="mixed-list-axis"
        ),
        pytest.param({"os": 3}, None, id="scalar-integer-axis-is-unknown"),
        pytest.param({"os": True}, None, id="scalar-boolean-axis-is-unknown"),
        pytest.param({"os": {"name": "ubuntu"}}, None, id="unsupported-axis-shape"),
    ],
)
def test_matrix_axes_normalize_only_supported_shapes(
    matrix: dict[str, object], expected: object
) -> None:
    """Missing and empty axes are unknown while supported values classify."""
    job: dict[str, object] = {"strategy": {"matrix": matrix}}
    assert linux_runner_status("${{ matrix.os }}", job) is expected, matrix


@pytest.mark.parametrize(
    ("matrix", "expected"),
    [
        pytest.param(
            {"include": [{"os": "ubuntu-latest"}]}, True, id="include-only-axis"
        ),
        pytest.param(
            {"os": ["windows-latest"], "include": [{"os": "ubuntu-latest"}]},
            True,
            id="axis-plus-include-values",
        ),
        pytest.param({"include": []}, None, id="empty-include-only-axis"),
        pytest.param({"os": ["ubuntu-latest"]}, True, id="absent-include"),
    ],
)
def test_matrix_include_values_preserve_axis_order_and_presence(
    matrix: dict[str, object], expected: object
) -> None:
    """Valid include rows add values, including for otherwise absent axes."""
    assert (
        linux_runner_status("${{ matrix.os }}", {"strategy": {"matrix": matrix}})
        is expected
    ), matrix


@pytest.mark.parametrize(
    "include",
    [
        pytest.param(None, id="null-include"),
        pytest.param("ubuntu-latest", id="string-include"),
        pytest.param({"os": "ubuntu-latest"}, id="mapping-include"),
        pytest.param([{"arch": "x64"}, None], id="bad-row-without-requested-key"),
    ],
)
def test_malformed_include_data_is_unknown_even_without_selected_values(
    include: object,
) -> None:
    """Every include row is validated, even if it lacks the requested axis."""
    matrix = {"include": include}
    assert (
        linux_runner_status("${{ matrix.os }}", {"strategy": {"matrix": matrix}})
        is None
    ), include


@pytest.mark.parametrize(
    ("runner", "matrix", "expected"),
    [
        pytest.param(
            "${{ matrix.os }}", ["ubuntu", "windows"], True, id="scalar-any-linux"
        ),
        pytest.param(
            ["${{ matrix.os }}"],
            ["ubuntu", "windows"],
            None,
            id="label-requires-unanimity",
        ),
        pytest.param(
            "${{ matrix.os }}",
            ["ubuntu", "unknown"],
            None,
            id="scalar-known-and-unknown",
        ),
        pytest.param(
            "${{ matrix.os }}", ["ubuntu", 7], None, id="scalar-known-and-non-string"
        ),
        pytest.param(
            ["${{ matrix.os }}"],
            ["ubuntu", "linux"],
            True,
            id="all-linux-label-expression",
        ),
        pytest.param(
            ["${{ matrix.os }}"],
            ["windows", "macos"],
            False,
            id="all-non-linux-label-expression",
        ),
    ],
)
def test_matrix_expression_callers_keep_their_aggregation_policy(
    runner: object, matrix: list[object], expected: object
) -> None:
    """Scalar expressions use any-Linux; label expressions require agreement."""
    job: dict[str, object] = {"strategy": {"matrix": {"os": matrix}}}
    assert linux_runner_status(runner, job) is expected, runner


@pytest.mark.parametrize(
    ("labels", "expected"),
    [
        pytest.param([], None, id="empty-labels"),
        pytest.param(["custom-runner"], None, id="unknown-only-labels"),
        pytest.param(
            ["ubuntu-latest", "windows-latest"], None, id="conflicting-os-labels"
        ),
        pytest.param(["ubuntu-latest", "x64"], True, id="linux-with-neutral-label"),
    ],
)
def test_label_lists_keep_unknown_and_conflict_semantics(
    labels: list[object], expected: object
) -> None:
    """Label-list aggregation keeps its explicit Linux/conflict policy."""
    assert linux_runner_status(labels, {}) is expected, labels


@pytest.mark.parametrize(
    ("runner", "expected"),
    [
        pytest.param(
            {"group": "hosted", "labels": "ubuntu-24.04"}, True, id="group-scalar-label"
        ),
        pytest.param(
            {"group": "hosted", "labels": ["ubuntu-24.04", "x64"]},
            True,
            id="group-label-list",
        ),
        pytest.param({"group": "hosted"}, None, id="missing-labels"),
        pytest.param(
            {"group": "hosted", "labels": "ubuntu", "extra": "unsupported"},
            None,
            id="unsupported-group-key",
        ),
    ],
)
def test_group_mappings_validate_shape_and_classify_labels(
    runner: dict[str, object], expected: object
) -> None:
    """Group runners accept only the existing group and labels keys."""
    assert linux_runner_status(runner, {}) is expected, runner


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        pytest.param("runner", True, id="plain-key"),
        pytest.param("runner_group", True, id="underscore-key"),
        pytest.param("runner-arch", True, id="hyphen-key"),
        pytest.param("runner.expr", None, id="unsupported-expression"),
    ],
)
def test_matrix_key_spellings_follow_the_supported_expression(
    key: str, expected: object
) -> None:
    """Only simple supported key spellings are resolved from the matrix."""
    runner = f"${{{{ matrix.{key} }}}}"
    job: dict[str, object] = {"strategy": {"matrix": {key: "ubuntu-latest"}}}
    assert linux_runner_status(runner, job) is expected, runner


def test_explicit_labels_are_case_insensitive_and_linux_matching_is_first() -> None:
    """Label matching is case-insensitive and retains Linux-first precedence."""
    assert linux_runner_status("UBUNTU-24.04", {}) is True, "Ubuntu label was not Linux"
    assert linux_runner_status("Windows-Linux", {}) is True, "Linux match must win"


def test_matrix_classification_does_not_mutate_the_supplied_job() -> None:
    """Normalization copies axis and include data without changing the job."""
    job: dict[str, object] = {
        "strategy": {
            "matrix": {
                "os": ["ubuntu-latest", "windows-latest"],
                "include": [{"os": "linux"}, {"arch": "x64"}],
            }
        }
    }
    original = deepcopy(job)

    assert linux_runner_status("${{ matrix.os }}", job) is True, (
        "mixed matrix must retain any-Linux scalar semantics"
    )
    assert job == original, "matrix classification mutated the workflow job"


@pytest.mark.parametrize(
    ("include", "expected"),
    [
        pytest.param([{"arch": "x64"}], [], id="valid-unselected-row"),
        pytest.param([], [], id="valid-empty-include"),
        pytest.param([{"arch": "x64"}, None], None, id="invalid-unselected-row"),
    ],
)
def test_matrix_include_reader_distinguishes_empty_from_malformed(
    include: object, expected: list[object] | None
) -> None:
    """Include rows are fully validated before values for one axis are selected."""
    assert _matrix_include_values(include, "os") == expected, include


def test_matrix_axis_reader_copies_non_empty_lists() -> None:
    """Axis normalization returns a separate list and ignores empty lists."""
    axis = ["ubuntu-latest", "windows-latest"]
    normalized = _matrix_axis_values(axis)

    assert normalized == axis, "axis contents changed"
    assert normalized is not axis, "axis list was not copied"
    assert not _matrix_axis_values([]), "empty axis gained values"
