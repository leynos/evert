"""Prove CI provisions the rolling Whitaker suite through its shared action."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from build_tools_runner import linux_runner_status
from whitaker_provisioning_rules import workflow_lint_steps
from workflow_contract_support import (
    Document,
    Step,
    calls,
    continues_on_error,
    fresh_documents,
    jobs,
    steps,
)

WORKFLOW = "ci.yml"
JOB = "build-test"
ACTION = "leynos/shared-actions/.github/actions/install-whitaker"
ACTION_REF = "6dea5677a84fec60ca51b07202570e3af12ffdb4"
ACTION_USE = f"{ACTION}@{ACTION_REF}"
FORBIDDEN_INPUTS = {"allow-suite-pin", "installer-version", "suite-version"}
DIRECT_SETUP = re.compile(
    r"\bwhitaker-installer\b|\bcargo-dylint\b|"
    r"\bcargo\s+(?:install|binstall)\b[^\n]*(?:whitaker|dylint)",
    re.IGNORECASE,
)
TARGET = "x86_64-unknown-linux-gnu"


def _job_steps(documents: dict[str, Document]) -> tuple[dict[str, object], list[Step]]:
    """Return the named CI job and its step mappings."""
    job = jobs(WORKFLOW, documents[WORKFLOW])[JOB]
    raw_steps = job.get("steps")
    assert isinstance(raw_steps, list) and all(isinstance(step, dict) for step in raw_steps)
    return job, raw_steps


def _action_steps(steps_to_check: list[Step]) -> list[Step]:
    """Find steps that call the shared Whitaker installer action."""
    return [step for step in steps_to_check if calls(step, ACTION)]


def _development_cranelift_default() -> bool | None:
    """Read Cranelift selection from the Linux target's committed Cargo flags."""
    config_path = Path(__file__).resolve().parents[2] / ".cargo" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    target_config = config.get("target", {}).get(TARGET, {})
    rustflags = target_config.get("rustflags")
    if not isinstance(rustflags, list) or not all(isinstance(flag, str) for flag in rustflags):
        return None
    return "-Zcodegen-backend=cranelift" in rustflags


def _boolean_input(value: object) -> bool | None:
    """Read YAML booleans and quoted GitHub action boolean inputs."""
    if value is True or (isinstance(value, str) and value.casefold() == "true"):
        return True
    if value is False or (isinstance(value, str) and value.casefold() == "false"):
        return False
    return None


def _lint_job_action_violations(
    where: str, job_steps: list[Step], lint_indices: list[int], route_name: str
) -> list[str]:
    """Require one unconditional, correctly pinned action before the lint path."""
    violations: list[str] = []
    action_steps = _action_steps(job_steps)
    if len(action_steps) != 1:
        violations.append(f"{where} requires exactly one shared Whitaker action")
    for action_step in action_steps:
        if action_step.get("uses") != ACTION_USE:
            violations.append(f"{where} must pin the approved Whitaker action SHA")
        if "if" in action_step:
            violations.append(f"{where} Whitaker action must be unconditional")
        if continues_on_error(action_step):
            violations.append(f"{where} Whitaker action must not continue on error")

        inputs = action_step.get("with", {})
        if not isinstance(inputs, dict):
            violations.append(f"{where} Whitaker action inputs must be a mapping")
            continue
        for forbidden in sorted(FORBIDDEN_INPUTS.intersection(inputs)):
            violations.append(f"{where} Whitaker action must not set {forbidden}")
        selected = _boolean_input(inputs.get("cranelift", False))
        expected = _development_cranelift_default()
        if expected is None:
            violations.append("cannot determine the Linux development Cranelift default")
        elif selected is not expected:
            violations.append(
                "Whitaker action cranelift input must match the Linux development default"
            )

    for index in lint_indices:
        lint_step = job_steps[index]
        if "if" in lint_step:
            violations.append(f"{where} lint path must be unconditional")
        if continues_on_error(lint_step):
            violations.append(f"{where} lint path must not continue on error")
    if len(action_steps) == 1 and lint_indices:
        action_index = job_steps.index(action_steps[0])
        if action_index >= min(lint_indices):
            violations.append(f"{where} Whitaker action must run before {route_name}")
    return violations


def whitaker_provisioning_violations(documents: dict[str, Document]) -> list[str]:
    """Report CI routes that can omit or bypass the shared Whitaker action."""
    violations: list[str] = []
    document = documents.get(WORKFLOW)
    if document is None:
        return [f"{WORKFLOW} is missing"]

    workflow_jobs = jobs(WORKFLOW, document)
    job = workflow_jobs.get(JOB)
    if job is None:
        return [f"{WORKFLOW}:jobs.{JOB} is missing"]
    if "if" in job:
        violations.append(f"{WORKFLOW}:jobs.{JOB} must be unconditional")
    if continues_on_error(job):
        violations.append(f"{WORKFLOW}:jobs.{JOB} must not continue on error")

    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list) or not all(isinstance(step, dict) for step in raw_steps):
        return [*violations, f"{WORKFLOW}:jobs.{JOB} has malformed steps"]
    ci_steps = raw_steps
    lint_indices: list[int] = []
    for index, step in enumerate(ci_steps):
        command = step.get("run")
        if isinstance(command, str) and re.search(r"\bmake\s+lint\b", command):
            lint_indices.append(index)
            if command.strip() != "make lint":
                violations.append(f"{WORKFLOW}:jobs.{JOB} must run make lint directly")
            if "if" in step:
                violations.append(f"{WORKFLOW}:jobs.{JOB} make lint must be unconditional")
            if continues_on_error(step):
                violations.append(f"{WORKFLOW}:jobs.{JOB} make lint must not continue on error")
    if len(lint_indices) != 1:
        violations.append(f"{WORKFLOW}:jobs.{JOB} requires exactly one make lint step")
    violations.extend(
        _lint_job_action_violations(
            f"{WORKFLOW}:jobs.{JOB}", ci_steps, lint_indices, "make lint"
        )
    )

    for name, workflow in documents.items():
        for job_id, workflow_job in jobs(name, workflow).items():
            if name == WORKFLOW and job_id == JOB:
                continue
            if "uses" in workflow_job and "steps" not in workflow_job:
                continue
            job_steps, lint_path_indices, indeterminate = workflow_lint_steps(workflow_job)
            if not lint_path_indices:
                continue
            where = f"{name}:jobs.{job_id}"
            runner = linux_runner_status(workflow_job.get("runs-on"), workflow_job)
            if runner is None:
                violations.append(
                    f"{where} has a lint path but its Linux runner cannot be determined"
                )
                continue
            if not runner:
                continue
            if continues_on_error(workflow_job):
                violations.append(f"{where} must not continue on error")
            if indeterminate:
                violations.append(f"{where} has an indeterminate local Make lint path")
            violations.extend(
                _lint_job_action_violations(
                    where, job_steps, lint_path_indices, "the lint path"
                )
            )

    for name, workflow in documents.items():
        for step in steps(name, workflow):
            command = step.get("run")
            if isinstance(command, str) and DIRECT_SETUP.search(command):
                violations.append(f"{name} contains direct Whitaker or cargo-dylint provisioning")
    return violations


def test_ci_uses_the_approved_shared_whitaker_action_before_lint() -> None:
    assert whitaker_provisioning_violations(fresh_documents()) == []


@pytest.mark.parametrize(
    ("target", "job_id"),
    [
        pytest.param("lint", "future-direct-lint", id="new-direct-lint-job"),
        pytest.param("all", "future-composite-lint", id="new-composite-lint-job"),
    ],
)
def test_new_linux_lint_job_without_action_is_rejected(target: str, job_id: str) -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"][job_id] = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": f"make {target}"}],
    }

    assert whitaker_provisioning_violations(documents) == [
        f"ci.yml:jobs.{job_id} requires exactly one shared Whitaker action"
    ]


def test_new_linux_composite_lint_job_accepts_prior_action() -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"]["future-composite-lint"] = {
        "runs-on": "ubuntu-latest",
        "steps": [
            {"uses": ACTION_USE, "with": {"cranelift": "false"}},
            {"run": "make all"},
        ],
    }

    assert whitaker_provisioning_violations(documents) == []


def test_new_linux_lint_job_with_job_level_soft_fail_is_rejected() -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"]["future-soft-failing-lint"] = {
        "runs-on": "ubuntu-latest",
        "continue-on-error": True,
        "steps": [
            {"uses": ACTION_USE, "with": {"cranelift": "false"}},
            {"run": "make lint"},
        ],
    }

    assert whitaker_provisioning_violations(documents) == [
        "ci.yml:jobs.future-soft-failing-lint must not continue on error"
    ]


def test_indeterminate_runner_for_a_new_lint_job_fails_closed() -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"]["future-unknown-lint"] = {
        "runs-on": "${{ inputs.runner }}",
        "steps": [{"run": "make lint"}],
    }

    assert whitaker_provisioning_violations(documents) == [
        "ci.yml:jobs.future-unknown-lint has a lint path but its Linux runner "
        "cannot be determined"
    ]


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("remove", "requires exactly one shared Whitaker action", id="removed"),
        pytest.param("late", "must run before make lint", id="moved-after-lint"),
        pytest.param("conditional", "Whitaker action must be unconditional", id="conditional"),
        pytest.param("soft-fail", "Whitaker action must not continue on error", id="soft-failing"),
        pytest.param("wrong-pin", "must pin the approved Whitaker action SHA", id="wrong-pin"),
        pytest.param("suite-version", "must not set suite-version", id="suite-version"),
        pytest.param("allow-suite-pin", "must not set allow-suite-pin", id="allow-suite-pin"),
        pytest.param("installer-version", "must not set installer-version", id="installer-version"),
        pytest.param("direct-installer", "direct Whitaker or cargo-dylint", id="direct-installer"),
        pytest.param("cargo-dylint", "direct Whitaker or cargo-dylint", id="cargo-dylint-setup"),
        pytest.param("ignored-lint", "must run make lint directly", id="ignored-lint"),
        pytest.param("remove-lint", "requires exactly one make lint step", id="missing-lint"),
        pytest.param("conditional-lint", "make lint must be unconditional", id="conditional-lint"),
        pytest.param(
            "soft-fail-lint",
            "make lint must not continue on error",
            id="soft-failing-lint",
        ),
        pytest.param("cranelift-mismatch", "cranelift input must match", id="backend-mismatch"),
    ],
)
def test_whitaker_provisioning_mutations_are_rejected(
    mutation: str, expected: str
) -> None:
    documents = fresh_documents()
    _, ci_steps = _job_steps(documents)
    action = _action_steps(ci_steps)[0]
    action_index = ci_steps.index(action)
    lint_index = next(
        index for index, step in enumerate(ci_steps) if step.get("run") == "make lint"
    )

    if mutation == "remove":
        ci_steps.pop(action_index)
    elif mutation == "late":
        ci_steps.insert(lint_index + 1, ci_steps.pop(action_index))
    elif mutation == "conditional":
        action["if"] = "runner.os == 'Linux'"
    elif mutation == "soft-fail":
        action["continue-on-error"] = True
    elif mutation == "wrong-pin":
        action["uses"] = f"{ACTION}@v0.2.9"
    elif mutation in FORBIDDEN_INPUTS:
        action.setdefault("with", {})[mutation] = "0.2.9"
    elif mutation in {"direct-installer", "cargo-dylint"}:
        command = (
            "whitaker-installer --no-source-fallback"
            if mutation == "direct-installer"
            else "cargo binstall --no-confirm cargo-dylint"
        )
        documents[WORKFLOW]["jobs"][JOB]["steps"].append({"run": command})
    elif mutation == "ignored-lint":
        ci_steps[lint_index]["run"] = "make lint || true"
    elif mutation == "remove-lint":
        ci_steps.pop(lint_index)
    elif mutation == "conditional-lint":
        ci_steps[lint_index]["if"] = "runner.os == 'Linux'"
    elif mutation == "soft-fail-lint":
        ci_steps[lint_index]["continue-on-error"] = True
    else:
        action.setdefault("with", {})["cranelift"] = "true"

    violations = whitaker_provisioning_violations(documents)
    assert any(expected in violation for violation in violations), violations
