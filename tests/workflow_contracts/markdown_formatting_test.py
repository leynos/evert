"""Hold the Markdown tools in CI before the checks that use them."""

import copy
import re
from pathlib import Path

import pytest
import yaml
from workflow_contract_support import mapping_at

WORKFLOW_PATH = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
INSTALLER = re.compile(
    r"^leynos/shared-actions/\.github/actions/install-mdtablefix@[0-9a-f]{40}$"
)
MARKDOWNLINT = re.compile(r"^DavidAnson/markdownlint-cli2-action@[0-9a-f]{40}$")


def _steps() -> list[dict[str, object]]:
    """Load the CI steps that own Markdown formatting and linting."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow["jobs"]["build-test"]["steps"]


def _is_unconditional(step: dict[str, object]) -> bool:
    """Return whether a step has neither a condition nor soft-failure."""
    return "if" not in step and step.get("continue-on-error") is None


def _formatter_indexes(steps: list[dict[str, object]]) -> list[int]:
    """Return the positions of the steps that run the formatting gate."""
    return [
        index for index, step in enumerate(steps) if step.get("run") == "make check-fmt"
    ]


def _formatter_findings(steps: list[dict[str, object]], checks: list[int]) -> list[str]:
    """Report a missing, repeated or weakened ``make check-fmt`` step."""
    if len(checks) != 1:
        return ["CI must run make check-fmt once"]
    if not _is_unconditional(steps[checks[0]]):
        return ["make check-fmt must be unconditional and binding"]
    return []


def _installer_findings(steps: list[dict[str, object]], checks: list[int]) -> list[str]:
    """Report a missing, unpinned, late or weakened mdtablefix installer."""
    installers = [
        (index, step)
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith(
            "leynos/shared-actions/.github/actions/install-mdtablefix@"
        )
    ]
    if len(installers) != 1:
        return ["CI must install mdtablefix once"]
    index, step = installers[0]
    inputs = step.get("with")
    # Each entry is (condition that must hold, finding when it does not).
    expectations = [
        (
            INSTALLER.fullmatch(str(step.get("uses", ""))),
            "mdtablefix installer must use a full commit SHA",
        ),
        (
            isinstance(inputs, dict) and inputs.get("version") == "0.6.1",
            "mdtablefix installer must request version 0.6.1",
        ),
        (
            _is_unconditional(step),
            "mdtablefix installer must be unconditional and binding",
        ),
        (
            not checks or index < checks[0],
            "mdtablefix installer must precede make check-fmt",
        ),
    ]
    return [finding for holds, finding in expectations if not holds]


def _linter_findings(steps: list[dict[str, object]]) -> list[str]:
    """Report a missing, unpinned, narrowed or weakened markdownlint action."""
    linters = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("DavidAnson/markdownlint-cli2-action@")
    ]
    if len(linters) != 1:
        return ["CI must run the markdownlint action once"]
    step = linters[0]
    inputs = step.get("with")
    expectations = [
        (
            MARKDOWNLINT.fullmatch(str(step.get("uses", ""))),
            "markdownlint action must use a full commit SHA",
        ),
        (
            isinstance(inputs, dict) and inputs.get("globs") == "**/*.md",
            "markdownlint action must select **/*.md",
        ),
        (
            _is_unconditional(step),
            "markdownlint action must be unconditional and binding",
        ),
    ]
    return [finding for holds, finding in expectations if not holds]


def _violations(steps: list[dict[str, object]]) -> list[str]:
    """Report missing or weakened CI wiring for this repository's Make gate."""
    checks = _formatter_indexes(steps)
    return [
        *_formatter_findings(steps, checks),
        *_installer_findings(steps, checks),
        *_linter_findings(steps),
    ]


def test_ci_installs_and_runs_markdown_tools() -> None:
    """The CI job has an unconditional binary installer and action lint."""
    assert not (findings := _violations(_steps())), findings


@pytest.mark.parametrize(
    "mutation",
    [
        "remove-installer",
        "late-installer",
        "conditional-installer",
        "soft-installer",
        "narrow-globs",
        "remove-formatter",
        "soft-formatter",
        "conditional-formatter",
    ],
)
def test_ci_markdown_contract_rejects_drift(mutation: str) -> None:
    """Each change that would skip a required Markdown check is detected."""
    steps = copy.deepcopy(_steps())
    installer_index = next(
        index
        for index, step in enumerate(steps)
        if INSTALLER.fullmatch(str(step.get("uses", "")))
    )
    formatter_index = next(
        index for index, step in enumerate(steps) if step.get("run") == "make check-fmt"
    )
    linter = next(
        step for step in steps if MARKDOWNLINT.fullmatch(str(step.get("uses", "")))
    )
    mutations = {
        "remove-installer": lambda: steps.pop(installer_index),
        "late-installer": lambda: steps.insert(
            formatter_index + 1, steps.pop(installer_index)
        ),
        "conditional-installer": lambda: steps[installer_index].update({
            "if": "github.event_name == 'push'"
        }),
        "soft-installer": lambda: steps[installer_index].update({
            "continue-on-error": True
        }),
        "narrow-globs": lambda: mapping_at(linter, "with").update({
            "globs": "docs/**/*.md"
        }),
        "remove-formatter": lambda: steps.pop(formatter_index),
        "soft-formatter": lambda: steps[formatter_index].update({
            "continue-on-error": True
        }),
        "conditional-formatter": lambda: steps[formatter_index].update({
            "if": "github.event_name == 'push'"
        }),
    }
    mutations[mutation]()
    assert _violations(steps), f"the {mutation} mutation escaped the contract"
