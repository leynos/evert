"""Guard the repository's supported Cargo routes and their documented boundary."""

from pathlib import Path

import pytest
from supported_route_rules import COVERAGE, guide_errors, supported_route_violations
from workflow_contract_support import fresh_documents, jobs

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "developers-guide.md"
GUIDE_TEXT = GUIDE.read_text(encoding="utf-8")


def test_supported_workflow_routes_match_the_documented_inventory() -> None:
    """Accept the committed workflows and developers' guide as they stand."""
    violations = supported_route_violations(fresh_documents(), GUIDE_TEXT)
    assert violations == [], "\n".join(violations)


@pytest.mark.parametrize(
    ("workflow", "job_id", "job", "expected"),
    [
        pytest.param(
            "ci.yml",
            "future-development",
            {"runs-on": "windows-latest", "steps": [{"run": "make lint"}]},
            "unsupported",
            id="new-dev-unsupported-runner",
        ),
        pytest.param(
            "coverage-main.yml",
            "future-coverage",
            {"runs-on": "macos-latest", "steps": [{"uses": f"{COVERAGE}@deadbeef"}]},
            "unsupported",
            id="new-coverage-unsupported-runner",
        ),
        pytest.param(
            "ci.yml",
            "future-reusable",
            {"uses": "leynos/shared-actions/.github/workflows/future.yml@" + "a" * 40},
            "unreviewed reusable workflow",
            id="unknown-reusable-workflow",
        ),
    ],
)
def test_new_routes_and_reusable_calls_fail_closed(
    workflow: str, job_id: str, job: dict[str, object], expected: str
) -> None:
    """Reject new jobs and reusable calls that bypass the reviewed inventory."""
    documents = fresh_documents()
    jobs(workflow, documents[workflow])[job_id] = job
    errors = supported_route_violations(documents, GUIDE_TEXT)
    assert any(job_id in error and expected in error for error in errors), errors


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("unstable-cross", "cross +stable", id="stable-cross-removed"),
        pytest.param("release-rustflags", "RUSTFLAGS", id="release-flags-not-empty"),
        pytest.param(
            "install-rustflags", "RUSTFLAGS", id="cross-install-flags-not-empty"
        ),
        pytest.param("encoded-flags", "encoded flags", id="encoded-flag-removal-lost"),
    ],
)
def test_release_route_mutations_are_rejected(mutation: str, expected: str) -> None:
    """Reject release workflow edits that weaken the Cross build contract."""
    documents = fresh_documents()
    steps = jobs("release.yml", documents["release.yml"])["build"]["steps"]
    assert isinstance(steps, list), "release.yml build steps must be a list"
    install = next(step for step in steps if step.get("name") == "Install cross")
    build = next(step for step in steps if step.get("name") == "Build release binary")
    match mutation:
        case "unstable-cross":
            build["run"] = str(build["run"]).replace("cross +stable", "cross")
        case "release-rustflags":
            build["env"] = {}
        case "install-rustflags":
            install["env"] = {}
        case _:
            flags = "env -u CARGO_ENCODED_RUSTFLAGS "
            build["run"] = str(build["run"]).replace(flags, "")
    errors = supported_route_violations(documents, GUIDE_TEXT)
    assert any(expected in error for error in errors), errors


def test_cross_host_unsupported_guidance_cannot_be_removed() -> None:
    """Reject a guide that no longer calls the cross-host route unsupported."""
    guide = " ".join(GUIDE_TEXT.split())
    mutated = guide.replace(
        "That cross-host development route is unsupported:",
        "That cross-host development route is supported:",
        1,
    )
    errors = guide_errors(mutated)
    assert mutated != guide, "the guide no longer contains the sentence under test"
    assert any("unsupported boundary" in error for error in errors), errors
