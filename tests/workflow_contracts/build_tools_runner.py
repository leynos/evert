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
    values = _matrix_values(job, matrix_match.group(1))
    if values is None:
        return None
    statuses = [_runner_value_status(value) for value in values]
    if any(status is None for status in statuses):
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
    values = matrix.get(key)
    found: list[object]
    match values:
        case [_, *_]:
            found = list(values)
        case str() | int() | float() | bool():
            found = [values]
        case _:
            found = []
    includes = matrix.get("include", [])
    if not isinstance(includes, list) or not all(
        isinstance(row, dict) for row in includes
    ):
        return None
    found.extend(row[key] for row in includes if key in row)
    return found or None


def _runner_label_set_status(
    labels: list[object], job: dict[str, object]
) -> bool | None:
    """Classify runner labels without treating conflicting OS labels as Linux."""
    statuses = [_runner_value_status_for_job(value, job) for value in labels]
    has_linux = True in statuses
    has_non_linux = False in statuses
    if has_linux and has_non_linux:
        return None
    if has_linux:
        return True
    if has_non_linux:
        return False
    return None


def _runner_value_status_for_job(value: object, job: dict[str, object]) -> bool | None:
    """Resolve a runner matrix label only when all its values agree."""
    if not isinstance(value, str):
        return None
    matrix_match = MATRIX_EXPRESSION.fullmatch(value)
    if matrix_match is None:
        return _runner_value_status(value)
    values = _matrix_values(job, matrix_match.group(1))
    if values is None:
        return None
    statuses = [_runner_value_status(item) for item in values]
    if any(status is None for status in statuses) or len(set(statuses)) != 1:
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
