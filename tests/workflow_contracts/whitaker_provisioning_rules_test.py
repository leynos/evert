"""Test Make-path parsing and action-order policy boundaries."""

import typing as typ

import pytest
import whitaker_provisioning_rules as rules
from whitaker_provisioning_rules import (
    ACTION_USE,
    _action_order_violations,
    _ActionOrderContext,
    _make_invocation_arguments,
    _MakeGraph,
    lint_job_action_violations,
    make_lint_step_status,
)

if typ.TYPE_CHECKING:
    from workflow_contract_support import Step


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        pytest.param("printf 'nothing'", [], id="no-make"),
        pytest.param("make lint", [["lint"]], id="one-make"),
        pytest.param(
            "make lint && make fmt; make typecheck | make doc",
            [["lint"], ["fmt"], ["typecheck"], ["doc"]],
            id="separated-makes",
        ),
        pytest.param(
            "make lint \\\n typecheck", [["lint", "typecheck"]], id="continued-command"
        ),
        pytest.param(
            "make -C . JOBS=4 lint -j2",
            [["-C", ".", "JOBS=4", "lint", "-j2"]],
            id="options-and-assignments",
        ),
        pytest.param("", [], id="empty-run"),
    ],
)
def test_make_invocation_arguments_extracts_each_call(
    run: str, expected: list[list[str]]
) -> None:
    """Make invocations are split at shell separators after continuation folding."""
    assert _make_invocation_arguments(run) == expected, run


def _make_graph() -> _MakeGraph:
    """Build a small local graph with lint, aggregate, and uncertain targets."""
    return _MakeGraph(
        lint_targets={"lint", "all"},
        uncertain_targets={"uncertain"},
        graph={"lint": set(), "all": {"lint"}, "build": set()},
        default_target="all",
    )


@pytest.mark.parametrize(
    ("run", "graph", "expected"),
    [
        pytest.param("make lint", "present", True, id="direct-lint"),
        pytest.param("make all", "present", True, id="aggregate-through-graph"),
        pytest.param(
            "make -f other.mk build; make lint",
            "present",
            None,
            id="unresolved-invocation-carries-forward",
        ),
        pytest.param("make unknown", "present", None, id="unknown-target"),
        pytest.param("make", "present", True, id="default-target"),
        pytest.param("make lint", "missing", None, id="missing-graph-make"),
        pytest.param("printf 'hello'", "missing", False, id="missing-graph-no-make"),
    ],
)
def test_make_lint_step_status_preserves_resolution_rules(
    monkeypatch: pytest.MonkeyPatch, run: str, graph: str, expected: object
) -> None:
    """Direct, graph-resolved, and unknown Make paths retain their statuses."""
    resolved = _make_graph() if graph == "present" else None

    def provide_graph() -> _MakeGraph | None:
        """Return the selected synthetic graph."""
        return resolved

    monkeypatch.setattr(rules, "_make_lint_targets", provide_graph)
    assert make_lint_step_status(run) is expected, run


@pytest.mark.parametrize(
    ("action_position", "action_count", "lint_indices", "expected"),
    [
        pytest.param(0, 0, [0], [], id="no-actions"),
        pytest.param(1, 2, [0], [], id="two-actions"),
        pytest.param(0, 1, [], [], id="no-lint-indices"),
        pytest.param(0, 1, [1], [], id="action-before-lint"),
        pytest.param(
            0, 1, [0], ["must run before make lint"], id="action-at-lint-index"
        ),
        pytest.param(1, 1, [0], ["must run before make lint"], id="action-after-lint"),
    ],
)
def test_action_order_violations_require_one_prior_action(
    action_position: int,
    action_count: int,
    lint_indices: list[int],
    expected: list[str],
) -> None:
    """Only one action and at least one lint index activate the order check."""
    job_steps: list[Step] = [{} for _ in range(max(2, action_count))]
    actions = [job_steps[index] for index in range(action_count)]
    if action_count == 1:
        actions = [job_steps[action_position]]
    violations = _action_order_violations(
        "ci.yml",
        _ActionOrderContext(job_steps, actions, lint_indices, "make lint"),
    )
    expected_messages = [f"ci.yml Whitaker action {message}" for message in expected]
    assert violations == expected_messages, violations


def test_lint_job_violations_keep_cardinality_before_step_and_lint_errors() -> None:
    """Cardinality is first, followed by action and lint-step diagnostics."""
    first_action: Step = {"uses": ACTION_USE, "with": {"cranelift": "false"}}
    second_action: Step = {"uses": ACTION_USE, "with": {"cranelift": "false"}}
    lint_step: Step = {"run": "make lint", "if": False, "continue-on-error": True}

    violations = lint_job_action_violations(
        "ci.yml", [first_action, second_action, lint_step], [2], "make lint"
    )

    assert violations == [
        "ci.yml requires exactly one shared Whitaker action",
        "ci.yml lint path must be unconditional",
        "ci.yml lint path must not continue on error",
    ], violations


def test_lint_job_violations_keep_action_lint_and_order_diagnostic_order() -> None:
    """Action checks precede lint checks, which precede the final order check."""
    lint_step: Step = {"run": "make lint", "if": False, "continue-on-error": True}
    action: Step = {"uses": ACTION_USE, "if": False, "with": {"cranelift": "false"}}

    violations = lint_job_action_violations(
        "ci.yml", [lint_step, action], [0], "make lint"
    )

    assert violations == [
        "ci.yml Whitaker action must be unconditional",
        "ci.yml lint path must be unconditional",
        "ci.yml lint path must not continue on error",
        "ci.yml Whitaker action must run before make lint",
    ], violations
