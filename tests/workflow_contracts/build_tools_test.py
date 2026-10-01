"""Mutation tests for Linux suite build-tool provisioning."""

from __future__ import annotations

import pytest

from build_tools_rules import (
    LINKER_VERSION,
    build_tool_violations,
    read_build_tool_workflows,
)
from workflow_contract_support import (
    Document,
    WorkflowError,
    fresh_documents,
    jobs,
    load_workflow,
)


def _ci_steps(documents: dict[str, Document]) -> list[dict[str, object]]:
    """Return CI's validated build-test steps for named workflow mutations."""
    workflow_jobs = jobs("ci.yml", documents["ci.yml"])
    raw_steps = workflow_jobs["build-test"].get("steps")
    assert isinstance(raw_steps, list) and all(isinstance(step, dict) for step in raw_steps)
    return raw_steps


def test_current_workflows_provision_linker_before_each_linux_suite() -> None:
    violations = build_tool_violations(read_build_tool_workflows())
    assert violations == [], "\n".join(violations)


def test_duplicate_workflow_keys_are_rejected() -> None:
    with pytest.raises(WorkflowError, match="duplicate key"):
        load_workflow("duplicate.yml", "jobs:\n  test: {}\n  test: {}\n")


def test_removing_setup_rust_breaks_coverage_provisioning() -> None:
    documents = fresh_documents()
    steps = documents["ci.yml"]["jobs"]["build-test"]["steps"]
    setup_index = next(
        index
        for index, step in enumerate(steps)
        if isinstance(step, dict) and "setup-rust@" in str(step.get("uses", ""))
    )
    steps.pop(setup_index)

    violations = build_tool_violations(documents)
    assert any(
        "ci.yml:jobs.build-test no pinned linker installer" in violation
        for violation in violations
    ), violations


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("remove", "no unconditional make install-build-tools", id="removed"),
        pytest.param("late", "make install-build-tools must run before the suite", id="late"),
        pytest.param("conditional", "must not have an if condition", id="conditional"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
    ],
)
def test_wrapper_mutations_are_rejected(mutation: str, expected: str) -> None:
    documents = fresh_documents()
    steps = _ci_steps(documents)
    wrapper_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "make install-build-tools"
    )
    wrapper = steps[wrapper_index]
    if mutation == "remove":
        steps.pop(wrapper_index)
    elif mutation == "late":
        steps.append(steps.pop(wrapper_index))
    elif mutation == "conditional":
        wrapper["if"] = "runner.os == 'Linux'"
    else:
        wrapper["continue-on-error"] = True

    violations = build_tool_violations(documents)
    assert any(expected in violation for violation in violations), violations


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("late", "must run before the suite", id="moved-late"),
        pytest.param("conditional", "must not have an if condition", id="conditional"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
        pytest.param("version", f"must install pinned linker version {LINKER_VERSION}", id="version"),
    ],
)
def test_setup_rust_mutations_are_rejected(mutation: str, expected: str) -> None:
    documents = fresh_documents()
    steps = _ci_steps(documents)
    setup_index = next(
        index
        for index, step in enumerate(steps)
        if "setup-rust@" in str(step.get("uses", ""))
    )
    setup_step = steps[setup_index]
    if mutation == "late":
        steps.append(steps.pop(setup_index))
    elif mutation == "conditional":
        setup_step["if"] = "runner.os == 'Linux'"
    elif mutation == "soft-fail":
        setup_step["continue-on-error"] = True
    else:
        setup_step["with"]["mold-version"] = "0.0.0"

    violations = build_tool_violations(documents)
    assert any(expected in violation for violation in violations), violations


def test_new_linux_suite_without_an_installer_is_discovered() -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"]["future-linux-suite"] = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": "cargo test --workspace"}],
    }

    violations = build_tool_violations(documents)
    assert any(
        "ci.yml:jobs.future-linux-suite no pinned linker installer" in violation
        for violation in violations
    ), violations


def test_unknown_runner_for_a_suite_fails_closed() -> None:
    documents = fresh_documents()
    documents["ci.yml"]["jobs"]["future-unknown-suite"] = {
        "runs-on": "${{ inputs.runner }}",
        "steps": [{"run": "cargo test --workspace"}],
    }

    violations = build_tool_violations(documents)
    assert any(
        "future-unknown-suite has a suite path but its Linux runner cannot be determined"
        in violation
        for violation in violations
    ), violations


def test_new_local_reusable_suite_call_fails_closed() -> None:
    documents = fresh_documents()
    documents["future-reusable.yml"] = {
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [{"run": "cargo test --workspace"}],
            }
        }
    }
    documents["ci.yml"]["jobs"]["future-reusable"] = {
        "uses": "./.github/workflows/future-reusable.yml"
    }

    violations = build_tool_violations(documents)
    assert any(
        "future-reusable calls a local reusable workflow whose suite paths are not checked"
        in violation
        for violation in violations
    ), violations


def test_mutation_reusable_suite_requires_build_tool_install() -> None:
    documents = fresh_documents()
    commands = documents["mutation-testing.yml"]["jobs"]["mutation"]["with"][
        "setup-commands"
    ]
    documents["mutation-testing.yml"]["jobs"]["mutation"]["with"][
        "setup-commands"
    ] = commands.replace("make install-build-tools\n", "")

    violations = build_tool_violations(documents)
    assert any(
        "mutation-testing.yml:jobs.mutation setup-commands must run one unconditional"
        in violation
        for violation in violations
    ), violations


def test_mutation_setup_cannot_hide_install_under_a_condition() -> None:
    documents = fresh_documents()
    job = documents["mutation-testing.yml"]["jobs"]["mutation"]
    commands = job["with"]["setup-commands"]
    job["with"]["setup-commands"] = commands.replace(
        "make install-build-tools\n", "if test -n \"$HOME\"; then\nmake install-build-tools\nfi\n"
    )

    violations = build_tool_violations(documents)
    assert any("must run one unconditional" in violation for violation in violations)


def test_empty_suite_set_is_not_compliant() -> None:
    documents = {
        "only-build.yml": {
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "steps": [{"run": "cargo build --workspace"}],
                }
            }
        }
    }

    assert build_tool_violations(documents) == [
        "no test, coverage, or mutation suite paths were found"
    ]
