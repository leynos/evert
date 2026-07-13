"""Contract tests for the mutation-testing caller workflow.

The executable logic lives in the ``leynos/shared-actions`` reusable
workflow, which carries its own unit and integration tests; evert's
caller is declarative configuration. These tests parse the caller with
PyYAML and pin the contract it must uphold, so drift (repointing the pin
at a branch, widening permissions, or losing the feature and linker
configuration) fails CI on the pull request rather than surfacing in a
scheduled or manual run.

Run via ``make test-workflow-contracts``.
"""

from __future__ import annotations

from pathlib import Path

import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "mutation-testing.yml"
)

#: The pinned commit of leynos/shared-actions (leynos/shared-actions
#: PR #334, which adds the `mode: check` coverage gate used by the CI
#: workflow's coverage steps; the estate keeps a single repo-wide pin).
#: Bump the workflow and this constant together.
PINNED_SHA = "927edd45ae77be4251a8a18ca9eb5613a2e32cbd"

EXPECTED_USES = (
    "leynos/shared-actions/.github/workflows/mutation-cargo.yml@" + PINNED_SHA
)

#: The exact caller configuration: mirror the CI baseline's
#: --all-features and install the clang and mold linker set that
#: .cargo/config.toml requires on x86_64-unknown-linux-gnu.
EXPECTED_WITH = {
    "extra-args": "--all-features",
    "setup-commands": (
        "export DEBIAN_FRONTEND=noninteractive\n"
        "sudo apt-get update\n"
        "sudo apt-get install --yes --no-install-recommends clang lld mold\n"
    ),
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


def test_uses_reference_is_pinned_to_the_documented_sha() -> None:
    """The job must call the shared workflow at the exact documented SHA."""
    uses = _mutation_job(_load()).get("uses")
    assert uses is not None, "jobs.mutation.uses is missing"
    path, _, ref = uses.partition("@")
    assert path == "leynos/shared-actions/.github/workflows/mutation-cargo.yml", (
        f"jobs.mutation.uses must reference mutation-cargo.yml, got {path!r}"
    )
    assert len(ref) == 40, (
        f"jobs.mutation.uses must pin a full 40-character commit SHA, "
        f"not a branch or tag: {ref!r}"
    )
    assert all(c in "0123456789abcdef" for c in ref), (
        f"jobs.mutation.uses must pin a lowercase hex commit SHA, "
        f"not a branch or tag: {ref!r}"
    )
    assert uses == EXPECTED_USES, (
        f"jobs.mutation.uses pins {ref!r}; this test documents {PINNED_SHA!r} — "
        "bump the workflow and this test together"
    )


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
    """The caller passes exactly the documented feature and linker setup."""
    with_block = _mutation_job(_load()).get("with")
    assert isinstance(with_block, dict), "jobs.mutation.with is missing"
    assert with_block == EXPECTED_WITH, (
        f"jobs.mutation.with must be exactly {EXPECTED_WITH!r} "
        f"(the CI --all-features baseline plus the clang/mold linker "
        f"setup), got {with_block!r}"
    )
