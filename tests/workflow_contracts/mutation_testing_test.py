"""Contract tests for the mutation-testing caller workflow.

The executable logic lives in the ``leynos/shared-actions`` reusable
workflow, which carries its own unit and integration tests; evert's
caller is declarative configuration. These tests parse the caller with
PyYAML and assert the contract it must uphold: the caller references a
reviewed full-SHA revision, and the surrounding permissions, triggers,
and inputs are not lost. A proposed pin change needs source review before
it is added to the allowlist, so CI catches an unreviewed Dependabot
repin before a scheduled or manual run.

Run via ``make test-workflow-contracts``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "mutation-testing.yml"
)

#: The reusable-workflow revisions whose `install-mold` input and forwarding
#: were checked in merged source. Shared-actions #545 added the input and
#: forwards it to Setup Rust; Dependabot proposals need that source review
#: before another SHA is added here.
REVIEWED_SHARED_ACTION_PINS = frozenset(
    {"9a27950942334d69ff79005b3a8db23bf151f43f"}
)

#: Require a complete, lowercase commit SHA in the expected reusable-workflow
#: path before checking it against the source-reviewed allowlist.
USES_RE = re.compile(
    r"^leynos/shared-actions/\.github/workflows/mutation-cargo\.yml@(?P<pin>[0-9a-f]{40})$"
)

#: The exact caller configuration: mirror the CI baseline's
#: --all-features and install the Clang and pinned linker set that
#: .cargo/config.toml requires on x86_64-unknown-linux-gnu.
EXPECTED_WITH = {
    "extra-args": "--all-features",
    "setup-commands": (
        "export DEBIAN_FRONTEND=noninteractive\n"
        "sudo apt-get update\n"
        "sudo apt-get install --yes --no-install-recommends clang lld\n"
        "make install-build-tools\n"
        'echo "$HOME/.local/bin" >> "$GITHUB_PATH"\n'
    ),
    "install-mold": "true",
}


def _load() -> dict[str, object]:
    """Parse the workflow file."""
    return yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))


def _triggers(workflow: dict[str, object]) -> dict[str, object]:
    """Return the ``on:`` mapping (PyYAML parses the bare key as True)."""
    triggers = workflow.get("on", workflow.get(True))
    assert isinstance(triggers, dict), "the workflow must declare an on: mapping"
    return triggers


def _mutation_job(workflow: dict[str, object]) -> dict[str, object]:
    """Return the single calling job."""
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), "the workflow must declare a jobs mapping"
    assert jobs, "the workflow must declare at least one job"
    assert list(jobs) == ["mutation"], (
        f"expected a single job named 'mutation', found {sorted(jobs)}"
    )
    return jobs["mutation"]


def _assert_reviewed_action_pin(uses: object) -> None:
    """Require the reusable action's exact path and a reviewed full SHA."""
    assert isinstance(uses, str), f"jobs.mutation.uses must be a string, got {uses!r}"
    match = USES_RE.fullmatch(uses)
    assert match is not None, (
        "jobs.mutation.uses must reference mutation-cargo.yml pinned to a "
        f"full 40-character lowercase hex commit SHA, not a branch or tag: {uses!r}"
    )
    pin = match.group("pin")
    assert pin in REVIEWED_SHARED_ACTION_PINS, (
        f"shared-actions pin {pin} has not been reviewed for the required "
        "install-mold input and forwarding"
    )


def _assert_mutation_job_contract(job: dict[str, object]) -> None:
    """Require an approved action revision and its exact caller inputs."""
    _assert_reviewed_action_pin(job.get("uses"))
    with_block = job.get("with")
    assert with_block == EXPECTED_WITH, (
        f"jobs.mutation.with must be exactly {EXPECTED_WITH!r}, got {with_block!r}"
    )


def test_uses_reference_is_pinned_to_a_commit_sha() -> None:
    """The job must call the source-reviewed shared action revision."""
    uses = _mutation_job(_load()).get("uses")
    _assert_reviewed_action_pin(uses)


@pytest.mark.parametrize(
    "pin",
    [
        pytest.param("22c1a57865e42ba7e2ca4f88ae49fa6f81f58013", id="old-pin"),
        pytest.param("0" * 40, id="unreviewed-full-sha"),
    ],
)
def test_unreviewed_action_pin_mutation_is_rejected(pin: str) -> None:
    """Old and otherwise valid SHA pins fail until their source is reviewed."""
    job = _mutation_job(_load())
    job["uses"] = (
        "leynos/shared-actions/.github/workflows/mutation-cargo.yml@" + pin
    )
    with pytest.raises(AssertionError, match="has not been reviewed"):
        _assert_mutation_job_contract(job)


@pytest.mark.parametrize(
    ("mutation", "value"),
    [
        pytest.param("drop", None, id="missing-install-mold"),
        pytest.param("change", "false", id="install-mold-disabled"),
    ],
)
def test_linker_provisioning_input_mutation_is_rejected(
    mutation: str, value: str | None
) -> None:
    """Removing or disabling the shared linker provisioning input fails."""
    job = _mutation_job(_load())
    with_block = job["with"]
    assert isinstance(with_block, dict)
    if mutation == "drop":
        del with_block["install-mold"]
    else:
        with_block["install-mold"] = value
    with pytest.raises(AssertionError, match="jobs.mutation.with must be exactly"):
        _assert_mutation_job_contract(job)


def test_job_permissions_are_exactly_least_privilege() -> None:
    """The job grants contents: read and id-token: write, nothing broader."""
    permissions = _mutation_job(_load()).get("permissions")
    assert permissions == {"contents": "read", "id-token": "write"}, (
        "jobs.mutation.permissions must be exactly "
        f"{{'contents': 'read', 'id-token': 'write'}}, got {permissions!r}"
    )


def test_workflow_default_permissions_are_empty() -> None:
    """The workflow-level default token scope is empty."""
    workflow = _load()
    assert workflow.get("permissions") == {}, (
        f"top-level permissions must be an empty mapping, got "
        f"{workflow.get('permissions')!r}"
    )


def test_concurrency_serializes_per_ref_without_cancelling() -> None:
    """Runs queue per ref instead of cancelling one another."""
    concurrency = _load().get("concurrency")
    assert isinstance(concurrency, dict), "the workflow must declare concurrency"
    assert concurrency.get("group") == "mutation-testing-${{ github.ref }}", (
        f"concurrency.group must key on the triggering ref, got "
        f"{concurrency.get('group')!r}"
    )
    assert concurrency.get("cancel-in-progress") is False, (
        f"concurrency.cancel-in-progress must be false, got "
        f"{concurrency.get('cancel-in-progress')!r}"
    )


def test_triggers_keep_schedule_and_plain_dispatch() -> None:
    """The daily schedule stays; dispatch has no legacy branch input."""
    triggers = _triggers(_load())
    schedule = triggers.get("schedule")
    assert schedule == [{"cron": "35 10 * * *"}], (
        f"on.schedule must be the daily 10:35 UTC cron, got {schedule!r}"
    )
    assert "workflow_dispatch" in triggers, "on.workflow_dispatch is missing"
    dispatch = triggers.get("workflow_dispatch") or {}
    inputs = dispatch.get("inputs") or {}
    assert "branch" not in inputs, (
        "on.workflow_dispatch must not declare a branch input; the Actions "
        "run-workflow control selects the ref"
    )


def test_with_block_carries_the_caller_configuration() -> None:
    """The caller passes reviewed linker provisioning and its setup commands."""
    _assert_mutation_job_contract(_mutation_job(_load()))
