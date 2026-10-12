"""Test named mutations of the shared Whitaker provisioning route."""

import dataclasses
import typing as typ

import pytest
from whitaker_provisioning_rules import (
    ACTION,
    FORBIDDEN_INPUTS,
    action_steps,
)
from whitaker_provisioning_test import whitaker_provisioning_violations
from workflow_contract_support import Document, Step, fresh_documents, jobs, mapping_at

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
        scenario.action.setdefault("with", {})
        mapping_at(scenario.action, "with")[name] = value

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
