"""Require pinned linker provisioning before every Linux test-suite workflow path.

The standard development build uses the pinned linker on the proved x86_64 GNU/Linux
development route. This consumer contract checks direct Make/Cargo suites,
coverage actions, and the shared mutation workflow before those paths reach
compilation. It scans all workflows so a new suite job is measured without
adding its job id to a list.
"""

import re
import typing as typ
from pathlib import Path, PurePosixPath

from build_tools_runner import linux_runner_status
from workflow_contract_support import Document, WorkflowError, jobs, read_workflows

WORKFLOW_DIRECTORY: typ.Final[Path] = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows"
)
SETUP_RUST: typ.Final[str] = "leynos/shared-actions/.github/actions/setup-rust"
SETUP_RUST_REF: typ.Final[str] = (
    f"{SETUP_RUST}@c4ed5ffaf0640b1907d5359a87fd1677034eec27"
)
LINKER_VERSION: typ.Final[str] = "2.41.0"
MUTATION_WORKFLOW: typ.Final[str] = "mutation-cargo.yml"
SUITE_COMMAND: typ.Final[re.Pattern[str]] = re.compile(
    r"\b(?:cargo(?:\s+\+\S+)?\s+(?:test\b|nextest\b|llvm-cov\b)|"
    r"make\s+(?:-[A-Za-z][^\s]*\s+)*(?:test(?:-[A-Za-z0-9_-]+)?|coverage)\b)"
)


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
) -> tuple[bool, list[str]]:
    """Classify one job as a suite path and collect its provisioning violations."""
    if _is_mutation_job(job):
        return True, _mutation_violations(where, job)
    reusable_problem = _unresolved_reusable_problem(job, documents)
    if reusable_problem is not None:
        return False, [f"{where} {reusable_problem}"]

    step_list = _job_steps(where, job)
    suite_indexes = [
        index for index, step in enumerate(step_list) if _is_suite_step(step)
    ]
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
    return True, [
        *_step_installer_violations(where, step_list, first_suite),
        *_step_wrapper_violations(where, step_list, first_suite),
    ]


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
        path, separator, _reference = uses.partition("@")
        if separator:
            return "calls a local workflow at an uninspectable external ref"
        workflow_name = PurePosixPath(path).name
        if workflow_name not in documents:
            return "calls an unreadable local workflow"
        return "calls a local reusable workflow whose suite paths are not checked"
    return "calls an external reusable workflow whose suite runner cannot be inspected"


def _mutation_violations(where: str, job: dict[str, object]) -> list[str]:
    """Check the caller's pre-suite setup command and its failure handling."""
    setup = job.get("with")
    if not isinstance(setup, dict):
        return [f"{where} must pass make install-build-tools before mutation tests"]
    commands = setup.get("setup-commands")
    if not isinstance(commands, str):
        return [f"{where} must pass make install-build-tools before mutation tests"]

    violations: list[str] = []
    if _continues_on_error(job):
        violations.append(f"{where} must not soften mutation-suite failures")
    install_lines = [
        line.strip()
        for line in commands.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    exact_installs = [
        index
        for index, line in enumerate(install_lines)
        if line == "make install-build-tools"
    ]
    if len(exact_installs) != 1:
        violations.append(
            f"{where} setup-commands must run one unconditional "
            "make install-build-tools command"
        )
    elif any(line == "set +e" for line in install_lines[: exact_installs[0]]):
        violations.append(f"{where} must preserve the install-build-tools exit status")
    elif _install_is_conditional(install_lines, exact_installs[0]):
        violations.append(
            f"{where} setup-commands must run one unconditional "
            "make install-build-tools command"
        )
    return violations


def _continues_on_error(mapping: dict[str, object]) -> bool:
    """Treat an expression or any value other than literal false as unsafe."""
    return mapping.get("continue-on-error", False) is not False


def _install_is_conditional(lines: list[str], install_index: int) -> bool:
    """Return whether a preceding shell control block encloses the install."""
    conditional_depth = 0
    for line in lines[:install_index]:
        words = line.split()
        first = words[0].casefold() if words else ""
        match first:
            case "if" | "case" | "while" | "until":
                conditional_depth += 1
            case "fi" | "esac" | "done":
                conditional_depth = max(0, conditional_depth - 1)
    return conditional_depth > 0


def _is_suite_step(step: dict[str, object]) -> bool:
    """Recognize direct suite commands and the shared coverage action."""
    uses = step.get("uses")
    if uses is not None:
        if not isinstance(uses, str):
            message = f"cannot read step action reference {uses!r}"
            raise WorkflowError(message)
        if "generate-coverage" in uses.casefold():
            return True
    run = step.get("run")
    if run is None:
        return False
    if not isinstance(run, str):
        message = f"cannot read step run command {run!r}"
        raise WorkflowError(message)
    return any(
        SUITE_COMMAND.search(line) is not None
        for line in run.splitlines()
        if not line.lstrip().startswith("#")
    )


def _step_installer_violations(
    where: str, steps: list[dict[str, object]], suite_index: int
) -> list[str]:
    """Require an unconditional approved setup-rust step before the suite."""
    candidates = [
        (index, step)
        for index, step in enumerate(steps)
        if _is_setup_rust_candidate(step)
    ]
    valid_before = [
        index
        for index, step in candidates
        if index < suite_index and not _setup_rust_problems(step)
    ]
    if valid_before:
        return []

    problems = [
        problem for _, step in candidates for problem in _setup_rust_problems(step)
    ]
    if any(
        index >= suite_index and not _setup_rust_problems(step)
        for index, step in candidates
    ):
        problems.append("the pinned linker installer must run before the suite")
    if not candidates:
        problems.append("no pinned linker installer occurs before the suite")
    return [f"{where} {problem}" for problem in dict.fromkeys(problems)]


def _step_wrapper_violations(
    where: str, steps: list[dict[str, object]], suite_index: int
) -> list[str]:
    """Require a standalone Make installer before each Linux suite path."""
    candidates = [
        (index, step)
        for index, step in enumerate(steps)
        if isinstance(step.get("run"), str)
        and step["run"].strip() == "make install-build-tools"
    ]
    valid_before = [
        index
        for index, step in candidates
        if index < suite_index and "if" not in step and not _continues_on_error(step)
    ]
    if valid_before:
        return []

    problems: list[str] = []
    if not candidates:
        problems.append(
            "no unconditional make install-build-tools step occurs before the suite"
        )
    for index, step in candidates:
        if "if" in step:
            problems.append(
                "make install-build-tools step must not have an if condition"
            )
        if _continues_on_error(step):
            problems.append("make install-build-tools step must not continue on error")
        if index >= suite_index:
            problems.append("make install-build-tools must run before the suite")
    return [f"{where} {problem}" for problem in dict.fromkeys(problems)]


def _is_setup_rust_candidate(step: dict[str, object]) -> bool:
    """Recognize setup-rust steps that may own linker provisioning."""
    uses = step.get("uses")
    inputs = step.get("with")
    return (isinstance(uses, str) and SETUP_RUST in uses) or (
        isinstance(inputs, dict) and "install-mold" in inputs
    )


def _setup_rust_problems(step: dict[str, object]) -> list[str]:
    """Validate action identity, linker version, and unconditional execution."""
    uses = step.get("uses")
    inputs = step.get("with")
    if not isinstance(uses, str) or not isinstance(inputs, dict):
        return ["must use the pinned setup-rust linker installer"]

    problems: list[str] = []
    if uses != SETUP_RUST_REF:
        problems.append("must use the approved pinned setup-rust action")
    if inputs.get("install-mold") is not True and inputs.get("install-mold") != "true":
        problems.append("must enable setup-rust install-mold")
    version = inputs.get("mold-version")
    if version is not None and str(version) != LINKER_VERSION:
        problems.append(f"must install pinned linker version {LINKER_VERSION}")
    if "if" in step:
        problems.append("the pinned linker installer must not have an if condition")
    if _continues_on_error(step):
        problems.append("the pinned linker installer must not continue on error")
    return problems
