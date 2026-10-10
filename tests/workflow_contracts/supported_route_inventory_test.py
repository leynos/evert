"""Guard the repository's supported Cargo routes and their documented boundary."""

from pathlib import Path

import pytest
from supported_route_rules import (
    COVERAGE,
    _release_command_errors,
    guide_errors,
    supported_route_violations,
)
from workflow_contract_support import Step, fresh_documents, jobs

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "developers-guide.md"
GUIDE_TEXT = GUIDE.read_text(encoding="utf-8")


def test_supported_workflow_routes_match_the_documented_inventory() -> None:
    """Accept the committed workflows and developers' guide as they stand."""
    violations = supported_route_violations(fresh_documents(), GUIDE_TEXT)
    assert violations == [], "\n".join(violations)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        pytest.param("format", "lcov", id="legacy-format"),
        pytest.param("output-path", "lcov.info", id="legacy-output-path"),
    ],
)
def test_mixed_coverage_route_rejects_legacy_lcov_settings(
    key: str, value: str
) -> None:
    """Require a Cobertura report format and matching output path."""
    documents = fresh_documents()
    job = jobs("ci.yml", documents["ci.yml"])["build-test"]
    steps = job.get("steps")
    assert isinstance(steps, list), "ci.yml build-test steps must be a list"
    coverage = next(
        step for step in steps if f"{COVERAGE}@" in str(step.get("uses", ""))
    )
    inputs = coverage.get("with")
    assert isinstance(inputs, dict), "coverage action inputs must be a mapping"
    inputs[key] = value

    errors = supported_route_violations(documents, GUIDE_TEXT)
    assert any("Cobertura ratchet selection" in error for error in errors), errors


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
        "That cross-host development route is unsupported because",
        "That cross-host development route is supported because",
        1,
    )
    errors = guide_errors(mutated)
    assert mutated != guide, "the guide no longer contains the sentence under test"
    assert any("unsupported boundary" in error for error in errors), errors


def test_missing_release_steps_skip_their_command_checks() -> None:
    """An absent step adds no command diagnostics for that step."""
    valid_build: tuple[int, Step] = (
        1,
        {
            "run": (
                "env -u CARGO_ENCODED_RUSTFLAGS cross +stable build --release "
                "--target ${{ matrix.target }}"
            )
        },
    )
    invalid_install: tuple[int, Step] = (0, {"run": "cargo install cross"})

    assert not _release_command_errors(None, valid_build), (
        "a missing install step must not add install command errors"
    )
    assert _release_command_errors(invalid_install, None) == [
        "release.yml Install cross must clear encoded flags"
    ], "a missing build step must not add build command errors"


def test_release_commands_allow_whitespace_and_install_script_context() -> None:
    """Commands are whitespace-normalized; install accepts context and flags."""
    install: tuple[int, Step] = (
        0,
        {
            "run": (
                "echo prepare\n  env -u CARGO_ENCODED_RUSTFLAGS\n"
                "cargo install cross --locked\necho finish"
            )
        },
    )
    build: tuple[int, Step] = (
        1,
        {
            "run": (
                "  env -u CARGO_ENCODED_RUSTFLAGS\n"
                "cross +stable build --release --target ${{ matrix.target }}  "
            )
        },
    )

    assert not _release_command_errors(install, build), (
        "whitespace normalization and extra install context should pass"
    )


def test_install_command_requires_the_encoded_flags_substring() -> None:
    """Install scripts without the expected prefix retain their diagnostic."""
    install: tuple[int, Step] = (0, {"run": "cargo install cross --locked"})
    assert _release_command_errors(install, None) == [
        "release.yml Install cross must clear encoded flags"
    ], "installation command without the flags-clearing substring was accepted"


def test_prefixed_wrong_release_command_reports_only_target_mismatch() -> None:
    """A correct prefix with a wrong command fails only the exact-command check."""
    build: tuple[int, Step] = (
        1,
        {"run": "env -u CARGO_ENCODED_RUSTFLAGS cross build --release"},
    )
    assert _release_command_errors(None, build) == [
        "release.yml must build every matrix target with cross +stable"
    ], "correct prefix with wrong build command must report only target mismatch"


def test_unprefixed_wrong_release_command_reports_both_errors_in_order() -> None:
    """Prefix and exact-command checks remain independent and ordered."""
    build: tuple[int, Step] = (1, {"run": "cross build --release"})
    assert _release_command_errors(None, build) == [
        "release.yml Build release binary must clear encoded flags",
        "release.yml must build every matrix target with cross +stable",
    ], "unprefixed build must report both independent diagnostics"


def test_install_diagnostic_precedes_both_build_diagnostics() -> None:
    """Release command errors retain install-before-build aggregation order."""
    install: tuple[int, Step] = (0, {"run": "cargo install cross"})
    build: tuple[int, Step] = (1, {"run": "cross build --release"})
    assert _release_command_errors(install, build) == [
        "release.yml Install cross must clear encoded flags",
        "release.yml Build release binary must clear encoded flags",
        "release.yml must build every matrix target with cross +stable",
    ], "installation error must precede both build command errors"
