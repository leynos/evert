"""Test pull-request coverage compiler-flag isolation and preflight wiring."""

from __future__ import annotations

import re

import pytest

from workflow_contract_support import Document, WorkflowError, fresh_documents, jobs

ENCODED_FLAGS = "CARGO_ENCODED_RUSTFLAGS"
COVERAGE_CHECK_NAME = "Check coverage compiler flag isolation"
ENCODED_FLAGS_CHECK = re.compile(
    r"(?ms)^\s*if \[\[ \$\{CARGO_ENCODED_RUSTFLAGS\+x\} \]\]; then\s+"
    r".*?^\s+exit 1\s*$\s+fi\s*$"
)


def _coverage_flag_violations(documents: dict[str, Document]) -> list[str]:
    """Hold the PR coverage preflight before generation and out of env scopes."""
    workflow = documents.get("ci.yml")
    if workflow is None:
        return ["ci.yml is required for the pull-request coverage contract"]

    violations: list[str] = []
    if _binds_encoded_flags(workflow):
        violations.append("ci.yml workflow env must not bind CARGO_ENCODED_RUSTFLAGS")

    coverage_jobs = []
    for job_id, job in jobs("ci.yml", workflow).items():
        raw_steps = job.get("steps", [])
        if not isinstance(raw_steps, list) or not all(
            isinstance(step, dict) for step in raw_steps
        ):
            raise WorkflowError(f"ci.yml:jobs.{job_id} has unreadable steps")
        steps = raw_steps
        for index, step in enumerate(steps):
            if "generate-coverage" in str(step.get("uses", "")).casefold():
                coverage_jobs.append((job_id, job, steps, index))
            if _binds_encoded_flags(step):
                violations.append(
                    f"ci.yml:jobs.{job_id}:steps[{index}] env must not bind "
                    "CARGO_ENCODED_RUSTFLAGS"
                )

    if not coverage_jobs:
        return violations + ["ci.yml has no pull-request coverage action"]

    for job_id, job, steps, coverage_index in coverage_jobs:
        where = f"ci.yml:jobs.{job_id}"
        if _binds_encoded_flags(job):
            violations.append(f"{where} env must not bind CARGO_ENCODED_RUSTFLAGS")
        if coverage_index == 0:
            violations.append(f"{where} coverage compiler preflight must precede coverage")
            continue
        check_step = steps[coverage_index - 1]
        if check_step.get("name") != COVERAGE_CHECK_NAME:
            violations.append(
                f"{where} {COVERAGE_CHECK_NAME!r} must immediately precede coverage"
            )
            continue
        if check_step.get("if") != "github.event_name == 'pull_request'":
            violations.append(f"{where} coverage compiler preflight must be pull-request-only")
        if _continues_on_error(check_step):
            violations.append(f"{where} coverage compiler preflight must not continue on error")
        run = check_step.get("run")
        if not isinstance(run, str) or ENCODED_FLAGS_CHECK.search(run) is None:
            violations.append(
                f"{where} coverage compiler preflight must fail when encoded flags are set"
            )
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
    assert isinstance(raw_steps, list) and all(isinstance(step, dict) for step in raw_steps)
    return raw_steps


def _coverage_step_index(steps: list[dict[str, object]]) -> int:
    """Find CI's coverage generator step for ordering mutations."""
    return next(
        index
        for index, step in enumerate(steps)
        if "generate-coverage" in str(step.get("uses", "")).casefold()
    )


def test_coverage_compiler_preflight_is_binding_and_isolated() -> None:
    violations = _coverage_flag_violations(fresh_documents())
    assert violations == [], "\n".join(violations)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("removed", "must immediately precede coverage", id="removed"),
        pytest.param("late", "must immediately precede coverage", id="late"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
        pytest.param("wrong-event", "must be pull-request-only", id="wrong-event"),
        pytest.param("empty-is-unset", "must fail when encoded flags are set", id="empty-is-unset"),
    ],
)
def test_coverage_preflight_mutations_are_rejected(
    mutation: str, expected: str
) -> None:
    documents = fresh_documents()
    steps = _ci_steps(documents)
    coverage_index = _coverage_step_index(steps)
    check_index = coverage_index - 1
    check_step = steps[check_index]
    if mutation == "removed":
        steps.pop(check_index)
    elif mutation == "late":
        steps.append(steps.pop(check_index))
    elif mutation == "soft-fail":
        check_step["continue-on-error"] = True
    elif mutation == "wrong-event":
        check_step["if"] = "github.event_name == 'workflow_dispatch'"
    else:
        check_step["run"] = (
            'if [[ -n "$CARGO_ENCODED_RUSTFLAGS" ]]; then\n'
            "  exit 1\n"
            "fi"
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
def test_encoded_flags_cannot_be_bound_in_coverage_environment_scopes(scope: str) -> None:
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
