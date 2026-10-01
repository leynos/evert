"""Keep the main coverage job isolated from development compiler flags."""

import re

import pytest
from workflow_contract_support import (
    Workflow,
    calls,
    continues_on_error,
    fresh_documents,
    jobs,
    mapping_at,
)

WORKFLOW = "coverage-main.yml"
JOB = "coverage-upload"
COVERAGE_ACTION = "leynos/shared-actions/.github/actions/generate-coverage"
CHECK_NAME = "Check coverage compiler environment"
ENCODED_FLAGS = "CARGO_ENCODED_RUSTFLAGS"
LLVM_RUSTFLAGS = "-C link-arg=-fuse-ld=lld"
ENCODED_FLAGS_GUARD = re.compile(
    r'(?ms)^[ \t]*if \[ "\$\{CARGO_ENCODED_RUSTFLAGS\+x\}" \]; then\n'
    r".*?^[ \t]*exit 1[ \t]*\n^[ \t]*fi[ \t]*$"
)


def _coverage_steps(documents: Workflow) -> list[dict[str, object]]:
    """Return the main coverage job's mutable steps."""
    job = jobs(WORKFLOW, documents[WORKFLOW])[JOB]
    raw_steps = job.get("steps")
    assert isinstance(raw_steps, list), "coverage job steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), (
        "coverage job steps must be mappings"
    )
    return raw_steps


def _readable_steps(job: dict[str, object]) -> list[dict[str, object]] | None:
    """Return the job's steps, or ``None`` when they are not all mappings."""
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list):
        return None
    if not all(isinstance(step, dict) for step in raw_steps):
        return None
    return raw_steps


def _coverage_flag_violations(
    documents: Workflow,
) -> list[str]:
    """Check that main coverage fails before inherited flags can win.

    Returns
    -------
    list[str]
        One message per violated contract; empty when the workflow complies.
    """
    workflow = documents.get(WORKFLOW)
    if workflow is None:
        return [f"{WORKFLOW} is required for the main coverage compiler contract"]

    violations: list[str] = []
    if _binds_encoded_flags(mapping_at(documents, WORKFLOW)):
        violations.append(f"{WORKFLOW} workflow env must not bind {ENCODED_FLAGS}")
    job = jobs(WORKFLOW, workflow).get(JOB)
    if job is None:
        return [*violations, f"{WORKFLOW} must retain jobs.{JOB}"]
    if _binds_encoded_flags(job):
        violations.append(f"{WORKFLOW}:jobs.{JOB} env must not bind {ENCODED_FLAGS}")

    steps = _readable_steps(job)
    if steps is None:
        return [*violations, f"{WORKFLOW}:jobs.{JOB} has unreadable steps"]
    return [*violations, *_step_violations(steps)]


def _step_violations(steps: list[dict[str, object]]) -> list[str]:
    """Check the encoded-flag bindings, coverage call and guard step."""
    violations = [
        f"{WORKFLOW}:jobs.{JOB}:steps[{index}] must not bind {ENCODED_FLAGS}"
        for index, step in enumerate(steps)
        if _binds_encoded_flags(step)
    ]
    coverage_steps = [step for step in steps if calls(step, COVERAGE_ACTION)]
    if len(coverage_steps) != 1:
        return [*violations, f"{WORKFLOW}:jobs.{JOB} must call coverage exactly once"]
    coverage = coverage_steps[0]
    coverage_environment = coverage.get("env")
    if (
        not isinstance(coverage_environment, dict)
        or coverage_environment.get("RUSTFLAGS") != LLVM_RUSTFLAGS
    ):
        violations.append(f"{WORKFLOW} coverage must use the explicit LLVM RUSTFLAGS")
    return [*violations, *_check_step_violations(steps, coverage)]


def _check_step_violations(
    steps: list[dict[str, object]], coverage: dict[str, object]
) -> list[str]:
    """Check the compiler-environment guard exists once and precedes coverage."""
    check_matches = [
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == CHECK_NAME
    ]
    if len(check_matches) != 1:
        return [f"{WORKFLOW} must have one compiler-environment check"]
    check_index, check = check_matches[0]
    violations = []
    if check_index >= steps.index(coverage):
        violations.append(
            f"{WORKFLOW} compiler-environment check must precede coverage"
        )
    return [*violations, *_check_content_violations(check)]


def _check_content_violations(check: dict[str, object]) -> list[str]:
    """Check the guard step is unconditional and fails on encoded flags."""
    violations = []
    if "if" in check or continues_on_error(check):
        violations.append(
            f"{WORKFLOW} compiler-environment check must be unconditional and binding"
        )
    run = check.get("run")
    if not isinstance(run, str) or ENCODED_FLAGS_GUARD.search(run) is None:
        violations.append(
            f"{WORKFLOW} compiler-environment check must fail when "
            f"{ENCODED_FLAGS} is set"
        )
    return violations


def _binds_encoded_flags(mapping: dict[str, object]) -> bool:
    """Fail closed on malformed env maps and direct encoded-flag bindings."""
    environment = mapping.get("env")
    return environment is not None and (
        not isinstance(environment, dict) or ENCODED_FLAGS in environment
    )


def test_main_coverage_has_a_binding_compiler_environment_check() -> None:
    """The checked-in workflow satisfies the compiler-environment contract."""
    violations = _coverage_flag_violations(fresh_documents())
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param(
            "removed", "must have one compiler-environment check", id="removed"
        ),
        pytest.param("late", "must precede coverage", id="late"),
        pytest.param("guarded", "must be unconditional and binding", id="guarded"),
        pytest.param(
            "soft-failing", "must be unconditional and binding", id="soft-failing"
        ),
        pytest.param("wrong-command", "must fail when", id="wrong-command"),
    ],
)
def test_main_coverage_environment_check_mutations_fail(
    mutation: str, expected: str
) -> None:
    """Each weakening of the guard step is reported as a violation."""
    documents = fresh_documents()
    _mutate_check_step(_coverage_steps(documents), mutation)

    violations = _coverage_flag_violations(documents)
    assert any(expected in violation for violation in violations), violations


def _mutate_check_step(steps: list[dict[str, object]], mutation: str) -> None:
    """Weaken the compiler-environment guard step in the named way."""
    coverage_index = next(
        index for index, step in enumerate(steps) if calls(step, COVERAGE_ACTION)
    )
    check_index = next(
        index for index, step in enumerate(steps) if step.get("name") == CHECK_NAME
    )
    check = steps[check_index]
    match mutation:
        case "removed":
            steps.pop(check_index)
        case "late":
            steps.remove(check)
            steps.insert(coverage_index + 1, check)
        case "guarded":
            check["if"] = "false"
        case "soft-failing":
            check["continue-on-error"] = True
        case _:
            check["run"] = "true"


@pytest.mark.parametrize("scope", ["workflow", "job", "coverage step"])
def test_main_coverage_rejects_encoded_flags_bindings(scope: str) -> None:
    """Binding the encoded flags at any scope is reported as a violation."""
    documents = fresh_documents()
    workflow = documents[WORKFLOW]
    match scope:
        case "workflow":
            workflow["env"] = {ENCODED_FLAGS: ""}
        case "job":
            jobs(WORKFLOW, workflow)[JOB]["env"] = {ENCODED_FLAGS: ""}
        case _:
            coverage = next(
                step
                for step in _coverage_steps(documents)
                if calls(step, COVERAGE_ACTION)
            )
            coverage["env"] = {ENCODED_FLAGS: ""}

    violations = _coverage_flag_violations(documents)
    assert any(ENCODED_FLAGS in violation for violation in violations), violations


def test_main_coverage_keeps_the_explicit_llvm_flags() -> None:
    """Swapping the explicit LLVM RUSTFLAGS for Cranelift is rejected."""
    documents = fresh_documents()
    steps = _coverage_steps(documents)
    coverage = next(step for step in steps if calls(step, COVERAGE_ACTION))
    mapping_at(coverage, "env")["RUSTFLAGS"] = "-Zcodegen-backend=cranelift -Zthreads=8"

    violations = _coverage_flag_violations(documents)
    assert any("explicit LLVM RUSTFLAGS" in violation for violation in violations), (
        violations
    )
