"""Test Make-path parsing and action-order policy boundaries."""

import typing as typ

import pytest
from whitaker_provisioning_rules import (
    ACTION_USE,
    _action_order_violations,
    _LintJobContext,
    _make_invocation_arguments,
    _MakeGraph,
    development_cranelift_default,
    lint_job_action_violations,
    make_lint_step_status,
    make_lint_targets,
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
    ("run", "graph_present", "expected"),
    [
        pytest.param("make lint", True, True, id="direct-lint"),
        pytest.param("make all", True, True, id="aggregate-through-graph"),
        pytest.param(
            "make -f other.mk build; make lint",
            True,
            None,
            id="unresolved-invocation-carries-forward",
        ),
        pytest.param("make unknown", True, None, id="unknown-target"),
        pytest.param("make", True, True, id="default-target"),
        pytest.param("make lint", False, None, id="missing-graph-make"),
        pytest.param("printf 'hello'", False, False, id="missing-graph-no-make"),
    ],
)
def test_make_lint_step_status_preserves_resolution_rules(
    run: str, graph_present: object, expected: object
) -> None:
    """Direct, graph-resolved, and unknown Make paths retain their statuses."""
    graph = _make_graph() if graph_present else None
    assert make_lint_step_status(run, graph) is expected, run


def test_make_graph_parser_consumes_injected_makefile_source() -> None:
    """Literal prerequisites are parsed without reading the repository file."""
    graph = make_lint_targets("lint:\nall: lint\n")

    assert graph is not None, "supplied Makefile text should produce a graph"
    assert graph.lint_targets == {"lint", "all"}, graph


@pytest.mark.parametrize(
    ("config", "expected"),
    [
        pytest.param(
            {"target": {'cfg(target_os = "linux")': {"rustflags": []}}},
            False,
            id="llvm-default",
        ),
        pytest.param(
            {
                "target": {
                    'cfg(target_os = "linux")': {
                        "rustflags": ["-Zcodegen-backend=cranelift"]
                    }
                }
            },
            True,
            id="cranelift-default",
        ),
        pytest.param({"target": []}, None, id="unknown-shape"),
        pytest.param({}, None, id="missing-target"),
    ],
)
def test_cranelift_selection_uses_parsed_configuration(
    config: object, expected: object
) -> None:
    """The pure rule accepts parsed configuration and preserves unknown state."""
    assert development_cranelift_default(config) is expected, config


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
        _LintJobContext(
            job_steps=job_steps,
            actions=actions,
            lint_indices=lint_indices,
            route_name="make lint",
        ),
    )
    expected_messages = [f"ci.yml Whitaker action {message}" for message in expected]
    assert violations == expected_messages, violations


def test_lint_job_violations_keep_cardinality_before_step_and_lint_errors() -> None:
    """Cardinality is first, followed by action and lint-step diagnostics."""
    first_action: Step = {"uses": ACTION_USE, "with": {"cranelift": "false"}}
    second_action: Step = {"uses": ACTION_USE, "with": {"cranelift": "false"}}
    lint_step: Step = {"run": "make lint", "if": False, "continue-on-error": True}

    violations = lint_job_action_violations(
        "ci.yml",
        _LintJobContext(
            job_steps=[first_action, second_action, lint_step],
            lint_indices=[2],
            route_name="make lint",
            expected_cranelift=False,
        ),
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
        "ci.yml",
        _LintJobContext(
            job_steps=[lint_step, action],
            lint_indices=[0],
            route_name="make lint",
            expected_cranelift=False,
        ),
    )

    assert violations == [
        "ci.yml Whitaker action must be unconditional",
        "ci.yml lint path must be unconditional",
        "ci.yml lint path must not continue on error",
        "ci.yml Whitaker action must run before make lint",
    ], violations
