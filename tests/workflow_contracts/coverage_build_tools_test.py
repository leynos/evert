"""Hold the protected coverage job's linker and build-tool ordering."""

import pytest
from build_tools_rules import build_tool_violations
from workflow_contract_support import Workflow, calls, fresh_documents, jobs

WORKFLOW = "coverage-main.yml"
JOB = "coverage-upload"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage"


def _coverage_job_steps(documents: Workflow) -> list[dict[str, object]]:
    """Return the main coverage job's mutable steps."""
    job = jobs(WORKFLOW, documents[WORKFLOW])[JOB]
    raw_steps = job.get("steps")
    assert isinstance(raw_steps, list), "coverage job steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), "steps are mappings"
    return raw_steps


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        pytest.param(
            "remove", "no unconditional make install-build-tools", id="removed"
        ),
        pytest.param("after coverage", "must run before the suite", id="late"),
        pytest.param("guarded", "must not have an if condition", id="conditional"),
        pytest.param("soft failing", "must not continue on error", id="soft-failing"),
        pytest.param(
            "different command",
            "no unconditional make install-build-tools",
            id="wrong-command",
        ),
    ],
)
def test_main_coverage_installs_build_tools_before_its_suite(
    change: str, expected: str
) -> None:
    """The LLVM coverage route still needs Make's configured test tools."""
    documents = fresh_documents()
    steps = _coverage_job_steps(documents)
    installer = next(
        step for step in steps if step.get("run") == "make install-build-tools"
    )
    coverage = next(step for step in steps if calls(step, COVERAGE_ACTION))
    match change:
        case "remove":
            steps.remove(installer)
        case "after coverage":
            steps.remove(installer)
            steps.insert(steps.index(coverage) + 1, installer)
        case "guarded":
            installer["if"] = "runner.os == 'Linux'"
        case "soft failing":
            installer["continue-on-error"] = True
        case _:
            installer["run"] = "make check-build-tools"

    violations = build_tool_violations(documents)
    assert any(expected in violation for violation in violations), violations
