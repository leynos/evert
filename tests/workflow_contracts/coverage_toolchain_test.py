"""Require the pull-request and main coverage jobs to share Rust setup."""

from __future__ import annotations

import typing as typ

import pytest

from coverage_toolchain_rules import SETUP_ACTION, toolchain_violations
from workflow_contract_support import Document, Step, calls, fresh_documents, jobs

PULL_REQUEST = "ci.yml"
PULL_REQUEST_JOB = "build-test"
PUBLISHER = "coverage-main.yml"
PUBLISHER_JOB = "coverage-upload"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage"


def _coverage_step(name: str, document: Document, job_id: str) -> Step:
    """Return one named coverage action from its workflow job."""
    raw_steps = jobs(name, document)[job_id].get("steps")
    assert isinstance(raw_steps, list) and all(isinstance(step, dict) for step in raw_steps)
    return next(step for step in raw_steps if calls(typ.cast(Step, step), COVERAGE_ACTION))


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
    raw_steps = jobs(name, document)[job_id].get("steps")
    assert isinstance(raw_steps, list) and all(isinstance(step, dict) for step in raw_steps)
    return next(step for step in raw_steps if calls(typ.cast(Step, step), SETUP_ACTION))


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
def test_pull_request_setup_matches_the_main_publisher(change: str, expected: str) -> None:
    documents = fresh_documents()
    pull_request = documents[PULL_REQUEST]
    steps = jobs(PULL_REQUEST, pull_request)[PULL_REQUEST_JOB]["steps"]
    assert isinstance(steps, list)
    setup = _setup(PULL_REQUEST, pull_request, PULL_REQUEST_JOB)
    if change == "pin":
        setup["uses"] = str(setup["uses"])[:-1] + "0"
    elif change == "toolchain":
        typ.cast("dict[str, str]", setup["with"])["toolchain"] = "stable"
    elif change == "linker":
        typ.cast("dict[str, str]", setup["with"])["install-mold"] = "false"
    elif change == "guard":
        setup["if"] = "false"
    elif change == "soft-failing":
        setup["continue-on-error"] = True
    elif change == "unpinned":
        setup["uses"] = str(setup["uses"]).split("@")[0] + "@main"
    else:
        steps.remove(setup)

    violations = _violations(documents)
    assert any(expected in violation for violation in violations), violations


def test_main_publisher_cannot_lose_its_setup() -> None:
    documents = fresh_documents()
    publisher = documents[PUBLISHER]
    steps = jobs(PUBLISHER, publisher)[PUBLISHER_JOB]["steps"]
    assert isinstance(steps, list)
    steps.remove(_setup(PUBLISHER, publisher, PUBLISHER_JOB))

    violations = _violations(documents)
    assert any("needs one setup-rust" in violation for violation in violations), violations


@pytest.mark.parametrize(("workflow", "job_id"), [(PULL_REQUEST, PULL_REQUEST_JOB), (PUBLISHER, PUBLISHER_JOB)])
def test_rust_setup_precedes_build_tool_installation(workflow: str, job_id: str) -> None:
    documents = fresh_documents()
    document = documents[workflow]
    steps = jobs(workflow, document)[job_id]["steps"]
    assert isinstance(steps, list)
    setup = _setup(workflow, document, job_id)
    installer = next(step for step in steps if step.get("run") == "make install-build-tools")
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
    assert violations == [expected]
