"""Mutation tests for Linux suite build-tool provisioning."""

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
    mapping_at,
    sequence_at,
)

FUTURE_REUSABLE_WORKFLOW = "/".join(
    (".", ".github", "workflows", "future-reusable.yml")
)


def _ci_steps(documents: dict[str, Document]) -> list[dict[str, object]]:
    """Return CI's validated build-test steps for named workflow mutations."""
    workflow_jobs = jobs("ci.yml", documents["ci.yml"])
    raw_steps = workflow_jobs["build-test"].get("steps")
    assert isinstance(raw_steps, list), "CI build-test steps must be a list"
    assert all(isinstance(step, dict) for step in raw_steps), "steps are mappings"
    return raw_steps


def test_current_workflows_provision_linker_before_each_linux_suite() -> None:
    """Every Linux suite job in the repository provisions the linker first."""
    violations = build_tool_violations(read_build_tool_workflows())
    assert not violations, "\n".join(violations)


@pytest.mark.parametrize(
    "source",
    [
        "jobs:\n  test: {}\n  test: {}\n",
        (
            "jobs:\n"
            "  test:\n"
            "    steps:\n"
            "      - uses: checkout\n"
            "        uses: another-action\n"
        ),
    ],
)
def test_duplicate_workflow_keys_are_rejected(source: str) -> None:
    """Workflow loading rejects duplicate keys at every mapping depth."""
    with pytest.raises(WorkflowError, match="duplicate key"):
        load_workflow("duplicate.yml", source)


def test_removing_setup_rust_breaks_coverage_provisioning() -> None:
    """Dropping setup-rust leaves the CI suite without a linker installer."""
    documents = fresh_documents()
    steps = sequence_at(documents, "ci.yml", "jobs", "build-test", "steps")
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
        pytest.param(
            "remove", "no unconditional make install-build-tools", id="removed"
        ),
        pytest.param(
            "late", "make install-build-tools must run before the suite", id="late"
        ),
        pytest.param("conditional", "must not have an if condition", id="conditional"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
    ],
)
def test_wrapper_mutations_are_rejected(mutation: str, expected: str) -> None:
    """Each broken Make installer step is reported."""
    documents = fresh_documents()
    steps = _ci_steps(documents)
    wrapper_index = next(
        index
        for index, step in enumerate(steps)
        if step.get("run") == "make install-build-tools"
    )
    wrapper = steps[wrapper_index]
    match mutation:
        case "remove":
            steps.pop(wrapper_index)
        case "late":
            steps.append(steps.pop(wrapper_index))
        case "conditional":
            wrapper["if"] = "runner.os == 'Linux'"
        case _:
            wrapper["continue-on-error"] = True

    violations = build_tool_violations(documents)
    assert any(expected in violation for violation in violations), violations


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("late", "must run before the suite", id="moved-late"),
        pytest.param("conditional", "must not have an if condition", id="conditional"),
        pytest.param("soft-fail", "must not continue on error", id="soft-failing"),
        pytest.param(
            "version",
            f"must install pinned linker version {LINKER_VERSION}",
            id="version",
        ),
    ],
)
def test_setup_rust_mutations_are_rejected(mutation: str, expected: str) -> None:
    """Each broken setup-rust step is reported."""
    documents = fresh_documents()
    steps = _ci_steps(documents)
    setup_index = next(
        index
        for index, step in enumerate(steps)
        if "setup-rust@" in str(step.get("uses", ""))
    )
    setup_step = steps[setup_index]
    match mutation:
        case "late":
            steps.append(steps.pop(setup_index))
        case "conditional":
            setup_step["if"] = "runner.os == 'Linux'"
        case "soft-fail":
            setup_step["continue-on-error"] = True
        case _:
            mapping_at(setup_step, "with")["mold-version"] = "0.0.0"

    violations = build_tool_violations(documents)
    assert any(expected in violation for violation in violations), violations


def test_new_linux_suite_without_an_installer_is_discovered() -> None:
    """A new suite job is measured without being listed anywhere."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")["future-linux-suite"] = {
        "runs-on": "ubuntu-latest",
        "steps": [{"run": "cargo test --workspace"}],
    }

    violations = build_tool_violations(documents)
    assert any(
        "ci.yml:jobs.future-linux-suite no pinned linker installer" in violation
        for violation in violations
    ), violations


def test_unknown_runner_for_a_suite_fails_closed() -> None:
    """A suite on an undeterminable runner is a violation."""
    documents = fresh_documents()
    mapping_at(documents, "ci.yml", "jobs")["future-unknown-suite"] = {
        "runs-on": "${{ inputs.runner }}",
        "steps": [{"run": "cargo test --workspace"}],
    }

    violations = build_tool_violations(documents)
    assert any(
        "future-unknown-suite has a suite path but its Linux runner "
        "cannot be determined" in violation
        for violation in violations
    ), violations


def test_new_local_reusable_suite_call_fails_closed() -> None:
    """A local reusable workflow call is refused as unchecked."""
    documents = fresh_documents()
    documents["future-reusable.yml"] = {
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [{"run": "cargo test --workspace"}],
            }
        }
    }
    mapping_at(documents, "ci.yml", "jobs")["future-reusable"] = {
        "uses": FUTURE_REUSABLE_WORKFLOW
    }

    violations = build_tool_violations(documents)
    assert any(
        "future-reusable calls a local reusable workflow whose suite paths "
        "are not checked" in violation
        for violation in violations
    ), violations


def test_mutation_reusable_suite_requires_build_tool_install() -> None:
    """The mutation workflow caller must install build tools."""
    documents = fresh_documents()
    inputs = mapping_at(documents, "mutation-testing.yml", "jobs", "mutation", "with")
    commands = inputs["setup-commands"]
    assert isinstance(commands, str), "setup-commands must be a string"
    inputs["setup-commands"] = commands.replace("make install-build-tools\n", "")

    violations = build_tool_violations(documents)
    assert any(
        "mutation-testing.yml:jobs.mutation setup-commands must run one unconditional"
        in violation
        for violation in violations
    ), violations


def test_mutation_setup_cannot_hide_install_under_a_condition() -> None:
    """A conditional install does not satisfy the mutation contract."""
    documents = fresh_documents()
    inputs = mapping_at(documents, "mutation-testing.yml", "jobs", "mutation", "with")
    commands = inputs["setup-commands"]
    assert isinstance(commands, str), "setup-commands must be a string"
    inputs["setup-commands"] = commands.replace(
        "make install-build-tools\n",
        'if test -n "$HOME"; then\nmake install-build-tools\nfi\n',
    )

    violations = build_tool_violations(documents)
    assert any("must run one unconditional" in violation for violation in violations), (
        violations
    )


def test_empty_suite_set_is_not_compliant() -> None:
    """A workflow set with no suite path is not compliant."""
    documents: dict[str, Document] = {
        "only-build.yml": {
            "jobs": {
                "build": {
                    "runs-on": "ubuntu-latest",
                    "steps": [{"run": "cargo build --workspace"}],
                }
            }
        }
    }

    expected = ["no test, coverage, or mutation suite paths were found"]
    assert build_tool_violations(documents) == expected, expected
