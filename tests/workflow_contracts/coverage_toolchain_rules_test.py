"""Test the extracted coverage setup validation boundaries."""

import typing as typ

import pytest
from coverage_toolchain_rules import (
    SETUP_ACTION,
    _setup,
    _setup_order_problems,
)
from coverage_toolchain_test_support import (
    COVERAGE_ACTION,
    PUBLISHER,
    PULL_REQUEST,
    PULL_REQUEST_JOB,
    _job_steps,
    _violations,
)
from workflow_contract_support import Document, Step, calls, fresh_documents

PINNED_SETUP = f"{SETUP_ACTION}@{'a' * 40}"
MISSING = object()


def _rule_setup_result(held: list[Step]) -> tuple[Step | None, list[str]]:
    """Run the private setup validator for one synthetic coverage job."""
    coverage = next(step for step in held if calls(step, COVERAGE_ACTION))
    document: Document = {"jobs": {"coverage": {"steps": held}}}
    return _setup("synthetic.yml", document, coverage)


def _valid_setup_step() -> Step:
    """Return a fresh setup action with a full-SHA pin and pinned linker input."""
    return {"uses": PINNED_SETUP, "with": {"install-mold": "true"}}


def _coverage_action_step() -> Step:
    """Return a fresh coverage action marker for synthetic jobs."""
    return {"uses": f"{COVERAGE_ACTION}@{'b' * 40}"}


def test_setup_accepts_the_required_order_and_returns_the_original_step() -> None:
    """Setup, exact installer, and coverage in order satisfy the rule."""
    setup = _valid_setup_step()
    returned, problems = _rule_setup_result([
        setup,
        {"run": "make install-build-tools"},
        _coverage_action_step(),
    ])

    assert returned is setup, "setup identity was not preserved"
    assert not problems, f"valid setup order produced diagnostics: {problems}"


@pytest.mark.parametrize(
    ("setups", "expected"),
    [
        pytest.param(
            [], ["synthetic.yml coverage needs one setup-rust step"], id="missing-setup"
        ),
        pytest.param(
            [
                {"uses": f"{SETUP_ACTION}@main", "if": False, "with": None},
                {"uses": f"{SETUP_ACTION}@main", "if": False, "with": None},
            ],
            ["synthetic.yml coverage needs one setup-rust step"],
            id="duplicate-setup",
        ),
    ],
)
def test_setup_cardinality_stops_downstream_validation(
    setups: list[Step], expected: list[str]
) -> None:
    """Zero or multiple setup candidates return only the cardinality error."""
    returned, problems = _rule_setup_result([*setups, _coverage_action_step()])

    assert returned is None, "cardinality failure returned a setup step"
    assert problems == expected, problems


@pytest.mark.parametrize(
    ("installers", "expected"),
    [
        pytest.param(
            [], "needs one `make install-build-tools` step", id="missing-installer"
        ),
        pytest.param(
            [
                {"run": "make install-build-tools"},
                {"run": "make install-build-tools"},
            ],
            "needs one `make install-build-tools` step",
            id="duplicate-installers",
        ),
    ],
)
def test_setup_requires_exactly_one_installer(
    installers: list[Step], expected: str
) -> None:
    """Missing or duplicate exact install commands are reported."""
    _, problems = _rule_setup_result([
        _valid_setup_step(),
        *installers,
        _coverage_action_step(),
    ])

    assert problems == [f"synthetic.yml coverage {expected}"], problems


@pytest.mark.parametrize(
    ("held", "expected"),
    [
        pytest.param(
            [
                _coverage_action_step(),
                _valid_setup_step(),
                {"run": "make install-build-tools"},
            ],
            ["synthetic.yml setup-rust must precede coverage"],
            id="setup-after-coverage",
        ),
        pytest.param(
            [
                {"run": "make install-build-tools"},
                _valid_setup_step(),
                _coverage_action_step(),
            ],
            ["synthetic.yml setup-rust must precede build-tool installation"],
            id="setup-after-installation",
        ),
        pytest.param(
            [
                {"run": "make install-build-tools"},
                _coverage_action_step(),
                {
                    "uses": f"{SETUP_ACTION}@main",
                    "if": False,
                    "continue-on-error": "${{ false }}",
                    "with": None,
                },
            ],
            [
                "synthetic.yml setup-rust must precede coverage",
                "synthetic.yml setup-rust must precede build-tool installation",
                "synthetic.yml setup-rust must be unconditional and binding",
                "synthetic.yml setup-rust must use a full-SHA pin",
                "synthetic.yml setup-rust must install pinned linker",
            ],
            id="combined-order-and-setup-problems",
        ),
    ],
)
def test_setup_order_and_step_diagnostics_keep_their_order(
    held: list[Step], expected: list[str]
) -> None:
    """Ordering errors precede accumulated validation errors."""
    _, problems = _rule_setup_result(held)
    assert problems == expected, problems


@pytest.mark.parametrize(
    ("updates", "expected"),
    [
        pytest.param({}, [], id="missing-continue-on-error-is-valid"),
        pytest.param({"continue-on-error": False}, [], id="literal-false-is-valid"),
        pytest.param(
            {"continue-on-error": True},
            ["must be unconditional and binding"],
            id="true-continue-on-error",
        ),
        pytest.param(
            {"continue-on-error": "false"},
            ["must be unconditional and binding"],
            id="string-continue-on-error",
        ),
        pytest.param(
            {"continue-on-error": "${{ always() }}"},
            ["must be unconditional and binding"],
            id="expression-continue-on-error",
        ),
        pytest.param(
            {"if": False},
            ["must be unconditional and binding"],
            id="if-false-is-still-conditional",
        ),
    ],
)
def test_setup_condition_and_soft_failure_semantics(
    updates: dict[str, object], expected: list[str]
) -> None:
    """Any if key is conditional; only absent or literal false is binding."""
    setup = _valid_setup_step()
    setup.update(updates)
    _, problems = _rule_setup_result([
        setup,
        {"run": "make install-build-tools"},
        _coverage_action_step(),
    ])

    expected_messages = [f"synthetic.yml setup-rust {message}" for message in expected]
    assert problems == expected_messages, problems


@pytest.mark.parametrize(
    ("uses", "expected"),
    [
        pytest.param(PINNED_SETUP, [], id="full-sha-pin"),
        pytest.param(
            f"{SETUP_ACTION}@main", ["must use a full-SHA pin"], id="mutable-ref"
        ),
        pytest.param(
            f"{SETUP_ACTION}@abcdef", ["must use a full-SHA pin"], id="short-ref"
        ),
    ],
)
def test_setup_requires_a_full_sha_pin(uses: str, expected: list[str]) -> None:
    """A full-length hexadecimal ref is accepted without fixing its value."""
    setup = _valid_setup_step()
    setup["uses"] = uses
    _, problems = _rule_setup_result([
        setup,
        {"run": "make install-build-tools"},
        _coverage_action_step(),
    ])

    expected_messages = [f"synthetic.yml setup-rust {item}" for item in expected]
    assert problems == expected_messages, problems


@pytest.mark.parametrize(
    "inputs",
    [
        pytest.param(MISSING, id="missing-with"),
        pytest.param(None, id="null-with"),
        pytest.param("not a mapping", id="non-mapping-with"),
        pytest.param({}, id="missing-install-mold"),
        pytest.param({"install-mold": "false"}, id="false-string-input"),
        pytest.param({"install-mold": False}, id="false-boolean-input"),
        pytest.param({"install-mold": True}, id="true-boolean-input"),
    ],
)
def test_setup_requires_the_literal_linker_input(inputs: object) -> None:
    """Only the string value ``true`` selects pinned mould installation."""
    setup = _valid_setup_step()
    if inputs is MISSING:
        setup.pop("with")
    else:
        setup["with"] = inputs
    _, problems = _rule_setup_result([
        setup,
        {"run": "make install-build-tools"},
        _coverage_action_step(),
    ])

    assert problems == ["synthetic.yml setup-rust must install pinned linker"], problems


def test_setup_install_command_matching_remains_exact() -> None:
    """Extra arguments do not count as the exact installer invocation."""
    _, problems = _rule_setup_result([
        _valid_setup_step(),
        {"run": "make install-build-tools --offline"},
        _coverage_action_step(),
    ])

    assert problems == [
        "synthetic.yml coverage needs one `make install-build-tools` step"
    ], problems


def test_setup_order_checks_keep_list_index_equality_semantics() -> None:
    """The order helper retains list.index's equality-based lookup."""
    setup = _valid_setup_step()
    equal_setup = dict(setup)
    installer: Step = {"run": "make install-build-tools"}
    coverage = _coverage_action_step()
    held: list[Step] = [equal_setup, installer, setup, coverage]

    problems = _setup_order_problems("synthetic.yml", held, setup, coverage)

    assert not problems, problems


def test_public_toolchain_rule_compares_the_whole_input_mapping() -> None:
    """A lane-only input is action-selection drift, even when known inputs agree."""
    documents = fresh_documents()
    lane_setup = next(
        step
        for step in _job_steps(PULL_REQUEST, documents[PULL_REQUEST], PULL_REQUEST_JOB)
        if calls(step, SETUP_ACTION)
    )
    typ.cast("dict[str, object]", lane_setup["with"])["extra"] = "value"

    violations = _violations(documents)

    assert violations == [
        f"{PULL_REQUEST} setup-rust toolchain selection differs from {PUBLISHER}"
    ], violations
