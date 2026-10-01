"""Guard the repository's supported Cargo routes and their documented boundary."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from workflow_contract_support import (
    Document,
    WorkflowError,
    calls,
    fresh_documents,
    jobs,
    triggers,
)

UBUNTU = "ubuntu-latest"  # Runner label does not prove x86_64 architecture.
COVERAGE = "leynos/shared-actions/.github/actions/generate-coverage"
SETUP_RUST = "leynos/shared-actions/.github/actions/setup-rust"
ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "developers-guide.md"
RELEASE_TARGETS = (
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "x86_64-pc-windows-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-unknown-freebsd",
)
LLVM_ENV = {
    "CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER": "clang",
    "RUSTFLAGS": "-C link-arg=-fuse-ld=lld",
    "CFLAGS": "-fuse-ld=lld",
    "LDFLAGS": "-fuse-ld=lld",
}
KNOWN_ROUTES = {
    ("ci.yml", "build-test"), ("act-validation.yml", "act-validation"),
    ("coverage-main.yml", "coverage-upload"), ("release.yml", "build"),
}
# These wrappers are outside direct-job scanning; their contents are not proven here.
KNOWN_REUSABLE_CALLS = {
    ("dependabot-automerge.yml", "automerge"): "dependabot-automerge.yml",
    ("mutation-testing.yml", "mutation"): "mutation-cargo.yml",
}
BUILD_COMMAND = re.compile(
    r"(?im)(?:^|\s)(?:make\s+(?:build|test|lint|typecheck)"
    r"|cargo\s+(?:\+\S+\s+)?(?:build|test|check|clippy|doc|llvm-cov|nextest)"
    r"|cross\s+(?:\+\S+\s+)?build)\b"
)


def _steps(name: str, job_id: str, job: dict[str, object]) -> list[dict[str, object]]:
    found = job.get("steps")
    if not isinstance(found, list) or not all(isinstance(step, dict) for step in found):
        raise WorkflowError(f"{name}:jobs.{job_id} has unreadable steps")
    return found


def _named(
    name: str, job_id: str, steps: list[dict[str, object]], step_name: str, errors: list[str]
) -> tuple[int, dict[str, object]] | None:
    found = [(index, step) for index, step in enumerate(steps) if step.get("name") == step_name]
    if len(found) != 1:
        errors.append(f"{name}:jobs.{job_id} must have exactly one {step_name!r} step")
        return None
    return found[0]


def _before(
    name: str, job_id: str, earlier: int | None, later: int | None, message: str, errors: list[str]
) -> None:
    if earlier is not None and later is not None and earlier >= later:
        errors.append(f"{name}:jobs.{job_id} {message}")


def _development_route(
    name: str, job_id: str, job: dict[str, object], gate_name: str, gate_run: str
) -> tuple[list[str], list[dict[str, object]]]:
    errors: list[str] = []
    if job.get("runs-on") != UBUNTU:
        errors.append(f"{name}:jobs.{job_id} has an unsupported or indeterminate runner")
    steps = _steps(name, job_id, job)
    setup = _named(name, job_id, steps, "Setup Rust", errors)
    wrapper = _named(name, job_id, steps, "Install build-standard wrapper", errors)
    gate = _named(name, job_id, steps, gate_name, errors)
    if setup is not None:
        uses = str(setup[1].get("uses", "")).partition("@")[0]
        inputs = setup[1].get("with")
        if (
            uses.casefold() != SETUP_RUST.casefold()
            or not isinstance(inputs, dict)
            or inputs.get("install-mold") != "true"
        ):
            errors.append(f"{name}:jobs.{job_id} must install the pinned linker with shared setup-rust")
    if wrapper is not None and wrapper[1].get("run") != "make install-build-tools":
        errors.append(f"{name}:jobs.{job_id} wrapper step must run make install-build-tools")
    if gate is not None and gate[1].get("run") != gate_run:
        errors.append(f"{name}:jobs.{job_id} {gate_name} route changed")
    _before(name, job_id, setup[0] if setup else None, wrapper[0] if wrapper else None,
            "must set up the linker before its build tools", errors)
    _before(name, job_id, wrapper[0] if wrapper else None, gate[0] if gate else None,
            "must install build tools before its development gate", errors)
    return errors, steps


def _coverage_route(
    name: str, job_id: str, steps: list[dict[str, object]], errors: list[str]
) -> tuple[int, dict[str, object]] | None:
    found = [(i, step) for i, step in enumerate(steps) if calls(step, COVERAGE)]
    if len(found) != 1:
        errors.append(f"{name}:jobs.{job_id} must call the coverage action exactly once")
        return None
    index, step = found[0]
    if step.get("env") != LLVM_ENV:
        errors.append(f"{name}:jobs.{job_id} coverage must use the explicit LLVM route")
    inputs = step.get("with")
    expected = {"output-path": "lcov.info", "format": "lcov", "with-ratchet": "true"}
    if not isinstance(inputs, dict) or any(
        inputs.get(key) != value for key, value in expected.items()
    ):
        errors.append(f"{name}:jobs.{job_id} coverage must retain the lcov ratchet selection")
    return index, step


def _pr_route(documents: dict[str, Document]) -> list[str]:
    name = "ci.yml"
    errors: list[str] = []
    document = documents[name]
    if "pull_request" not in triggers(name, document):
        errors.append("ci.yml must retain its pull_request trigger")
    job = jobs(name, document).get("build-test")
    if job is None:
        return errors + ["ci.yml must retain jobs.build-test"]
    route_errors, steps = _development_route(name, "build-test", job, "Lint", "make lint")
    errors.extend(route_errors)
    wrapper = _named(name, "build-test", steps, "Install build-standard wrapper", errors)
    coverage = _coverage_route(name, "build-test", steps, errors)
    _before(
        name,
        "build-test",
        wrapper[0] if wrapper else None,
        coverage[0] if coverage else None,
        "must install build tools before coverage tests",
        errors,
    )
    if coverage is not None and coverage[1].get("if") != "github.event_name == 'pull_request'":
        errors.append("ci.yml coverage must stay on the pull_request route")
    return errors


def _act_route(documents: dict[str, Document]) -> list[str]:
    name = "act-validation.yml"
    errors: list[str] = []
    document = documents[name]
    if "pull_request" not in triggers(name, document):
        errors.append("act-validation.yml must retain its pull_request trigger")
    job = jobs(name, document).get("act-validation")
    if job is None:
        return errors + ["act-validation.yml must retain jobs.act-validation"]
    route_errors, _ = _development_route(
        name, "act-validation", job, "Run tests with act validation", "make test WITH_ACT=1"
    )
    return errors + route_errors


def _coverage_main_route(documents: dict[str, Document]) -> list[str]:
    name = "coverage-main.yml"
    errors: list[str] = []
    document = documents[name]
    push = triggers(name, document).get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        errors.append("coverage-main.yml must publish from pushes to main")
    job = jobs(name, document).get("coverage-upload")
    if job is None:
        return errors + ["coverage-main.yml must retain jobs.coverage-upload"]
    if job.get("runs-on") != UBUNTU:
        errors.append("coverage-main.yml:jobs.coverage-upload has an unsupported runner")
    steps = _steps(name, "coverage-upload", job)
    _coverage_route(name, "coverage-upload", steps, errors)
    return errors


def _release_route(documents: dict[str, Document]) -> list[str]:
    name = "release.yml"
    errors: list[str] = []
    document = documents[name]
    job = jobs(name, document).get("build")
    if job is None:
        return errors + ["release.yml must retain jobs.build"]
    if job.get("runs-on") != UBUNTU:
        errors.append("release.yml:jobs.build must run on ubuntu-latest for Cross")
    strategy = job.get("strategy")
    matrix = strategy.get("matrix") if isinstance(strategy, dict) else None
    includes = matrix.get("include") if isinstance(matrix, dict) else None
    targets = [entry.get("target") for entry in includes if isinstance(entry, dict)] \
        if isinstance(includes, list) else []
    if tuple(targets) != RELEASE_TARGETS:
        errors.append("release.yml must retain its six reviewed Cross targets")
    steps = _steps(name, "build", job)
    setup_calls = [
        (index, step)
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).partition("@")[0].casefold() == SETUP_RUST.casefold()
    ]
    setup = setup_calls[0] if len(setup_calls) == 1 else None
    if setup is None:
        errors.append("release.yml build must have exactly one shared setup-rust action")
    elif not re.fullmatch(r"[0-9a-f]{40}", str(setup[1].get("uses", "")).partition("@")[2]):
        errors.append("release.yml setup-rust must use an immutable full-SHA pin")
    install = _named(name, "build", steps, "Install cross", errors)
    build = _named(name, "build", steps, "Build release binary", errors)
    if setup is not None:
        uses = str(setup[1].get("uses", "")).partition("@")[0]
        inputs = setup[1].get("with")
        if (
            uses.casefold() != SETUP_RUST.casefold()
            or not isinstance(inputs, dict)
            or inputs.get("toolchain") != "stable"
        ):
            errors.append("release.yml must provision its stable shared Rust toolchain")
    for step_name, found in (("Install cross", install), ("Build release binary", build)):
        if found is not None:
            env = found[1].get("env")
            if not isinstance(env, dict) or env.get("RUSTFLAGS") != "":
                errors.append(f"release.yml {step_name} must set RUSTFLAGS to an empty string")
    if install is not None:
        command = " ".join(str(install[1].get("run", "")).split())
        if "env -u CARGO_ENCODED_RUSTFLAGS cargo install cross" not in command:
            errors.append("release.yml Install cross must clear encoded flags")
    if build is not None:
        command = " ".join(str(build[1].get("run", "")).split())
        if not command.startswith("env -u CARGO_ENCODED_RUSTFLAGS "):
            errors.append("release.yml Build release binary must clear encoded flags")
        expected = (
            "env -u CARGO_ENCODED_RUSTFLAGS cross +stable build --release "
            "--target ${{ matrix.target }}"
        )
        if command != expected:
            errors.append("release.yml must build every matrix target with cross +stable")
    _before(
        name,
        "build",
        setup[0] if setup else None,
        install[0] if install else None,
        "must provision stable Rust before installing Cross",
        errors,
    )
    _before(
        name,
        "build",
        install[0] if install else None,
        build[0] if build else None,
        "must install Cross before building release targets",
        errors,
    )
    return errors


def _has_route(job: dict[str, object]) -> bool:
    if ".github/workflows/" in str(job.get("uses", "")):
        return True
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    return any(
        isinstance(step, dict)
        and (
            calls(step, COVERAGE)
            or (
                isinstance(step.get("run"), str)
                and BUILD_COMMAND.search(step["run"])
            )
        )
        for step in steps
    )


def _extra_route_errors(documents: dict[str, Document]) -> list[str]:
    errors: list[str] = []
    for name, document in documents.items():
        for job_id, job in jobs(name, document).items():
            if (name, job_id) in KNOWN_ROUTES:
                continue
            reusable = job.get("uses")
            if isinstance(reusable, str) and ".github/workflows/" in reusable:
                expected = KNOWN_REUSABLE_CALLS.get((name, job_id))
                prefix = f"leynos/shared-actions/.github/workflows/{expected}@" if expected else ""
                revision = reusable.removeprefix(prefix) if prefix else ""
                if not prefix or not re.fullmatch(r"[0-9a-f]{40}", revision):
                    errors.append(
                        f"{name}:jobs.{job_id} calls an unreviewed reusable workflow"
                    )
                continue
            if not _has_route(job):
                continue
            if job.get("runs-on") != UBUNTU:
                errors.append(f"{name}:jobs.{job_id} has an unsupported or indeterminate runner")
            else:
                errors.append(f"{name}:jobs.{job_id} adds a route outside the reviewed inventory")
    return errors


def _guide_errors(guide: str) -> list[str]:
    text = " ".join(guide.split())
    required = (
        ("native target", "On `x86_64-unknown-linux-gnu`, development"),
        ("cross-host behaviour", "Cargo's target table also applies to a direct cross build *to* "
         "`x86_64-unknown-linux-gnu` from another host."),
        ("unsupported boundary", "That cross-host development route is unsupported:"),
        ("Cross packaging", "stable Cross release workflow"),
    )
    return [
        f"developers' guide must document {label}"
        for label, phrase in required
        if phrase not in text
    ]


def supported_route_violations(documents: dict[str, Document], guide: str) -> list[str]:
    """Compare parsed workflow routes and the documented target boundary."""
    routes = (_pr_route, _act_route, _coverage_main_route, _release_route)
    route_errors = sum((route(documents) for route in routes), [])
    return route_errors + _extra_route_errors(documents) + _guide_errors(guide)


GUIDE_TEXT = GUIDE.read_text(encoding="utf-8")


def test_supported_workflow_routes_match_the_documented_inventory() -> None:
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
    documents = fresh_documents()
    jobs(workflow, documents[workflow])[job_id] = job
    errors = supported_route_violations(documents, GUIDE_TEXT)
    assert any(job_id in error and expected in error for error in errors), errors


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        pytest.param("unstable-cross", "cross +stable", id="stable-cross-removed"),
        pytest.param("release-rustflags", "RUSTFLAGS", id="release-flags-not-empty"),
        pytest.param("install-rustflags", "RUSTFLAGS", id="cross-install-flags-not-empty"),
        pytest.param("encoded-flags", "encoded flags", id="encoded-flag-removal-lost"),
    ],
)
def test_release_route_mutations_are_rejected(mutation: str, expected: str) -> None:
    documents = fresh_documents()
    steps = jobs("release.yml", documents["release.yml"])["build"]["steps"]
    assert isinstance(steps, list)
    install = next(step for step in steps if step.get("name") == "Install cross")
    build = next(step for step in steps if step.get("name") == "Build release binary")
    if mutation == "unstable-cross":
        build["run"] = str(build["run"]).replace("cross +stable", "cross")
    elif mutation == "release-rustflags":
        build["env"] = {}
    elif mutation == "install-rustflags":
        install["env"] = {}
    else:
        build["run"] = str(build["run"]).replace("env -u CARGO_ENCODED_RUSTFLAGS ", "")
    errors = supported_route_violations(documents, GUIDE_TEXT)
    assert any(expected in error for error in errors), errors


def test_cross_host_unsupported_guidance_cannot_be_removed() -> None:
    guide = " ".join(GUIDE_TEXT.split())
    mutated = guide.replace("That cross-host development route is unsupported:",
                            "That cross-host development route is supported:", 1)
    assert mutated != guide
    assert any("unsupported boundary" in error for error in _guide_errors(mutated))
