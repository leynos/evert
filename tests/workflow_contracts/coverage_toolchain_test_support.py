"""Share workflow accessors for coverage toolchain contract tests."""

import typing as typ

from coverage_toolchain_rules import toolchain_violations
from workflow_contract_support import Document, Step, calls, jobs

PULL_REQUEST = "ci.yml"
PULL_REQUEST_JOB = "build-test"
PUBLISHER = "coverage-main.yml"
PUBLISHER_JOB = "coverage-upload"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage"


def _job_steps(name: str, document: Document, job_id: str) -> list[Step]:
    """Return a named coverage job's mutable, typed steps."""
    raw_steps = jobs(name, document)[job_id].get("steps")
    assert isinstance(raw_steps, list), f"{name}:{job_id} steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), (
        f"{name}:{job_id} steps must be mappings"
    )
    return typ.cast("list[Step]", raw_steps)


def _coverage_step(name: str, document: Document, job_id: str) -> Step:
    """Return one named coverage action from its workflow job."""
    return next(
        step
        for step in _job_steps(name, document, job_id)
        if calls(step, COVERAGE_ACTION)
    )


def _violations(documents: dict[str, Document]) -> list[str]:
    """Compare pull-request coverage setup with the main publisher."""
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
