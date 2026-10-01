"""Discover workflow steps whose local Make target graph reaches Whitaker."""

from __future__ import annotations

import re
from pathlib import Path

from workflow_contract_support import Step

MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"
MAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")


def _make_lint_targets() -> tuple[set[str], set[str], dict[str, set[str] | None], str | None] | None:
    """Resolve Make targets whose local prerequisite path includes `lint`."""
    try:
        source = MAKEFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    except OSError as error:
        raise ValueError(f"cannot inspect local Makefile {MAKEFILE}: {error}") from error

    graph: dict[str, set[str] | None] = {}
    default_target: str | None = None
    for line in source.splitlines():
        if line.startswith("\t") or not line.strip() or line.lstrip().startswith("#"):
            continue
        declaration = line.split("##", 1)[0].split("#", 1)[0].strip()
        match = re.fullmatch(r"([A-Za-z0-9_-]+)\s*:\s*(.*)", declaration)
        if match is None:
            continue
        target, prerequisite_text = match.groups()
        if default_target is None:
            default_target = target
        prerequisites = prerequisite_text.split()
        unresolved = any(
            "$" in prerequisite and "/" not in prerequisite
            for prerequisite in prerequisites
        )
        parsed = {
            item
            for item in prerequisites
            if item != "|" and MAKE_TARGET.fullmatch(item)
        }
        previous = graph.get(target, set())
        if previous is None or unresolved:
            graph[target] = None
        else:
            graph[target] = previous | parsed
    if "lint" not in graph or default_target is None:
        return None

    reachable, uncertain = {"lint"}, {
        target for target, prerequisites in graph.items() if prerequisites is None
    }
    while True:
        expanded_reachable = reachable | {
            target
            for target, prerequisites in graph.items()
            if prerequisites is not None and prerequisites.intersection(reachable)
        }
        expanded_uncertain = uncertain | {
            target
            for target, prerequisites in graph.items()
            if prerequisites is not None and prerequisites.intersection(uncertain)
        }
        if expanded_reachable == reachable and expanded_uncertain == uncertain:
            break
        reachable, uncertain = expanded_reachable, expanded_uncertain
    return reachable, uncertain, graph, default_target


def make_lint_step_status(run: str) -> bool | None:
    """Recognize direct lint calls and literal local paths such as `make all`."""
    make_targets = _make_lint_targets()
    if make_targets is None:
        return None if re.search(r"\bmake\b", run) else False
    lint_targets, uncertain_targets, graph, default_target = make_targets
    found_lint = False
    unresolved = False
    for invocation in re.finditer(r"\bmake\b([^\n;&|]*)", run.replace("\\\n", " ")):
        arguments = invocation.group(1).split()
        target: str | None = None
        index = 0
        while index < len(arguments):
            argument = arguments[index]
            if argument in {"-C", "--directory", "-f", "--file"}:
                index += 1
                if index == len(arguments):
                    unresolved = True
                    break
                value = arguments[index]
                if (argument in {"-C", "--directory"} and value != ".") or (
                    argument in {"-f", "--file"} and value not in {"Makefile", "./Makefile"}
                ):
                    unresolved = True
                    break
            elif argument in {"-B", "--no-print-directory"}:
                pass
            elif argument.startswith("-"):
                unresolved = True
                break
            elif "=" in argument:
                if argument.split("=", 1)[0] in {"MAKEFLAGS", "MAKEFILES"}:
                    unresolved = True
                    break
            else:
                target = argument
                break
            index += 1
        selected = target or default_target
        if unresolved:
            continue
        if selected == "lint" or selected in lint_targets:
            found_lint = True
        elif selected in uncertain_targets or selected not in graph:
            unresolved = True
    if found_lint:
        return True
    return None if unresolved else False


def workflow_lint_steps(job: dict[str, object]) -> tuple[list[Step], list[int], bool]:
    """Find direct or literal Makefile paths to lint; mark unknown paths."""
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list) or not all(isinstance(step, dict) for step in raw_steps):
        return [], [], True
    lint_indices: list[int] = []
    indeterminate = False
    for index, step in enumerate(raw_steps):
        command = step.get("run")
        if command is None:
            continue
        if not isinstance(command, str):
            lint_indices.append(index)
            indeterminate = True
            continue
        route = make_lint_step_status(command)
        if route is True:
            lint_indices.append(index)
        elif route is None:
            lint_indices.append(index)
            indeterminate = True
    return raw_steps, lint_indices, indeterminate
