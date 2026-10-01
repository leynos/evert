"""Check the supported Cargo routes in the workflows against the reviewed inventory."""

import dataclasses
import re

from workflow_contract_support import Document, WorkflowError, calls, jobs, triggers

UBUNTU = "ubuntu-latest"  # Runner label does not prove x86_64 architecture.
COVERAGE = "leynos/shared-actions/.github/actions/generate-coverage"
SETUP_RUST = "leynos/shared-actions/.github/actions/setup-rust"
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
    ("ci.yml", "build-test"),
    ("act-validation.yml", "act-validation"),
    ("coverage-main.yml", "coverage-upload"),
    ("release.yml", "build"),
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

type Step = dict[str, object]
type Found = tuple[int, Step] | None
SHA = re.compile(r"[0-9a-f]{40}")
REUSABLE_MARKER = ".github/workflows/"
REUSABLE_PREFIX = "leynos/shared-actions/.github/workflows/"


@dataclasses.dataclass(frozen=True, slots=True)
class _JobRef:
    """Identify a workflow job for step lookups and error messages."""

    name: str
    job_id: str
    job: dict[str, object]

    @property
    def where(self) -> str:
        """Format the `workflow:jobs.id` prefix used by error messages."""
        return f"{self.name}:jobs.{self.job_id}"


def _steps(ref: _JobRef) -> list[Step]:
    """Return the job's step mappings or fail on unreadable steps."""
    found = ref.job.get("steps")
    if not isinstance(found, list) or not all(isinstance(step, dict) for step in found):
        message = f"{ref.where} has unreadable steps"
        raise WorkflowError(message)
    return found


def _named(ref: _JobRef, steps: list[Step], step_name: str, errors: list[str]) -> Found:
    """Find the single step called `step_name`, recording an error otherwise."""
    found = [
        (index, step)
        for index, step in enumerate(steps)
        if step.get("name") == step_name
    ]
    if len(found) != 1:
        errors.append(f"{ref.where} must have exactly one {step_name!r} step")
        return None
    return found[0]


def _before(ref: _JobRef, orderings: tuple[tuple[Found, Found, str], ...]) -> list[str]:
    """Require each `earlier` step to precede its `later` step when both exist."""
    return [
        f"{ref.where} {message}"
        for earlier, later, message in orderings
        if earlier is not None and later is not None and earlier[0] >= later[0]
    ]


def _is_setup_rust(step: Step) -> bool:
    """Report whether a step calls the shared setup-rust action, ignoring the pin."""
    uses = str(step.get("uses", "")).partition("@")[0]
    return uses.casefold() == SETUP_RUST.casefold()


def _has_input(step: Step, key: str, value: str) -> bool:
    """Report whether the step's `with` mapping sets `key` to `value`."""
    inputs = step.get("with")
    return isinstance(inputs, dict) and inputs.get(key) == value


def _setup_errors(ref: _JobRef, setup: Found) -> list[str]:
    """Require the development setup step to install the pinned linker."""
    if setup is None:
        return []
    if _is_setup_rust(setup[1]) and _has_input(setup[1], "install-mold", "true"):
        return []
    return [f"{ref.where} must install the pinned linker with shared setup-rust"]


def _development_route(
    ref: _JobRef, gate_name: str, gate_run: str
) -> tuple[list[str], list[Step]]:
    """Check a development job's runner, linker setup, wrapper and gate."""
    errors: list[str] = []
    if ref.job.get("runs-on") != UBUNTU:
        errors.append(f"{ref.where} has an unsupported or indeterminate runner")
    steps = _steps(ref)
    setup = _named(ref, steps, "Setup Rust", errors)
    wrapper = _named(ref, steps, "Install build-standard wrapper", errors)
    gate = _named(ref, steps, gate_name, errors)
    errors.extend(_setup_errors(ref, setup))
    if wrapper is not None and wrapper[1].get("run") != "make install-build-tools":
        errors.append(f"{ref.where} wrapper step must run make install-build-tools")
    if gate is not None and gate[1].get("run") != gate_run:
        errors.append(f"{ref.where} {gate_name} route changed")
    linker_first = "must set up the linker before its build tools"
    tools_first = "must install build tools before its development gate"
    errors.extend(
        _before(ref, ((setup, wrapper, linker_first), (wrapper, gate, tools_first)))
    )
    return errors, steps


def _coverage_route(ref: _JobRef, steps: list[Step], errors: list[str]) -> Found:
    """Require exactly one coverage action call on the explicit LLVM route."""
    found = [(i, step) for i, step in enumerate(steps) if calls(step, COVERAGE)]
    if len(found) != 1:
        errors.append(f"{ref.where} must call the coverage action exactly once")
        return None
    index, step = found[0]
    if step.get("env") != LLVM_ENV:
        errors.append(f"{ref.where} coverage must use the explicit LLVM route")
    expected = {"output-path": "lcov.info", "format": "lcov", "with-ratchet": "true"}
    if not all(_has_input(step, key, value) for key, value in expected.items()):
        errors.append(f"{ref.where} coverage must retain the lcov ratchet selection")
    return index, step


def _pr_route(documents: dict[str, Document]) -> list[str]:
    """Check the pull request development and coverage route in `ci.yml`."""
    name = "ci.yml"
    errors: list[str] = []
    document = documents[name]
    if "pull_request" not in triggers(name, document):
        errors.append("ci.yml must retain its pull_request trigger")
    job = jobs(name, document).get("build-test")
    if job is None:
        return [*errors, "ci.yml must retain jobs.build-test"]
    ref = _JobRef(name, "build-test", job)
    route_errors, steps = _development_route(ref, "Lint", "make lint")
    errors.extend(route_errors)
    wrapper = _named(ref, steps, "Install build-standard wrapper", errors)
    coverage = _coverage_route(ref, steps, errors)
    tools_first = "must install build tools before coverage tests"
    errors.extend(_before(ref, ((wrapper, coverage, tools_first),)))
    if (
        coverage is not None
        and coverage[1].get("if") != "github.event_name == 'pull_request'"
    ):
        errors.append("ci.yml coverage must stay on the pull_request route")
    return errors


def _act_route(documents: dict[str, Document]) -> list[str]:
    """Check the act validation development route."""
    name = "act-validation.yml"
    errors: list[str] = []
    document = documents[name]
    if "pull_request" not in triggers(name, document):
        errors.append("act-validation.yml must retain its pull_request trigger")
    job = jobs(name, document).get("act-validation")
    if job is None:
        return [*errors, "act-validation.yml must retain jobs.act-validation"]
    ref = _JobRef(name, "act-validation", job)
    route_errors, _ = _development_route(
        ref, "Run tests with act validation", "make test WITH_ACT=1"
    )
    return [*errors, *route_errors]


def _coverage_main_route(documents: dict[str, Document]) -> list[str]:
    """Check the coverage upload route that publishes from pushes to main."""
    name = "coverage-main.yml"
    errors: list[str] = []
    document = documents[name]
    push = triggers(name, document).get("push")
    if not isinstance(push, dict) or push.get("branches") != ["main"]:
        errors.append("coverage-main.yml must publish from pushes to main")
    job = jobs(name, document).get("coverage-upload")
    if job is None:
        return [*errors, "coverage-main.yml must retain jobs.coverage-upload"]
    if job.get("runs-on") != UBUNTU:
        errors.append(
            "coverage-main.yml:jobs.coverage-upload has an unsupported runner"
        )
    ref = _JobRef(name, "coverage-upload", job)
    _coverage_route(ref, _steps(ref), errors)
    return errors


def _mapping_get(value: object, key: str) -> object:
    """Read `key` from `value` when it is a mapping, else return None."""
    return value.get(key) if isinstance(value, dict) else None


def _release_targets(job: dict[str, object]) -> tuple[object, ...]:
    """List the targets declared in the job's build matrix."""
    strategy = _mapping_get(job.get("strategy"), "matrix")
    includes = _mapping_get(strategy, "include")
    if not isinstance(includes, list):
        return ()
    return tuple(entry.get("target") for entry in includes if isinstance(entry, dict))


def _release_matrix_errors(job: dict[str, object]) -> list[str]:
    """Check the release runner and its reviewed Cross target matrix."""
    errors: list[str] = []
    if job.get("runs-on") != UBUNTU:
        errors.append("release.yml:jobs.build must run on ubuntu-latest for Cross")
    if _release_targets(job) != RELEASE_TARGETS:
        errors.append("release.yml must retain its six reviewed Cross targets")
    return errors


def _release_setup(steps: list[Step]) -> tuple[Found, list[str]]:
    """Find the single shared setup-rust step and require an immutable pin."""
    setup_calls = [
        (index, step) for index, step in enumerate(steps) if _is_setup_rust(step)
    ]
    if len(setup_calls) != 1:
        return None, [
            "release.yml build must have exactly one shared setup-rust action"
        ]
    revision = str(setup_calls[0][1].get("uses", "")).partition("@")[2]
    if SHA.fullmatch(revision) is None:
        return setup_calls[0], [
            "release.yml setup-rust must use an immutable full-SHA pin"
        ]
    return setup_calls[0], []


def _clears_rustflags(step: Step) -> bool:
    """Report whether the step sets `RUSTFLAGS` to an empty string."""
    flags = _mapping_get(step.get("env"), "RUSTFLAGS")
    return isinstance(flags, str) and not flags


def _release_flag_errors(install: Found, build: Found) -> list[str]:
    """Require Cross install and build steps to blank `RUSTFLAGS`."""
    return [
        f"release.yml {step_name} must set RUSTFLAGS to an empty string"
        for step_name, found in (
            ("Install cross", install),
            ("Build release binary", build),
        )
        if found is not None and not _clears_rustflags(found[1])
    ]


def _release_command_errors(install: Found, build: Found) -> list[str]:
    """Require Cross install and build commands to clear encoded flags."""
    errors: list[str] = []
    cleared = "env -u CARGO_ENCODED_RUSTFLAGS "
    if install is not None:
        command = " ".join(str(install[1].get("run", "")).split())
        if f"{cleared}cargo install cross" not in command:
            errors.append("release.yml Install cross must clear encoded flags")
    if build is not None:
        command = " ".join(str(build[1].get("run", "")).split())
        if not command.startswith(cleared):
            errors.append("release.yml Build release binary must clear encoded flags")
        expected = (
            f"{cleared}cross +stable build --release --target ${{{{ matrix.target }}}}"
        )
        if command != expected:
            errors.append(
                "release.yml must build every matrix target with cross +stable"
            )
    return errors


def _release_route(documents: dict[str, Document]) -> list[str]:
    """Check the release workflow's Cross toolchain and build route."""
    job = jobs("release.yml", documents["release.yml"]).get("build")
    if job is None:
        return ["release.yml must retain jobs.build"]
    ref = _JobRef("release.yml", "build", job)
    errors = _release_matrix_errors(job)
    steps = _steps(ref)
    setup, setup_errors = _release_setup(steps)
    errors.extend(setup_errors)
    install = _named(ref, steps, "Install cross", errors)
    build = _named(ref, steps, "Build release binary", errors)
    if setup is not None and not _has_input(setup[1], "toolchain", "stable"):
        errors.append("release.yml must provision its stable shared Rust toolchain")
    errors.extend(_release_flag_errors(install, build))
    errors.extend(_release_command_errors(install, build))
    rust_first = "must provision stable Rust before installing Cross"
    cross_first = "must install Cross before building release targets"
    errors.extend(
        _before(ref, ((setup, install, rust_first), (install, build, cross_first)))
    )
    return errors


def _runs_build_command(step: Step) -> bool:
    """Report whether a step's script invokes a build, test or lint command."""
    command = step.get("run")
    return isinstance(command, str) and BUILD_COMMAND.search(command) is not None


def _has_route(job: dict[str, object]) -> bool:
    """Report whether a job calls a reusable workflow or runs a gated command."""
    if REUSABLE_MARKER in str(job.get("uses", "")):
        return True
    steps = job.get("steps")
    if not isinstance(steps, list):
        return False
    return any(
        isinstance(step, dict) and (calls(step, COVERAGE) or _runs_build_command(step))
        for step in steps
    )


def _job_route_errors(name: str, job_id: str, job: dict[str, object]) -> list[str]:
    """Reject a job that adds a route outside the reviewed inventory."""
    where = f"{name}:jobs.{job_id}"
    reusable = job.get("uses")
    if isinstance(reusable, str) and REUSABLE_MARKER in reusable:
        expected = KNOWN_REUSABLE_CALLS.get((name, job_id), "")
        revision = reusable.removeprefix(f"{REUSABLE_PREFIX}{expected}@")
        if expected and SHA.fullmatch(revision):
            return []
        return [f"{where} calls an unreviewed reusable workflow"]
    if not _has_route(job):
        return []
    if job.get("runs-on") != UBUNTU:
        return [f"{where} has an unsupported or indeterminate runner"]
    return [f"{where} adds a route outside the reviewed inventory"]


def _extra_route_errors(documents: dict[str, Document]) -> list[str]:
    """Collect errors for jobs that are not part of the known route inventory."""
    return [
        error
        for name, document in documents.items()
        for job_id, job in jobs(name, document).items()
        if (name, job_id) not in KNOWN_ROUTES
        for error in _job_route_errors(name, job_id, job)
    ]


def guide_errors(guide: str) -> list[str]:
    """Require the developers' guide to document the supported-target boundary."""
    text = " ".join(guide.split())
    required = (
        (
            "native Linux architectures",
            "On native Linux x86_64 and aarch64, development",
        ),
        (
            "cross-host behaviour",
            (
                "Cargo's target table also applies to direct cross builds to "
                "Linux targets from another host."
            ),
        ),
        (
            "unsupported boundary",
            "That cross-host development route is unsupported because",
        ),
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
    route_errors = [error for route in routes for error in route(documents)]
    return route_errors + _extra_route_errors(documents) + guide_errors(guide)
