"""Check direct workflow-step linker setup before Linux test suites."""

import dataclasses
import typing as typ

if typ.TYPE_CHECKING:
    import collections.abc as cabc

SETUP_RUST: typ.Final[str] = "leynos/shared-actions/.github/actions/setup-rust"
_SETUP_RUST_REF_PARTS = ("2ddf19b3fd", "52c0f1089d", "b0d57b015f", "859b80ab67")
SETUP_RUST_REF: typ.Final[str] = f"{SETUP_RUST}@{''.join(_SETUP_RUST_REF_PARTS)}"
LINKER_VERSION: typ.Final[str] = "2.41.0"
_MISSING_WRAPPER_DIAGNOSTIC: typ.Final[str] = (
    "no unconditional make install-build-tools step occurs before the suite"
)


@dataclasses.dataclass(frozen=True, slots=True)
class _StepCandidate:
    """Keep candidate position and validation findings together.

    Examples
    --------
    >>> _StepCandidate(2, ("invalid",)).index
    2
    """

    index: int
    problems: tuple[str, ...]


@dataclasses.dataclass(frozen=True, slots=True)
class _CandidatePolicy:
    """Pair one installer's selector, validation and diagnostic rules."""

    is_candidate: cabc.Callable[[dict[str, object]], bool]
    candidate_problems: cabc.Callable[[dict[str, object]], list[str]]
    problems: cabc.Callable[[list[_StepCandidate], int], list[str]]


def _continues_on_error(mapping: dict[str, object]) -> bool:
    """Treat an expression or any value other than literal false as unsafe."""
    return mapping.get("continue-on-error", False) is not False


def _candidate_steps(
    steps: list[dict[str, object]], policy: _CandidatePolicy
) -> list[_StepCandidate]:
    """Collect indexed candidates and their policy findings.

    Returns
    -------
    list[_StepCandidate]
        Candidate steps in source order with ordered validation findings.

    Examples
    --------
    >>> _candidate_steps([], _SETUP_RUST_POLICY)
    []
    """
    return [
        _StepCandidate(index, tuple(policy.candidate_problems(step)))
        for index, step in enumerate(steps)
        if policy.is_candidate(step)
    ]


def _has_valid_candidate_before(
    candidates: list[_StepCandidate], suite_index: int
) -> bool:
    """Return whether any valid installer candidate precedes the suite.

    Returns
    -------
    bool
        Whether a candidate with no validation findings appears before the suite.

    Examples
    --------
    >>> _has_valid_candidate_before([_StepCandidate(0, ())], 1)
    True
    """
    return any(
        candidate.index < suite_index and not candidate.problems
        for candidate in candidates
    )


def _installer_problem_messages(
    candidates: list[_StepCandidate], suite_index: int
) -> list[str]:
    """Collect ordered and de-duplicated setup-rust findings.

    Returns
    -------
    list[str]
        Setup input findings followed by missing or late-install findings.

    Examples
    --------
    >>> _installer_problem_messages([], 0)
    ['no pinned linker installer occurs before the suite']
    """
    problems = [problem for candidate in candidates for problem in candidate.problems]
    if any(
        candidate.index >= suite_index and not candidate.problems
        for candidate in candidates
    ):
        problems.append("the pinned linker installer must run before the suite")
    if not candidates:
        problems.append("no pinned linker installer occurs before the suite")
    return list(dict.fromkeys(problems))


def _candidate_step_violations(
    where: str,
    steps: list[dict[str, object]],
    suite_index: int,
    policy: _CandidatePolicy,
) -> list[str]:
    """Apply one candidate policy to the shared before-suite contract.

    Returns
    -------
    list[str]
        Findings prefixed with the workflow location, or an empty list.

    Examples
    --------
    >>> _candidate_step_violations("job", [], 0, _SETUP_RUST_POLICY)
    ['job no pinned linker installer occurs before the suite']
    """
    candidates = _candidate_steps(steps, policy)
    if _has_valid_candidate_before(candidates, suite_index):
        return []
    problems = policy.problems(candidates, suite_index)
    return [f"{where} {problem}" for problem in dict.fromkeys(problems)]


def _is_wrapper_candidate(step: dict[str, object]) -> bool:
    """Recognize standalone Make build-tool installer steps.

    Returns
    -------
    bool
        Whether the exact unconditional installer command is present.

    Examples
    --------
    >>> _is_wrapper_candidate({"run": "make install-build-tools"})
    True
    """
    run = step.get("run")
    return isinstance(run, str) and run.strip() == "make install-build-tools"


def _wrapper_input_problems(step: dict[str, object]) -> list[str]:
    """Collect condition and failure-handling findings for one Make installer.

    Returns
    -------
    list[str]
        Condition then failure-handling findings, when present.

    Examples
    --------
    >>> _wrapper_input_problems({})
    []
    """
    problems: list[str] = []
    if "if" in step:
        problems.append("make install-build-tools step must not have an if condition")
    if _continues_on_error(step):
        problems.append("make install-build-tools step must not continue on error")
    return problems


def _wrapper_candidate_problems(
    candidates: list[_StepCandidate], suite_index: int
) -> list[str]:
    """Collect findings for candidates, or report a missing installer.

    Returns
    -------
    list[str]
        Ordered wrapper findings for the candidates.

    Examples
    --------
    >>> _wrapper_candidate_problems([], 0)
    ['no unconditional make install-build-tools step occurs before the suite']
    """
    if not candidates:
        return [_MISSING_WRAPPER_DIAGNOSTIC]
    return [
        problem
        for candidate in candidates
        for problem in _wrapper_step_problems(candidate, suite_index)
    ]


def _wrapper_step_problems(
    candidate: _StepCandidate, suite_index: int
) -> list[str]:
    """Add the ordering diagnostic to one wrapper candidate's findings.

    Returns
    -------
    list[str]
        Ordered diagnostics for this installer step.

    Examples
    --------
    >>> _wrapper_step_problems(_StepCandidate(1, ()), 0)
    ['make install-build-tools must run before the suite']
    """
    problems = list(candidate.problems)
    if candidate.index >= suite_index:
        problems.append("make install-build-tools must run before the suite")
    return problems


def _is_setup_rust_candidate(step: dict[str, object]) -> bool:
    """Recognize steps that may own the pinned linker installation.

    Returns
    -------
    bool
        Whether the step uses setup-rust or supplies its installer input.

    Examples
    --------
    >>> _is_setup_rust_candidate({"with": {"install-mold": True}})
    True
    """
    uses = step.get("uses")
    inputs = step.get("with")
    return (isinstance(uses, str) and SETUP_RUST in uses) or (
        isinstance(inputs, dict) and "install-mold" in inputs
    )


def _setup_rust_problems(step: dict[str, object]) -> list[str]:
    """Validate setup-rust identity, inputs and unconditional execution.

    Returns
    -------
    list[str]
        Ordered setup and execution diagnostics.

    Examples
    --------
    >>> _setup_rust_problems({})
    ['must use the pinned setup-rust linker installer']
    """
    uses, inputs = step.get("uses"), step.get("with")
    if not isinstance(uses, str) or not isinstance(inputs, dict):
        return ["must use the pinned setup-rust linker installer"]
    problems = _setup_rust_input_problems(uses, inputs)
    problems.extend(_setup_rust_execution_problems(step))
    return problems


def _setup_rust_execution_problems(step: dict[str, object]) -> list[str]:
    """Report conditional or soft-failing setup-rust execution.

    Returns
    -------
    list[str]
        Execution findings in diagnostic order.

    Examples
    --------
    >>> _setup_rust_execution_problems({})
    []
    """
    problems: list[str] = []
    if "if" in step:
        problems.append("the pinned linker installer must not have an if condition")
    if _continues_on_error(step):
        problems.append("the pinned linker installer must not continue on error")
    return problems


def _setup_rust_input_problems(uses: str, inputs: dict[str, object]) -> list[str]:
    """Check the pinned setup-rust action and linker inputs.

    Returns
    -------
    list[str]
        Action identity, linker enablement and version findings in order.

    Examples
    --------
    >>> _setup_rust_input_problems("other", {})[0]
    'must use the approved pinned setup-rust action'
    """
    return [
        problem
        for problem in (
            _setup_rust_action_problem(uses),
            _setup_rust_linker_problem(inputs),
            _setup_rust_version_problem(inputs),
        )
        if problem is not None
    ]


def _setup_rust_action_problem(uses: str) -> str | None:
    """Return the action-pin diagnostic when the selected ref is unsupported.

    Returns
    -------
    str | None
        The action-pin diagnostic, or None when the ref is approved.

    Examples
    --------
    >>> _setup_rust_action_problem("other")
    'must use the approved pinned setup-rust action'
    """
    if uses != SETUP_RUST_REF:
        return "must use the approved pinned setup-rust action"
    return None


def _setup_rust_linker_problem(inputs: dict[str, object]) -> str | None:
    """Return the install-mold diagnostic when linker setup is disabled.

    Returns
    -------
    str | None
        The linker diagnostic, or None when installation is enabled.

    Examples
    --------
    >>> _setup_rust_linker_problem({})
    'must enable setup-rust install-mold'
    """
    enabled = inputs.get("install-mold")
    if enabled is not True and enabled != "true":
        return "must enable setup-rust install-mold"
    return None


def _setup_rust_version_problem(inputs: dict[str, object]) -> str | None:
    """Return a diagnostic when a supplied mould version differs from the pin.

    Returns
    -------
    str | None
        The version diagnostic, or None when the version is pinned.

    Examples
    --------
    >>> _setup_rust_version_problem({"mold-version": "1.0"})
    'must install pinned linker version 2.41.0'
    """
    version = inputs.get("mold-version")
    if version is not None and str(version) != LINKER_VERSION:
        return f"must install pinned linker version {LINKER_VERSION}"
    return None


_SETUP_RUST_POLICY = _CandidatePolicy(
    _is_setup_rust_candidate,
    _setup_rust_problems,
    _installer_problem_messages,
)
_MAKE_WRAPPER_POLICY = _CandidatePolicy(
    _is_wrapper_candidate,
    _wrapper_input_problems,
    _wrapper_candidate_problems,
)
_STEP_POLICIES = (_SETUP_RUST_POLICY, _MAKE_WRAPPER_POLICY)


def step_provisioning_violations(
    where: str, steps: list[dict[str, object]], suite_index: int
) -> list[str]:
    """Apply setup-rust then Make-wrapper provisioning checks to suite steps.

    Returns
    -------
    list[str]
        Ordered diagnostics from both step provisioning policies.

    Examples
    --------
    >>> step_provisioning_violations("job", [], 0)[0]
    'job no pinned linker installer occurs before the suite'
    """
    return [
        problem
        for policy in _STEP_POLICIES
        for problem in _candidate_step_violations(where, steps, suite_index, policy)
    ]
