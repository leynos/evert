"""Require the pull-request and main coverage jobs to share Rust setup."""

import typing as typ

import pytest
from coverage_toolchain_rules import SETUP_ACTION, toolchain_violations
from workflow_contract_support import Document, Step, calls, fresh_documents, jobs

PULL_REQUEST = "ci.yml"
PULL_REQUEST_JOB = "build-test"
PUBLISHER = "coverage-main.yml"
PUBLISHER_JOB = "coverage-upload"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage"


def _job_steps(name: str, document: Document, job_id: str) -> list[Step]:
    """Return a workflow job's mutable list of mapping steps."""
    raw_steps = jobs(name, document)[job_id].get("steps")
    assert isinstance(raw_steps, list), f"{name}:{job_id} steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), (
        f"{name}:{job_id} steps must be mappings"
    )
    return typ.cast("list[Step]", raw_steps)


def _coverage_step(name: str, document: Document, job_id: str) -> Step:
    """Return one named coverage action from its workflow job."""
    steps = _job_steps(name, document, job_id)
    return next(step for step in steps if calls(step, COVERAGE_ACTION))


def _violations(documents: dict[str, Document]) -> list[str]:
    """Compare the pull-request coverage setup with the main publisher."""
    publisher = documents[PUBLISHER]
    pull_request = documents[PULL_REQUEST]
    return toolchain_violations(
        documents,
        PUBLISHER,
        _coverage_step(PUBLISHER, publisher, PUBLISHER_JOB),
        [
            (
                PULL_REQUEST,
                pull_request,
                _coverage_step(PULL_REQUEST, pull_request, PULL_REQUEST_JOB),
            )
        ],
    )


def _setup(name: str, document: Document, job_id: str) -> Step:
    """Return the coverage job's pinned Rust setup step."""
    steps = _job_steps(name, document, job_id)
    return next(step for step in steps if calls(step, SETUP_ACTION))


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param("pin", "selection differs", id="pin"),
        pytest.param("toolchain", "selection differs", id="toolchain"),
        pytest.param("linker", "install pinned linker", id="linker"),
        pytest.param("guard", "unconditional and binding", id="guarded"),
        pytest.param("soft-failing", "unconditional and binding", id="soft-failing"),
        pytest.param("unpinned", "full-SHA pin", id="unpinned"),
        pytest.param("removed", "needs one setup-rust", id="removed"),
    ],
)
def test_pull_request_setup_matches_the_main_publisher(
    change: str, expected: str
) -> None:
    """Each drift in the pull-request setup step is reported."""
    documents = fresh_documents()
    pull_request = documents[PULL_REQUEST]
    steps = _job_steps(PULL_REQUEST, pull_request, PULL_REQUEST_JOB)
    setup = _setup(PULL_REQUEST, pull_request, PULL_REQUEST_JOB)
    match change:
        case "pin":
            setup["uses"] = str(setup["uses"])[:-1] + "0"
        case "toolchain":
            typ.cast("dict[str, str]", setup["with"])["toolchain"] = "stable"
        case "linker":
            typ.cast("dict[str, str]", setup["with"])["install-mold"] = "false"
        case "guard":
            setup["if"] = "false"
        case "soft-failing":
            setup["continue-on-error"] = True
        case "unpinned":
            setup["uses"] = str(setup["uses"]).split("@", maxsplit=1)[0] + "@main"
        case _:
            steps.remove(setup)

    violations = _violations(documents)
    assert any(expected in violation for violation in violations), violations


def test_main_publisher_cannot_lose_its_setup() -> None:
    """Removing the publisher's setup step is reported."""
    documents = fresh_documents()
    publisher = documents[PUBLISHER]
    steps = _job_steps(PUBLISHER, publisher, PUBLISHER_JOB)
    steps.remove(_setup(PUBLISHER, publisher, PUBLISHER_JOB))

    violations = _violations(documents)
    assert any("needs one setup-rust" in violation for violation in violations), (
        violations
    )


@pytest.mark.parametrize(
    ("workflow", "job_id"),
    [(PULL_REQUEST, PULL_REQUEST_JOB), (PUBLISHER, PUBLISHER_JOB)],
)
def test_rust_setup_precedes_build_tool_installation(
    workflow: str, job_id: str
) -> None:
    """Moving setup-rust after the installer is reported, and only that."""
    documents = fresh_documents()
    document = documents[workflow]
    steps = _job_steps(workflow, document, job_id)
    setup = _setup(workflow, document, job_id)
    installer = next(
        step for step in steps if step.get("run") == "make install-build-tools"
    )
    steps.remove(setup)
    steps.insert(steps.index(installer) + 1, setup)

    violations = toolchain_violations(
        documents,
        PUBLISHER,
        _coverage_step(PUBLISHER, documents[PUBLISHER], PUBLISHER_JOB),
        [
            (
                PULL_REQUEST,
                documents[PULL_REQUEST],
                _coverage_step(PULL_REQUEST, documents[PULL_REQUEST], PULL_REQUEST_JOB),
            )
        ],
    )
    expected = f"{workflow} setup-rust must precede build-tool installation"
    assert violations == [expected], violations
