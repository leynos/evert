"""Hold PR and publisher coverage to the same pinned Rust setup action.

This module owns only toolchain setup parity for the two coverage jobs. The
shared action revision fixes its installed component set; its caller inputs
select the repository toolchain and pinned linker installation.
"""

import re
import typing as typ

from workflow_contract_support import (
    Document,
    Step,
    calls,
    continues_on_error,
    holding_job,
)

SETUP_ACTION: typ.Final[str] = "leynos/shared-actions/.github/actions/setup-rust"
FULL_SHA: typ.Final[re.Pattern[str]] = re.compile(r"@[0-9a-f]{40}$")


def _setup(
    name: str, document: Document, coverage: Step
) -> tuple[Step | None, list[str]]:
    """Find the coverage job's sole unconditional setup before compilation."""
    held = typ.cast(
        "list[Step]", holding_job(name, document, coverage).get("steps", [])
    )
    found = [step for step in held if calls(step, SETUP_ACTION)]
    if len(found) != 1:
        return None, [f"{name} coverage needs one setup-rust step"]
    setup = found[0]
    problems = _setup_order_problems(name, held, setup, coverage)
    problems.extend(_setup_step_problems(name, setup))
    return setup, problems


def _setup_order_problems(
    name: str, held: list[Step], setup: Step, coverage: Step
) -> list[str]:
    """Report setup ordering errors before coverage and build-tool installation.

    Returns
    -------
    list[str]
        Ordering diagnostics in coverage-then-installer order.

    Examples
    --------
    >>> setup = {"uses": "setup-rust"}
    >>> coverage = {"uses": "generate-coverage"}
    >>> _setup_order_problems("ci.yml", [setup, coverage], setup, coverage)
    ['ci.yml coverage needs one `make install-build-tools` step']
    """
    problems = []
    if held.index(setup) > held.index(coverage):
        problems.append(f"{name} setup-rust must precede coverage")
    installers = [
        step for step in held if step.get("run") == "make install-build-tools"
    ]
    if len(installers) != 1:
        problems.append(f"{name} coverage needs one `make install-build-tools` step")
    elif held.index(setup) > held.index(installers[0]):
        problems.append(f"{name} setup-rust must precede build-tool installation")
    return problems


def _setup_step_problems(name: str, setup: Step) -> list[str]:
    """Report conditional, mutable-pin, and linker-input setup violations.

    Returns
    -------
    list[str]
        Applicable setup-step diagnostics in their original order.

    Examples
    --------
    >>> _setup_step_problems("ci.yml", {"uses": "setup-rust@main"})
    [
    ...     'ci.yml setup-rust must use a full-SHA pin',
    ...     'ci.yml setup-rust must install pinned linker',
    ... ]
    """
    problems = []
    if "if" in setup or continues_on_error(setup):
        problems.append(f"{name} setup-rust must be unconditional and binding")
    if not FULL_SHA.search(str(setup.get("uses", ""))):
        problems.append(f"{name} setup-rust must use a full-SHA pin")
    inputs = setup.get("with")
    if not isinstance(inputs, dict) or inputs.get("install-mold") != "true":
        problems.append(f"{name} setup-rust must install pinned linker")
    return problems


def toolchain_violations(
    documents: dict[str, Document],
    publisher: str,
    trunk: Step,
    lanes: list[tuple[str, Document, Step]],
) -> list[str]:
    """Report toolchain/action/component selection drift between coverage jobs.

    The same full-SHA action and whole input mapping give both jobs the same
    component set and toolchain selection. The repository's toolchain file is
    checked out by both jobs; the caller must install the pinned linker before
    coverage.

    Returns
    -------
    list[str]
        One message per drift or setup problem; empty when the jobs agree.
    """
    main_setup, found = _setup(publisher, documents[publisher], trunk)
    for name, document, coverage in lanes:
        lane_setup, problems = _setup(name, document, coverage)
        found.extend(problems)
        if _setups_differ(main_setup, lane_setup):
            found.append(
                f"{name} setup-rust toolchain selection differs from {publisher}"
            )
    return found


def _setups_differ(main_setup: Step | None, lane_setup: Step | None) -> bool:
    """Tell whether two present setup steps pin different actions or inputs."""
    if main_setup is None or lane_setup is None:
        return False
    return any(main_setup.get(key) != lane_setup.get(key) for key in ("uses", "with"))
