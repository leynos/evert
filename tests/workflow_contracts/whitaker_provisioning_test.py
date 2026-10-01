"""Prove CI provisions the rolling Whitaker suite through its shared action."""

import dataclasses
import re
import typing as typ

import pytest
from build_tools_runner import linux_runner_status
from whitaker_provisioning_rules import (
    ACTION,
    ACTION_USE,
    FORBIDDEN_INPUTS,
    action_steps,
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
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

WORKFLOW = "ci.yml"
JOB = "build-test"


def _job_steps(documents: dict[str, Document]) -> tuple[dict[str, object], list[Step]]:
    """Return the named CI job and its step mappings."""
    job = jobs(WORKFLOW, documents[WORKFLOW])[JOB]
    raw_steps = job.get("steps")
    assert isinstance(raw_steps, list), f"{WORKFLOW}:jobs.{JOB} steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), "steps must be mappings"
    return job, raw_steps


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


def _ci_job_violations(job: dict[str, object], ci_steps: list[Step]) -> list[str]:
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
        lint_job_action_violations(where, ci_steps, lint_indices, "make lint")
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
    name: str, job_id: str, workflow_job: dict[str, object]
) -> list[str]:
    """Check a non-primary Linux job whose steps reach the lint path."""
    if "uses" in workflow_job and "steps" not in workflow_job:
        return []
    job_steps, lint_path_indices, is_indeterminate = workflow_lint_steps(workflow_job)
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
            where, job_steps, lint_path_indices, "the lint path"
        ),
    ]


def _other_jobs_violations(documents: dict[str, Document]) -> list[str]:
    """Check every job other than the primary CI job for lint-path provisioning."""
    return [
        violation
        for name, workflow in documents.items()
        for job_id, workflow_job in jobs(name, workflow).items()
        if (name, job_id) != (WORKFLOW, JOB)
        for violation in _other_job_violations(name, job_id, workflow_job)
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
    return [
        *_ci_job_violations(job, raw_steps),
        *_other_jobs_violations(documents),
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
    documents["ci.yml"]["jobs"][job_id] = {
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
    documents["ci.yml"]["jobs"]["future-composite-lint"] = {
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
    documents["ci.yml"]["jobs"]["future-soft-failing-lint"] = {
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
    documents["ci.yml"]["jobs"]["future-unknown-lint"] = {
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


@dataclasses.dataclass(frozen=True, slots=True)
class _Scenario:
    """Mutable CI workflow fixture with the positions mutations act upon."""

    documents: dict[str, Document]
    ci_steps: list[Step]
    action: Step
    lint_index: int

    def action_index(self) -> int:
        """Locate the shared action step at the time of the call."""
        return self.ci_steps.index(self.action)


def _scenario() -> _Scenario:
    """Load fresh workflows and locate the action and lint steps."""
    documents = fresh_documents()
    _, ci_steps = _job_steps(documents)
    lint_index = next(
        index for index, step in enumerate(ci_steps) if step.get("run") == "make lint"
    )
    return _Scenario(documents, ci_steps, action_steps(ci_steps)[0], lint_index)


def _move_action_after_lint(scenario: _Scenario) -> None:
    """Run the shared action after the lint step."""
    action = scenario.ci_steps.pop(scenario.action_index())
    scenario.ci_steps.insert(scenario.lint_index + 1, action)


def _set_action_key(key: str, *, value: object) -> cabc.Callable[[_Scenario], None]:
    """Build a mutation that sets a top-level key on the action step."""

    def mutate(scenario: _Scenario) -> None:
        """Set the key on the action step."""
        scenario.action[key] = value

    return mutate


def _set_action_input(name: str, value: str) -> cabc.Callable[[_Scenario], None]:
    """Build a mutation that sets an input on the action step."""

    def mutate(scenario: _Scenario) -> None:
        """Set the input on the action step."""
        scenario.action.setdefault("with", {})[name] = value

    return mutate


def _set_lint_key(key: str, *, value: object) -> cabc.Callable[[_Scenario], None]:
    """Build a mutation that sets a key on the lint step."""

    def mutate(scenario: _Scenario) -> None:
        """Set the key on the lint step."""
        scenario.ci_steps[scenario.lint_index][key] = value

    return mutate


def _append_run(command: str) -> cabc.Callable[[_Scenario], None]:
    """Build a mutation that appends a run step to the CI job."""

    def mutate(scenario: _Scenario) -> None:
        """Append the run step."""
        scenario.ci_steps.append({"run": command})

    return mutate


def _remove_action(scenario: _Scenario) -> None:
    """Delete the shared action step."""
    scenario.ci_steps.pop(scenario.action_index())


def _remove_lint(scenario: _Scenario) -> None:
    """Delete the lint step."""
    scenario.ci_steps.pop(scenario.lint_index)


_MUTATIONS: dict[str, cabc.Callable[[_Scenario], None]] = {
    "remove": _remove_action,
    "late": _move_action_after_lint,
    "conditional": _set_action_key("if", value="runner.os == 'Linux'"),
    "soft-fail": _set_action_key("continue-on-error", value=True),
    "wrong-pin": _set_action_key("uses", value=f"{ACTION}@v0.2.9"),
    **{name: _set_action_input(name, "0.2.9") for name in FORBIDDEN_INPUTS},
    "direct-installer": _append_run("whitaker-installer --no-source-fallback"),
    "cargo-dylint": _append_run("cargo binstall --no-confirm cargo-dylint"),
    "ignored-lint": _set_lint_key("run", value="make lint || true"),
    "remove-lint": _remove_lint,
    "conditional-lint": _set_lint_key("if", value="runner.os == 'Linux'"),
    "soft-fail-lint": _set_lint_key("continue-on-error", value=True),
    "cranelift-mismatch": _set_action_input("cranelift", "true"),
}


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param(
            "remove", "requires exactly one shared Whitaker action", id="removed"
        ),
        pytest.param("late", "must run before make lint", id="moved-after-lint"),
        pytest.param(
            "conditional", "Whitaker action must be unconditional", id="conditional"
        ),
        pytest.param(
            "soft-fail", "Whitaker action must not continue on error", id="soft-failing"
        ),
        pytest.param(
            "wrong-pin", "must pin the approved Whitaker action SHA", id="wrong-pin"
        ),
        pytest.param("suite-version", "must not set suite-version", id="suite-version"),
        pytest.param(
            "allow-suite-pin", "must not set allow-suite-pin", id="allow-suite-pin"
        ),
        pytest.param(
            "installer-version",
            "must not set installer-version",
            id="installer-version",
        ),
        pytest.param(
            "direct-installer", "direct Whitaker or cargo-dylint", id="direct-installer"
        ),
        pytest.param(
            "cargo-dylint", "direct Whitaker or cargo-dylint", id="cargo-dylint-setup"
        ),
        pytest.param("ignored-lint", "must run make lint directly", id="ignored-lint"),
        pytest.param(
            "remove-lint", "requires exactly one make lint step", id="missing-lint"
        ),
        pytest.param(
            "conditional-lint", "make lint must be unconditional", id="conditional-lint"
        ),
        pytest.param(
            "soft-fail-lint",
            "make lint must not continue on error",
            id="soft-failing-lint",
        ),
        pytest.param(
            "cranelift-mismatch", "cranelift input must match", id="backend-mismatch"
        ),
    ],
)
def test_whitaker_provisioning_mutations_are_rejected(
    mutation: str, expected: str
) -> None:
    """Reject each way of weakening the shared-action provisioning contract."""
    scenario = _scenario()
    _MUTATIONS[mutation](scenario)

    violations = whitaker_provisioning_violations(scenario.documents)
    assert any(expected in violation for violation in violations), violations
