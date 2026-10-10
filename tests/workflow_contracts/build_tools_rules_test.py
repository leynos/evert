"""Test build-tool policy helpers at their validation boundaries."""

import build_tools_rules as rules
import pytest
from build_tools_rules import (
    _is_suite_step,
    _mutation_violations,
    _step_installer_violations,
    _step_wrapper_violations,
    _unresolved_reusable_problem,
)
from workflow_contract_support import Document, WorkflowError

WHERE = "workflow.yml:jobs.test"
INSTALL_COMMAND = "make install-build-tools"
INSTALL_ORDER_DIAGNOSTIC = (
    f"{WHERE} setup-commands must run one unconditional "
    "make install-build-tools command"
)


def _valid_setup() -> dict[str, object]:
    """Return a fresh setup-rust step accepted by the installer policy."""
    return {
        "uses": rules.SETUP_RUST_REF,
        "with": {"install-mold": "true", "mold-version": rules.LINKER_VERSION},
    }


@pytest.mark.parametrize(
    ("steps", "suite_index", "expected"),
    [
        pytest.param(
            [_valid_setup(), {"run": "cargo test"}],
            1,
            [],
            id="valid-before-suite",
        ),
        pytest.param(
            [{"run": "cargo test"}, _valid_setup()],
            0,
            [f"{WHERE} the pinned linker installer must run before the suite"],
            id="valid-only-after-suite",
        ),
        pytest.param(
            [{"run": "cargo test"}],
            0,
            [f"{WHERE} no pinned linker installer occurs before the suite"],
            id="no-candidates",
        ),
        pytest.param(
            [
                {
                    "uses": f"{rules.SETUP_RUST}@main",
                    "with": {"install-mold": "false"},
                },
                {"uses": "another", "with": {"install-mold": "false"}},
                {"uses": f"{rules.SETUP_RUST}@main", "with": None},
                {"run": "cargo test"},
            ],
            2,
            [
                f"{WHERE} must use the approved pinned setup-rust action",
                f"{WHERE} must enable setup-rust install-mold",
                f"{WHERE} must use the pinned setup-rust linker installer",
            ],
            id="several-invalid-candidates-deduplicate-problems",
        ),
    ],
)
def test_installer_candidates_keep_validity_and_diagnostic_order(
    steps: list[dict[str, object]], suite_index: int, expected: list[str]
) -> None:
    """Installer candidates retain valid-before and first-seen message rules."""
    found = _step_installer_violations(WHERE, steps, suite_index)
    assert found == expected, found


def test_setup_rust_problems_are_computed_once_for_each_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Candidate validation is memoized even when an early candidate is valid."""
    candidates: list[dict[str, object]] = [
        _valid_setup(),
        {"uses": f"{rules.SETUP_RUST}@main"},
    ]
    visited: list[int] = []

    def record(step: dict[str, object]) -> list[str]:
        """Record each candidate and model one valid and one invalid result."""
        visited.append(id(step))
        return [] if step is candidates[0] else ["invalid candidate"]

    monkeypatch.setattr(rules, "_setup_rust_problems", record)
    suite_step: dict[str, object] = {"run": "cargo test"}
    candidate_steps: list[dict[str, object]] = [*candidates, suite_step]
    assert not _step_installer_violations(WHERE, candidate_steps, 2), (
        "valid candidate before the suite should satisfy the installer rule"
    )
    assert visited == [id(step) for step in candidates], visited


@pytest.mark.parametrize(
    "job",
    [
        pytest.param({}, id="missing-with"),
        pytest.param({"with": None}, id="null-with"),
        pytest.param({"with": "bad"}, id="non-mapping-with"),
        pytest.param({"with": {"setup-commands": 1}}, id="non-string-commands"),
    ],
)
def test_mutation_requires_a_mapping_and_string_setup_command(
    job: dict[str, object],
) -> None:
    """Malformed reusable-workflow inputs keep the existing early diagnostic."""
    found = _mutation_violations(WHERE, job)
    assert found == [
        f"{WHERE} must pass make install-build-tools before mutation tests"
    ], found


@pytest.mark.parametrize(
    ("commands", "expected"),
    [
        pytest.param(INSTALL_COMMAND, [], id="one-install"),
        pytest.param(
            "",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="zero-installs",
        ),
        pytest.param(
            f"{INSTALL_COMMAND}\n{INSTALL_COMMAND}",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="two-installs",
        ),
        pytest.param(
            f"# {INSTALL_COMMAND}",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="comment-ignored",
        ),
        pytest.param(
            f"set +e\n{INSTALL_COMMAND}",
            [f"{WHERE} must preserve the install-build-tools exit status"],
            id="set-plus-e-before-install",
        ),
        pytest.param(
            f"if test -n x; then\n{INSTALL_COMMAND}\nfi",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="if-block",
        ),
        pytest.param(
            f"case x in\nx)\n{INSTALL_COMMAND}\n;;\nesac",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="case-block",
        ),
        pytest.param(
            f"while test -n x; do\n{INSTALL_COMMAND}\ndone",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="while-block",
        ),
        pytest.param(
            f"until test -n x; do\n{INSTALL_COMMAND}\ndone",
            [INSTALL_ORDER_DIAGNOSTIC],
            id="until-block",
        ),
    ],
)
def test_mutation_install_validation_preserves_exact_line_rules(
    commands: str, expected: list[str]
) -> None:
    """Only one uncommented exact command outside control blocks is accepted."""
    violations = _mutation_violations(
        WHERE, {"with": {"setup-commands": commands}}
    )
    assert violations == expected, violations


def test_mutation_continue_on_error_is_reported_before_install_errors() -> None:
    """The soft-failure diagnostic remains first in aggregate output."""
    violations = _mutation_violations(
        WHERE,
        {"continue-on-error": True, "with": {"setup-commands": ""}},
    )

    assert violations == [
        f"{WHERE} must not soften mutation-suite failures",
        INSTALL_ORDER_DIAGNOSTIC,
    ], violations


@pytest.mark.parametrize(
    ("steps", "suite_index", "expected"),
    [
        pytest.param(
            [{"run": "cargo test"}],
            0,
            ["no unconditional make install-build-tools step occurs before the suite"],
            id="no-candidate",
        ),
        pytest.param(
            [{"run": INSTALL_COMMAND}, {"run": "cargo test"}],
            1,
            [],
            id="valid-candidate",
        ),
        pytest.param(
            [{"run": INSTALL_COMMAND, "if": False}, {"run": "cargo test"}],
            1,
            ["make install-build-tools step must not have an if condition"],
            id="if-key-even-false",
        ),
        pytest.param(
            [
                {"run": INSTALL_COMMAND, "continue-on-error": True},
                {"run": "cargo test"},
            ],
            1,
            ["make install-build-tools step must not continue on error"],
            id="continue-on-error",
        ),
        pytest.param(
            [{"run": "cargo test"}, {"run": INSTALL_COMMAND}],
            0,
            ["make install-build-tools must run before the suite"],
            id="after-suite",
        ),
        pytest.param(
            [
                {"run": INSTALL_COMMAND, "if": False, "continue-on-error": True},
                {"run": "cargo test"},
            ],
            1,
            [
                "make install-build-tools step must not have an if condition",
                "make install-build-tools step must not continue on error",
            ],
            id="combined-candidate-problems",
        ),
    ],
)
def test_wrapper_step_violations_keep_candidate_policy(
    steps: list[dict[str, object]], suite_index: int, expected: list[str]
) -> None:
    """Wrapper candidates retain their filter, early return and message order."""
    found = _step_wrapper_violations(WHERE, steps, suite_index)
    assert found == [f"{WHERE} {message}" for message in expected], found


@pytest.mark.parametrize(
    ("step", "message"),
    [
        pytest.param(
            {"uses": 7}, "cannot read step action reference 7", id="non-string-uses"
        ),
        pytest.param(
            {"uses": None},
            "cannot read step action reference None",
            id="null-uses",
        ),
        pytest.param(
            {"run": None}, "cannot read step run command None", id="non-string-run"
        ),
        pytest.param({"run": 4}, "cannot read step run command 4", id="integer-run"),
    ],
)
def test_suite_step_rejects_present_non_string_values(
    step: dict[str, object], message: str
) -> None:
    """Present non-text step values raise the existing shape diagnostics."""
    with pytest.raises(WorkflowError, match=message):
        _is_suite_step(step)


@pytest.mark.parametrize(
    ("step", "expected"),
    [
        pytest.param(
            {"uses": "local/generate-coverage@ref"}, True, id="coverage-action"
        ),
        pytest.param({"run": "# make test\necho done"}, False, id="commented-command"),
        pytest.param(
            {"run": "echo start\nmake test\necho finish"}, True, id="multiline-script"
        ),
        pytest.param({}, False, id="empty-step"),
    ],
)
def test_suite_step_detection_keeps_action_comment_and_script_rules(
    step: dict[str, object], expected: object
) -> None:
    """Coverage actions and uncommented commands are detected in script order."""
    assert _is_suite_step(step) is expected, step


@pytest.mark.parametrize(
    ("uses", "documents", "expected"),
    [
        pytest.param(
            "leynos/shared-actions/.github/workflows/dependabot-automerge.yml@main",
            {},
            None,
            id="dependabot-allow-list",
        ),
        pytest.param(
            "/".join((".", ".github", "workflows", "known.yml")) + "@main",
            {"known.yml": {}},
            "calls a local workflow at an uninspectable external ref",
            id="local-ref",
        ),
        pytest.param(
            "/".join((".", ".github", "workflows", "missing.yml")),
            {},
            "calls an unreadable local workflow",
            id="unreadable-local",
        ),
        pytest.param(
            "/".join((".", ".github", "workflows", "known.yml")),
            {"known.yml": {}},
            "calls a local reusable workflow whose suite paths are not checked",
            id="known-local",
        ),
        pytest.param(
            "owner/repo/.github/workflows/test.yml@main",
            {},
            (
                "calls an external reusable workflow whose suite runner "
                "cannot be inspected"
            ),
            id="external-workflow",
        ),
    ],
)
def test_reusable_workflow_dispositions_keep_allow_list_and_diagnostics(
    uses: str, documents: dict[str, Document], expected: str | None
) -> None:
    """Local, external and allow-listed reusable calls keep their decisions."""
    result = _unresolved_reusable_problem({"uses": uses}, documents)
    assert result == expected, result
