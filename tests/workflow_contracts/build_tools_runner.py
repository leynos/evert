"""Classify GitHub Actions runners for build-tool workflow contracts."""

import re
import typing as typ

MATRIX_EXPRESSION: typ.Final[re.Pattern[str]] = re.compile(
    r"^\$\{\{\s*matrix\.([A-Za-z_][A-Za-z0-9_-]*)\s*\}\}$"
)


def linux_runner_status(runs_on: object, job: dict[str, object]) -> bool | None:
    """Return Linux, non-Linux, or unknown for scalar/list/group runners.

    Simple matrix expressions are resolved from their listed values. Unknown
    labels and unsupported expressions remain unknown so a suite job cannot
    become an accidental pass.

    Returns
    -------
    bool | None
        ``True`` for Linux, ``False`` for non-Linux, ``None`` when unknown.

    Examples
    --------
    >>> linux_runner_status("ubuntu-latest", {})
    True
    >>> linux_runner_status({"group": "hosted"}, {}) is None
    True
    """
    match runs_on:
        case str():
            return _scalar_runner_status(runs_on, job)
        case list():
            return _runner_label_set_status(runs_on, job)
        case dict():
            return _mapping_runner_status(runs_on, job)
        case _:
            return None


def _scalar_runner_status(runs_on: str, job: dict[str, object]) -> bool | None:
    """Classify a string runner, resolving a bare matrix expression by any-Linux."""
    matrix_match = MATRIX_EXPRESSION.fullmatch(runs_on)
    if matrix_match is None:
        return _runner_value_status_for_job(runs_on, job)
    statuses = _matrix_runner_statuses(job, matrix_match.group(1))
    if statuses is None:
        return None
    return any(statuses)


def _mapping_runner_status(
    runs_on: dict[str, object], job: dict[str, object]
) -> bool | None:
    """Classify a runner group mapping by its labels, if it has any."""
    if set(runs_on) - {"group", "labels"} or "labels" not in runs_on:
        return None
    labels = runs_on["labels"]
    if isinstance(labels, list):
        return _runner_label_set_status(labels, job)
    return _runner_value_status_for_job(labels, job)


def _matrix_values(job: dict[str, object], key: str) -> list[object] | None:
    """Resolve a simple runner matrix axis and its explicit include values."""
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    if not isinstance(matrix, dict):
        return None
    found = _matrix_axis_values(matrix.get(key))
    includes = _matrix_include_values(matrix.get("include", []), key)
    if includes is None:
        return None
    found.extend(includes)
    return found or None


def _matrix_axis_values(value: object) -> list[object]:
    """Copy supported matrix-axis values into a normalized list.

    Returns
    -------
    list[object]
        A fresh list for supported values, or an empty list otherwise.

    Examples
    --------
    >>> _matrix_axis_values(["ubuntu", "windows"])
    ['ubuntu', 'windows']
    >>> _matrix_axis_values("ubuntu")
    ['ubuntu']
    >>> _matrix_axis_values([])
    []
    """
    match value:
        case [_, *_]:
            return list(value)
        case str() | int() | float() | bool():
            return [value]
        case _:
            return []


def _matrix_include_values(value: object, key: str) -> list[object] | None:
    """Validate include rows and select values for one matrix axis.

    Returns
    -------
    list[object] | None
        Selected values, or ``None`` when include data is malformed.

    Examples
    --------
    >>> _matrix_include_values([{"os": "ubuntu"}], "os")
    ['ubuntu']
    >>> _matrix_include_values([{"arch": "x64"}], "os")
    []
    >>> _matrix_include_values([None], "os") is None
    True
    """
    if not isinstance(value, list) or not all(isinstance(row, dict) for row in value):
        return None
    rows = typ.cast("list[dict[str, object]]", value)
    return [row[key] for row in rows if key in row]


def _matrix_runner_statuses(job: dict[str, object], key: str) -> list[bool] | None:
    """Resolve one matrix key and reject any unclassifiable runner value.

    Returns
    -------
    list[bool] | None
        Known Linux statuses in matrix order, or ``None`` if any value is
        unknown or the matrix cannot be resolved.

    Examples
    --------
    >>> _matrix_runner_statuses(
    ...     {"strategy": {"matrix": {"os": ["ubuntu-latest", "windows-latest"]}}},
    ...     "os",
    ... )
    [True, False]
    """
    values = _matrix_values(job, key)
    if values is None:
        return None
    statuses = [_runner_value_status(value) for value in values]
    if any(status is None for status in statuses):
        return None
    return typ.cast("list[bool]", statuses)


def _runner_label_set_status(
    labels: list[object], job: dict[str, object]
) -> bool | None:
    """Classify runner labels without treating conflicting OS labels as Linux."""
    statuses = {_runner_value_status_for_job(value, job) for value in labels}
    known_statuses = statuses - {None}
    if len(known_statuses) != 1:
        return None
    return next(iter(known_statuses))


def _runner_value_status_for_job(value: object, job: dict[str, object]) -> bool | None:
    """Resolve a runner matrix label only when all its values agree."""
    if not isinstance(value, str):
        return None
    matrix_match = MATRIX_EXPRESSION.fullmatch(value)
    if matrix_match is None:
        return _runner_value_status(value)
    statuses = _matrix_runner_statuses(job, matrix_match.group(1))
    if statuses is None or len(set(statuses)) != 1:
        return None
    return statuses[0]


def _runner_value_status(value: object) -> bool | None:
    """Classify one explicit runner label as Linux, non-Linux, or unknown."""
    if not isinstance(value, str):
        return None
    label = value.casefold()
    if "${{" in label or "}}" in label:
        return None
    if "ubuntu" in label or "linux" in label:
        return True
    if any(platform in label for platform in ("windows", "macos", "mac-os", "freebsd")):
        return False
    return None
