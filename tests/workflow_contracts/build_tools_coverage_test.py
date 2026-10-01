"""Test pull-request coverage compiler-flag isolation and preflight wiring."""

import dataclasses
import re

import pytest
from workflow_contract_support import Document, WorkflowError, fresh_documents, jobs

ENCODED_FLAGS = "CARGO_ENCODED_RUSTFLAGS"
COVERAGE_CHECK_NAME = "Check coverage compiler flag isolation"
ENCODED_FLAGS_CHECK = re.compile(
    r"(?ms)^\s*if \[\[ \$\{CARGO_ENCODED_RUSTFLAGS\+x\} \]\]; then\s+"
    r".*?^\s+exit 1\s*$\s+fi\s*$"
)


@dataclasses.dataclass(frozen=True, slots=True)
class _CoverageJob:
    """A CI job holding a coverage generator step and where that step sits."""

    job_id: str
    job: dict[str, object]
    steps: list[dict[str, object]]
    coverage_index: int


def _job_steps(job_id: str, job: dict[str, object]) -> list[dict[str, object]]:
    """Return a job's steps, failing closed when they are not mappings."""
    raw_steps = job.get("steps", [])
    if not isinstance(raw_steps, list) or not all(
        isinstance(step, dict) for step in raw_steps
    ):
        message = f"ci.yml:jobs.{job_id} has unreadable steps"
        raise WorkflowError(message)
    return raw_steps


def _scan_jobs(workflow: Document) -> tuple[list[_CoverageJob], list[str]]:
    """Find coverage steps and report step-level encoded-flag bindings."""
    coverage_jobs: list[_CoverageJob] = []
    violations: list[str] = []
    for job_id, job in jobs("ci.yml", workflow).items():
        steps = _job_steps(job_id, job)
        for index, step in enumerate(steps):
            if "generate-coverage" in str(step.get("uses", "")).casefold():
                coverage_jobs.append(_CoverageJob(job_id, job, steps, index))
            if _binds_encoded_flags(step):
                violations.append(
                    f"ci.yml:jobs.{job_id}:steps[{index}] env must not bind "
                    "CARGO_ENCODED_RUSTFLAGS"
                )
    return coverage_jobs, violations


def _preflight_violations(where: str, check_step: dict[str, object]) -> list[str]:
    """Report how the step before coverage fails to be a binding preflight."""
    if check_step.get("name") != COVERAGE_CHECK_NAME:
        return [f"{where} {COVERAGE_CHECK_NAME!r} must immediately precede coverage"]
    violations: list[str] = []
    if check_step.get("if") != "github.event_name == 'pull_request'":
        violations.append(
            f"{where} coverage compiler preflight must be pull-request-only"
        )
    if _continues_on_error(check_step):
        violations.append(
            f"{where} coverage compiler preflight must not continue on error"
        )
    run = check_step.get("run")
    if not isinstance(run, str) or ENCODED_FLAGS_CHECK.search(run) is None:
        violations.append(
            f"{where} coverage compiler preflight must fail when encoded flags are set"
        )
    return violations


def _job_violations(coverage: _CoverageJob) -> list[str]:
    """Report job-level encoded-flag bindings and preflight placement faults."""
    where = f"ci.yml:jobs.{coverage.job_id}"
    violations: list[str] = []
    if _binds_encoded_flags(coverage.job):
        violations.append(f"{where} env must not bind CARGO_ENCODED_RUSTFLAGS")
    if coverage.coverage_index == 0:
        violations.append(f"{where} coverage compiler preflight must precede coverage")
        return violations
    check_step = coverage.steps[coverage.coverage_index - 1]
    return [*violations, *_preflight_violations(where, check_step)]


def _coverage_flag_violations(documents: dict[str, Document]) -> list[str]:
    """Hold the PR coverage preflight before generation and out of env scopes."""
    workflow = documents.get("ci.yml")
    if workflow is None:
        return ["ci.yml is required for the pull-request coverage contract"]

    violations: list[str] = []
    if _binds_encoded_flags(workflow):
        violations.append("ci.yml workflow env must not bind CARGO_ENCODED_RUSTFLAGS")

    coverage_jobs, step_violations = _scan_jobs(workflow)
    violations.extend(step_violations)
    if not coverage_jobs:
        return [*violations, "ci.yml has no pull-request coverage action"]

    for coverage in coverage_jobs:
        violations.extend(_job_violations(coverage))
    return violations


def _binds_encoded_flags(mapping: dict[object, object]) -> bool:
    """Fail closed on malformed env maps and direct encoded-flag bindings."""
    environment = mapping.get("env")
    return environment is not None and (
        not isinstance(environment, dict) or ENCODED_FLAGS in environment
    )


def _continues_on_error(mapping: dict[str, object]) -> bool:
    """Treat expressions as unsafe unless continue-on-error is literal false."""
    return mapping.get("continue-on-error", False) is not False


def _ci_steps(documents: dict[str, Document]) -> list[dict[str, object]]:
    """Return CI's validated build-test steps for named workflow mutations."""
    workflow_jobs = jobs("ci.yml", documents["ci.yml"])
    raw_steps = workflow_jobs["build-test"].get("steps")
    assert isinstance(raw_steps, list), "build-test steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), (
        "build-test steps must be mappings"
    )
    return raw_steps


def _coverage_step_index(steps: list[dict[str, object]]) -> int:
    """Find CI's coverage generator step for ordering mutations."""
    return next(
        index
        for index, step in enumerate(steps)
        if "generate-coverage" in str(step.get("uses", "")).casefold()
    )


def test_coverage_compiler_preflight_is_binding_and_isolated() -> None:
    """The repository's CI workflow satisfies the coverage preflight contract."""
    violations = _coverage_flag_violations(fresh_documents())
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("removed", "must immediately precede coverage", id="removed"),
        pytest.param("late", "must immediately precede coverage", id="late"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
        pytest.param("wrong-event", "must be pull-request-only", id="wrong-event"),
        pytest.param(
            "empty-is-unset",
            "must fail when encoded flags are set",
            id="empty-is-unset",
        ),
    ],
)
def test_coverage_preflight_mutations_are_rejected(
    mutation: str, expected: str
) -> None:
    """Each preflight mutation is reported with its specific violation."""
    documents = fresh_documents()
    steps = _ci_steps(documents)
    coverage_index = _coverage_step_index(steps)
    check_index = coverage_index - 1
    check_step = steps[check_index]
    match mutation:
        case "removed":
            steps.pop(check_index)
        case "late":
            steps.append(steps.pop(check_index))
        case "soft-fail":
            check_step["continue-on-error"] = True
        case "wrong-event":
            check_step["if"] = "github.event_name == 'workflow_dispatch'"
        case _:
            check_step["run"] = (
                'if [[ -n "$CARGO_ENCODED_RUSTFLAGS" ]]; then\n  exit 1\nfi'
            )

    violations = _coverage_flag_violations(documents)
    assert any(expected in violation for violation in violations), violations


@pytest.mark.parametrize(
    "scope",
    [
        pytest.param("workflow", id="workflow-env"),
        pytest.param("job", id="job-env"),
        pytest.param("step", id="step-env"),
    ],
)
def test_encoded_flags_cannot_be_bound_in_coverage_environment_scopes(
    scope: str,
) -> None:
    """Binding encoded flags at workflow, job, or step scope is rejected."""
    documents = fresh_documents()
    workflow = documents["ci.yml"]
    if scope == "workflow":
        workflow["env"] = {ENCODED_FLAGS: ""}
    else:
        job = jobs("ci.yml", workflow)["build-test"]
        if scope == "job":
            job["env"] = {ENCODED_FLAGS: ""}
        else:
            steps = _ci_steps(documents)
            steps[_coverage_step_index(steps)]["env"] = {ENCODED_FLAGS: ""}

    violations = _coverage_flag_violations(documents)
    assert any(ENCODED_FLAGS in violation for violation in violations), violations
