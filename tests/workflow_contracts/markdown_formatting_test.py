"""Hold the Markdown tools in CI before the checks that use them."""

from __future__ import annotations

import copy
import re
from pathlib import Path

import pytest
import yaml

WORKFLOW_PATH = (
    Path(__file__).resolve().parents[2] / ".github" / "workflows" / "ci.yml"
)
INSTALLER = re.compile(
    r"^leynos/shared-actions/\.github/actions/install-mdtablefix@[0-9a-f]{40}$"
)
MARKDOWNLINT = re.compile(
    r"^DavidAnson/markdownlint-cli2-action@[0-9a-f]{40}$"
)


def _steps() -> list[dict[str, object]]:
    """Load the CI steps that own Markdown formatting and linting."""
    workflow = yaml.safe_load(WORKFLOW_PATH.read_text(encoding="utf-8"))
    return workflow["jobs"]["build-test"]["steps"]


def _violations(steps: list[dict[str, object]]) -> list[str]:
    """Report missing or weakened CI wiring for this repository's Make gate."""
    findings: list[str] = []
    checks = [
        index
        for index, step in enumerate(steps)
        if step.get("run") == "make check-fmt"
    ]
    if len(checks) != 1:
        findings.append("CI must run make check-fmt once")
    else:
        formatter = steps[checks[0]]
        if "if" in formatter or formatter.get("continue-on-error") is not None:
            findings.append("make check-fmt must be unconditional and binding")

    installers = [
        (index, step)
        for index, step in enumerate(steps)
        if str(step.get("uses", "")).startswith(
            "leynos/shared-actions/.github/actions/install-mdtablefix@"
        )
    ]
    if len(installers) != 1:
        findings.append("CI must install mdtablefix once")
    else:
        index, step = installers[0]
        if not INSTALLER.fullmatch(str(step.get("uses", ""))):
            findings.append("mdtablefix installer must use a full commit SHA")
        inputs = step.get("with")
        if not isinstance(inputs, dict) or inputs.get("version") != "0.6.0":
            findings.append("mdtablefix installer must request version 0.6.0")
        if "if" in step or step.get("continue-on-error") is not None:
            findings.append("mdtablefix installer must be unconditional and binding")
        if checks and index >= checks[0]:
            findings.append("mdtablefix installer must precede make check-fmt")

    linters = [
        step
        for step in steps
        if str(step.get("uses", "")).startswith("DavidAnson/markdownlint-cli2-action@")
    ]
    if len(linters) != 1:
        findings.append("CI must run the markdownlint action once")
    else:
        step = linters[0]
        if not MARKDOWNLINT.fullmatch(str(step.get("uses", ""))):
            findings.append("markdownlint action must use a full commit SHA")
        inputs = step.get("with")
        if not isinstance(inputs, dict) or inputs.get("globs") != "**/*.md":
            findings.append("markdownlint action must select **/*.md")
        if "if" in step or step.get("continue-on-error") is not None:
            findings.append("markdownlint action must be unconditional and binding")
    return findings


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
    if mutation == "remove-installer":
        steps.pop(installer_index)
    elif mutation == "late-installer":
        steps.insert(formatter_index + 1, steps.pop(installer_index))
    elif mutation == "conditional-installer":
        steps[installer_index]["if"] = "github.event_name == 'push'"
    elif mutation == "soft-installer":
        steps[installer_index]["continue-on-error"] = True
    elif mutation == "narrow-globs":
        linter["with"]["globs"] = "docs/**/*.md"
    elif mutation == "remove-formatter":
        steps.pop(formatter_index)
    elif mutation == "soft-formatter":
        steps[formatter_index]["continue-on-error"] = True
    elif mutation == "conditional-formatter":
        steps[formatter_index]["if"] = "github.event_name == 'push'"
    assert _violations(steps), f"the {mutation} mutation escaped the contract"
