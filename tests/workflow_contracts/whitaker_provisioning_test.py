"""Prove CI provisions the rolling Whitaker suite through its shared action."""

import re

import pytest
from build_tools_runner import linux_runner_status
from whitaker_provisioning_inputs import ProvisioningInputs, read_provisioning_inputs
from whitaker_provisioning_rules import (
    ACTION_USE,
    _LintJobContext,
    direct_setup_violations,
    lint_job_action_violations,
    workflow_lint_steps,
)
from workflow_contract_support import (
    Document,
    Step,
    continues_on_error,
    fresh_documents,
    jobs,
    mapping_at,
)

WORKFLOW = "ci.yml"
JOB = "build-test"


def _make_lint_step_violations(command: str, step: Step) -> list[str]:
    """Require a `make lint` step to be direct, unconditional and hard-failing."""
    where = f"{WORKFLOW}:jobs.{JOB}"
    violations: list[str] = []
    if command.strip() != "make lint":
        violations.append(f"{where} must run make lint directly")
    if "if" in step:
        violations.append(f"{where} make lint must be unconditional")
    if continues_on_error(step):
        violations.append(f"{where} make lint must not continue on error")
    return violations


def _ci_job_flag_violations(job: dict[str, object]) -> list[str]:
    """Require the primary CI job to be unconditional and hard-failing."""
    where = f"{WORKFLOW}:jobs.{JOB}"
    violations: list[str] = []
    if "if" in job:
        violations.append(f"{where} must be unconditional")
    if continues_on_error(job):
        violations.append(f"{where} must not continue on error")
    return violations


def _ci_job_violations(
    job: dict[str, object],
    ci_steps: list[dict[str, object]],
    inputs: ProvisioningInputs,
) -> list[str]:
    """Check the CI job's own flags, its lint steps and its Whitaker action."""
    where = f"{WORKFLOW}:jobs.{JOB}"
    violations = _ci_job_flag_violations(job)
    lint_indices: list[int] = []
    for index, step in enumerate(ci_steps):
        command = step.get("run")
        if isinstance(command, str) and re.search(r"\bmake\s+lint\b", command):
            lint_indices.append(index)
            violations.extend(_make_lint_step_violations(command, step))
    if len(lint_indices) != 1:
        violations.append(f"{where} requires exactly one make lint step")
    violations.extend(
        lint_job_action_violations(
            where,
            _LintJobContext(
                job_steps=ci_steps,
                lint_indices=lint_indices,
                route_name="make lint",
                expected_cranelift=inputs.cranelift_default,
            ),
        )
    )
    return violations


def _other_job_flag_violations(
    where: str, workflow_job: dict[str, object], *, is_indeterminate: bool
) -> list[str]:
    """Reject soft-failing jobs and lint paths that cannot be resolved locally."""
    violations: list[str] = []
    if continues_on_error(workflow_job):
        violations.append(f"{where} must not continue on error")
    if is_indeterminate:
        violations.append(f"{where} has an indeterminate local Make lint path")
    return violations


def _other_job_violations(
    name: str,
    job_id: str,
    workflow_job: dict[str, object],
    inputs: ProvisioningInputs,
) -> list[str]:
    """Check a non-primary Linux job whose steps reach the lint path."""
    if "uses" in workflow_job and "steps" not in workflow_job:
        return []
    job_steps, lint_path_indices, is_indeterminate = workflow_lint_steps(
        workflow_job, inputs.make_graph
    )
    if not lint_path_indices:
        return []
    where = f"{name}:jobs.{job_id}"
    runner = linux_runner_status(workflow_job.get("runs-on"), workflow_job)
    if runner is None:
        return [f"{where} has a lint path but its Linux runner cannot be determined"]
    if not runner:
        return []
    return [
        *_other_job_flag_violations(
            where, workflow_job, is_indeterminate=is_indeterminate
        ),
        *lint_job_action_violations(
            where,
            _LintJobContext(
                job_steps=job_steps,
                lint_indices=lint_path_indices,
                route_name="the lint path",
                expected_cranelift=inputs.cranelift_default,
            ),
        ),
    ]


def _other_jobs_violations(
    documents: dict[str, Document], inputs: ProvisioningInputs
) -> list[str]:
    """Check every job other than the primary CI job for lint-path provisioning."""
    return [
        violation
        for name, workflow in documents.items()
        for job_id, workflow_job in jobs(name, workflow).items()
        if (name, job_id) != (WORKFLOW, JOB)
        for violation in _other_job_violations(name, job_id, workflow_job, inputs)
    ]


def whitaker_provisioning_violations(documents: dict[str, Document]) -> list[str]:
    """Report CI routes that can omit or bypass the shared Whitaker action."""
    document = documents.get(WORKFLOW)
    if document is None:
        return [f"{WORKFLOW} is missing"]
    job = jobs(WORKFLOW, document).get(JOB)
    if job is None:
        return [f"{WORKFLOW}:jobs.{JOB} is missing"]
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list) or not all(
        isinstance(step, dict) for step in raw_steps
    ):
        return [
            *_ci_job_flag_violations(job),
            f"{WORKFLOW}:jobs.{JOB} has malformed steps",
        ]
    inputs = read_provisioning_inputs()
    return [
        *_ci_job_violations(job, raw_steps, inputs),
        *_other_jobs_violations(documents, inputs),
        *direct_setup_violations(documents),
    ]


def _assert_violations(documents: dict[str, Document], expected: list[str]) -> None:
    """Assert the exact violations reported for the workflow documents."""
    violations = whitaker_provisioning_violations(documents)
    assert violations == expected, violations


def test_ci_uses_the_approved_shared_whitaker_action_before_lint() -> None:
    """Accept the committed CI workflow as correctly provisioned."""
    _assert_violations(fresh_documents(), [])


@pytest.mark.parametrize(
    ("target", "job_id"),
    [
        pytest.param("lint", "future-direct-lint", id="new-direct-lint-job"),
        pytest.param("all", "future-composite-lint", id="new-composite-lint-job"),
    ],
)
def test_new_linux_lint_job_without_action_is_rejected(
    target: str, job_id: str
) -> None:
    """Reject a new Linux lint job that lacks the shared action."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")[job_id] = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": f"make {target}"}],
    }

    _assert_violations(
        documents,
        [f"ci.yml:jobs.{job_id} requires exactly one shared Whitaker action"],
    )


def test_new_linux_composite_lint_job_accepts_prior_action() -> None:
    """Accept a composite lint job that runs the action first."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")["future-composite-lint"] = {
        "runs-on": "ubuntu-latest",
        "steps": [
            {"uses": ACTION_USE, "with": {"cranelift": "false"}},
            {"run": "make all"},
        ],
    }

    _assert_violations(documents, [])


def test_new_linux_lint_job_with_job_level_soft_fail_is_rejected() -> None:
    """Reject a new lint job that soft-fails at job level."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")["future-soft-failing-lint"] = {
        "runs-on": "ubuntu-latest",
        "continue-on-error": True,
        "steps": [
            {"uses": ACTION_USE, "with": {"cranelift": "false"}},
            {"run": "make lint"},
        ],
    }

    _assert_violations(
        documents,
        ["ci.yml:jobs.future-soft-failing-lint must not continue on error"],
    )


def test_indeterminate_runner_for_a_new_lint_job_fails_closed() -> None:
    """Reject a lint job whose runner cannot be resolved to Linux."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")["future-unknown-lint"] = {
        "runs-on": "${{ inputs.runner }}",
        "steps": [{"run": "make lint"}],
    }

    _assert_violations(
        documents,
        [
            (
                "ci.yml:jobs.future-unknown-lint has a lint path but its Linux runner "
                "cannot be determined"
            )
        ],
    )
