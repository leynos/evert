"""Check Linux Make/Cargo, coverage, and mutation suites for pinned linker setup."""

import re
import typing as typ
from pathlib import Path, PurePosixPath

from build_tools_runner import linux_runner_status
from build_tools_step_provisioning import (
    _continues_on_error,
    step_provisioning_violations,
)
from workflow_contract_support import Document, WorkflowError, jobs, read_workflows

WORKFLOW_DIRECTORY: typ.Final[Path] = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows"
)
MUTATION_WORKFLOW: typ.Final[str] = "mutation-cargo.yml"
SUITE_COMMAND: typ.Final[re.Pattern[str]] = re.compile(
    r"\b(?:cargo(?:\s+\+\S+)?\s+(?:test\b|nextest\b|llvm-cov\b)|"
    r"make\s+(?:-[A-Za-z][^\s]*\s+)*(?:test(?:-[A-Za-z0-9_-]+)?|coverage)\b)"
)
_INSTALL_COMMAND_DIAGNOSTIC: typ.Final[str] = (
    "setup-commands must run one unconditional make install-build-tools command"
)
type JobRouteResult = tuple[bool, list[str]]


def build_tool_violations(documents: dict[str, Document]) -> list[str]:
    """Report Linux suite jobs that lack prior pinned linker provisioning.

    Every supplied workflow is scanned. A direct Make/Cargo test, coverage
    action, or mutation-cargo reusable call counts as a suite path. Unknown
    runner or job shapes fail closed when they contain such a path.

    Returns
    -------
    list[str]
        One message per violation; empty when every suite is compliant.

    Examples
    --------
    >>> build_tool_violations({})
    ['no workflow documents were read; refusing an empty suite set']
    >>> build_tool_violations({"empty.yml": {"jobs": {}}})
    ['no test, coverage, or mutation suite paths were found']
    """
    if not documents:
        return ["no workflow documents were read; refusing an empty suite set"]

    found_suites = 0
    violations: list[str] = []
    for workflow_name, document in documents.items():
        for job_id, job in jobs(workflow_name, document).items():
            where = f"{workflow_name}:jobs.{job_id}"
            is_suite, job_violations = _job_violations(where, job, documents)
            found_suites += is_suite
            violations.extend(job_violations)

    if not found_suites:
        violations.append("no test, coverage, or mutation suite paths were found")
    return violations


def _job_violations(
    where: str, job: dict[str, object], documents: dict[str, Document]
) -> JobRouteResult:
    """Keep mutation jobs ahead of ordinary reusable and direct suite routes."""
    if _is_mutation_job(job):
        return True, _mutation_violations(where, job)
    return _non_mutation_job_violations(where, job, documents)


def _non_mutation_job_violations(
    where: str, job: dict[str, object], documents: dict[str, Document]
) -> JobRouteResult:
    """Check reusable-workflow routing before inspecting ordinary job steps."""
    reusable_problem = _unresolved_reusable_problem(job, documents)
    if reusable_problem is not None:
        return False, [f"{where} {reusable_problem}"]
    return _direct_suite_violations(where, job)


def _direct_suite_violations(where: str, job: dict[str, object]) -> JobRouteResult:
    """Validate a direct suite path after mutation and reusable classification."""
    step_list = _job_steps(where, job)
    suite_indexes = [i for i, step in enumerate(step_list) if _is_suite_step(step)]
    if not suite_indexes:
        return False, []
    runner = linux_runner_status(job.get("runs-on"), job)
    if runner is None:
        return True, [
            f"{where} has a suite path but its Linux runner cannot be determined"
        ]
    if not runner:
        return True, []
    first_suite = min(suite_indexes)
    return True, step_provisioning_violations(where, step_list, first_suite)


def read_build_tool_workflows() -> dict[str, Document]:
    """Read every workflow with duplicate-key rejection enabled."""
    return read_workflows(WORKFLOW_DIRECTORY)


def _job_steps(where: str, job: dict[str, object]) -> list[dict[str, object]]:
    """Validate and return a workflow job's ordered step list."""
    raw_steps = job.get("steps", [])
    if not isinstance(raw_steps, list):
        message = f"{where}: cannot read job steps {raw_steps!r}"
        raise WorkflowError(message)
    if not all(isinstance(step, dict) for step in raw_steps):
        message = f"{where}: every workflow step must be a mapping"
        raise WorkflowError(message)
    return typ.cast("list[dict[str, object]]", raw_steps)


def _is_mutation_job(job: dict[str, object]) -> bool:
    """Recognize the shared mutation workflow, whose suite runs after setup."""
    uses = job.get("uses")
    if uses is None:
        return False
    if not isinstance(uses, str):
        message = f"cannot read reusable workflow reference {uses!r}"
        raise WorkflowError(message)
    return MUTATION_WORKFLOW in uses


def _unresolved_reusable_problem(
    job: dict[str, object], documents: dict[str, Document]
) -> str | None:
    """Refuse unknown reusable jobs whose suite and runner cannot be inspected."""
    uses = job.get("uses")
    if uses is None or not isinstance(uses, str):
        return None
    if uses.startswith(
        "leynos/shared-actions/.github/workflows/dependabot-automerge.yml@"
    ):
        return None
    if uses.startswith("./.github/workflows/"):
        return _local_workflow_problem(uses, documents)
    return "calls an external reusable workflow whose suite runner cannot be inspected"


def _local_workflow_problem(uses: str, documents: dict[str, Document]) -> str:
    """Check paths; ``_local_workflow_problem("missing.yml", {})`` flags missing.

    Returns
    -------
    str
        The policy diagnostic for the local workflow reference.
    """
    path, separator, _reference = uses.partition("@")
    if separator:
        return "calls a local workflow at an uninspectable external ref"
    workflow_name = PurePosixPath(path).name
    if workflow_name not in documents:
        return "calls an unreadable local workflow"
    return "calls a local reusable workflow whose suite paths are not checked"


def _mutation_violations(where: str, job: dict[str, object]) -> list[str]:
    """Check the caller's pre-suite setup command and its failure handling."""
    commands = _setup_commands(job)
    if commands is None:
        return [f"{where} must pass make install-build-tools before mutation tests"]

    violations: list[str] = []
    if _continues_on_error(job):
        violations.append(f"{where} must not soften mutation-suite failures")
    install_lines = [
        line.strip() for line in commands.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    install_problem = _install_order_problem(where, install_lines)
    if install_problem is not None:
        violations.append(install_problem)
    return violations


def _setup_commands(job: dict[str, object]) -> str | None:
    """Read setup commands, e.g. ``_setup_commands({})`` returns ``None``.

    Returns
    -------
    str | None
        Setup commands, or ``None`` for malformed input.
    """
    setup = job.get("with")
    commands = setup.get("setup-commands") if isinstance(setup, dict) else None
    return commands if isinstance(commands, str) else None


def _install_order_problem(where: str, install_lines: list[str]) -> str | None:
    """Find install errors; e.g. ``_install_order_problem("job", [])`` returns error.

    Returns
    -------
    str | None
        The first install-order diagnostic, or ``None`` when valid.
    """
    exact_installs = [
        index for index, line in enumerate(install_lines)
        if line == "make install-build-tools"
    ]
    if len(exact_installs) != 1:
        return f"{where} {_INSTALL_COMMAND_DIAGNOSTIC}"
    if any(line == "set +e" for line in install_lines[: exact_installs[0]]):
        return f"{where} must preserve the install-build-tools exit status"
    if _install_is_conditional(install_lines, exact_installs[0]):
        return f"{where} {_INSTALL_COMMAND_DIAGNOSTIC}"
    return None


def _install_is_conditional(lines: list[str], install_index: int) -> bool:
    """Return whether a preceding shell control block encloses the install."""
    conditional_depth = 0
    for line in lines[:install_index]:
        words = line.split()
        first = words[0].casefold() if words else ""
        match first:
            case "if" | "case" | "while" | "until" | "for" | "select":
                conditional_depth += 1
            case "fi" | "esac" | "done":
                conditional_depth = max(0, conditional_depth - 1)
    return conditional_depth > 0


def _is_suite_step(step: dict[str, object]) -> bool:
    """Recognize direct suite commands and the shared coverage action."""
    uses = _optional_text(step, "uses", "action reference")
    if uses is not None and "generate-coverage" in uses.casefold():
        return True
    run = _optional_text(step, "run", "run command")
    if run is None:
        return False
    return any(
        SUITE_COMMAND.search(line) is not None
        for line in run.splitlines()
        if not line.lstrip().startswith("#")
    )


def _optional_text(step: dict[str, object], key: str, label: str) -> str | None:
    """Read text, e.g. ``_optional_text({}, "run", "command")`` returns ``None``.

    Returns
    -------
    str | None
        The optional text value, or ``None`` when the key is absent.

    Raises
    ------
    WorkflowError
        If a present value is not a string.
    """
    if key not in step:
        return None
    value = step[key]
    if not isinstance(value, str):
        message = f"cannot read step {label} {value!r}"
        raise WorkflowError(message)
    return value
