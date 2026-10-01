"""Discover lint paths in workflows and check their Whitaker provisioning."""

import dataclasses
import re
import tomllib
import typing as typ
from pathlib import Path

from workflow_contract_support import calls, continues_on_error, steps

if typ.TYPE_CHECKING:
    from workflow_contract_support import Document, Step

ACTION = "leynos/shared-actions/.github/actions/install-whitaker"
ACTION_REF = "6dea5677a84fec60ca51b07202570e3af12ffdb4"
ACTION_USE = f"{ACTION}@{ACTION_REF}"
FORBIDDEN_INPUTS = {"allow-suite-pin", "installer-version", "suite-version"}
TARGET = "x86_64-unknown-linux-gnu"
DIRECT_SETUP = re.compile(
    r"\bwhitaker-installer\b|\bcargo-dylint\b|"
    r"\bcargo\s+(?:install|binstall)\b[^\n]*(?:whitaker|dylint)",
    re.IGNORECASE,
)
MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"
MAKE_TARGET = re.compile(r"^[A-Za-z0-9_-]+$")
_PATH_OPTIONS = {"-C", "--directory", "-f", "--file"}
_DIRECTORY_OPTIONS = {"-C", "--directory"}
_HARMLESS_FLAGS = {"-B", "--no-print-directory"}
_UNSAFE_VARIABLES = {"MAKEFLAGS", "MAKEFILES"}
_LOCAL_MAKEFILES = {"Makefile", "./Makefile"}


@dataclasses.dataclass(frozen=True, slots=True)
class _MakeGraph:
    """Local Make prerequisites plus the targets that reach `lint`.

    A prerequisite set of `None` marks a target whose prerequisites contain
    Make variables the parser cannot resolve, so reaching it stays uncertain.
    """

    lint_targets: set[str]
    uncertain_targets: set[str]
    graph: dict[str, set[str] | None]
    default_target: str


def _read_makefile() -> str:
    """Read the local Makefile with line continuations folded away."""
    try:
        return MAKEFILE.read_text(encoding="utf-8").replace("\\\n", " ")
    except OSError as error:
        message = f"cannot inspect local Makefile {MAKEFILE}: {error}"
        raise ValueError(message) from error


def _is_skippable(line: str) -> bool:
    """Report whether a Makefile line cannot declare a target."""
    return any((line.startswith("\t"), not line.strip(), line.lstrip().startswith("#")))


def _parse_declaration(line: str) -> tuple[str, list[str]] | None:
    """Split a `target: prerequisites` line, or return None for other lines."""
    if _is_skippable(line):
        return None
    declaration = line.split("##", 1)[0].split("#", 1)[0].strip()
    match = re.fullmatch(r"([A-Za-z0-9_-]+)\s*:\s*(.*)", declaration)
    if match is None:
        return None
    target, prerequisite_text = match.groups()
    return target, prerequisite_text.split()


def _has_unresolved_variable(prerequisites: list[str]) -> bool:
    """Report whether a prerequisite is a Make variable expansion."""
    return any("$" in item and "/" not in item for item in prerequisites)


def _literal_targets(prerequisites: list[str]) -> set[str]:
    """Keep the prerequisites that are plain local target names."""
    return {
        item for item in prerequisites if item != "|" and MAKE_TARGET.fullmatch(item)
    }


def _build_graph(source: str) -> tuple[dict[str, set[str] | None], str | None]:
    """Build the prerequisite graph and find the default target."""
    graph: dict[str, set[str] | None] = {}
    default_target: str | None = None
    for line in source.splitlines():
        declaration = _parse_declaration(line)
        if declaration is None:
            continue
        target, prerequisites = declaration
        if default_target is None:
            default_target = target
        previous = graph.get(target, set())
        if previous is None or _has_unresolved_variable(prerequisites):
            graph[target] = None
        else:
            graph[target] = previous | _literal_targets(prerequisites)
    return graph, default_target


def _close_over(graph: dict[str, set[str] | None], seeds: set[str]) -> set[str]:
    """Grow `seeds` with every target that depends on a member until stable."""
    closure = set(seeds)
    while True:
        grown = closure | {
            target
            for target, prerequisites in graph.items()
            if prerequisites is not None and prerequisites.intersection(closure)
        }
        if grown == closure:
            return closure
        closure = grown


def _make_lint_targets() -> _MakeGraph | None:
    """Resolve Make targets whose local prerequisite path includes `lint`."""
    graph, default_target = _build_graph(_read_makefile())
    if "lint" not in graph or default_target is None:
        return None
    unresolved_roots = {
        t for t, prerequisites in graph.items() if prerequisites is None
    }
    return _MakeGraph(
        lint_targets=_close_over(graph, {"lint"}),
        uncertain_targets=_close_over(graph, unresolved_roots),
        graph=graph,
        default_target=default_target,
    )


def _redirects_make(option: str, value: str) -> bool:
    """Report whether a path option points Make away from the local Makefile."""
    if option in _DIRECTORY_OPTIONS:
        return value != "."
    return value not in _LOCAL_MAKEFILES


def _is_unresolvable_option(argument: str) -> bool:
    """Report whether an argument changes Make behaviour in ways we cannot trace."""
    if argument.startswith("-"):
        return True
    return "=" in argument and argument.split("=", 1)[0] in _UNSAFE_VARIABLES


def _parse_make_arguments(arguments: list[str]) -> tuple[str | None, bool]:
    """Return the selected target and whether the invocation is unresolvable."""
    tokens = iter(arguments)
    for argument in tokens:
        if argument in _PATH_OPTIONS:
            value = next(tokens, None)
            if value is None or _redirects_make(argument, value):
                return None, True
        elif argument in _HARMLESS_FLAGS:
            continue
        elif _is_unresolvable_option(argument):
            return None, True
        elif "=" not in argument:
            return argument, False
    return None, False


def _target_status(selected: str, make_graph: _MakeGraph) -> bool | None:
    """Classify a target as reaching lint (True), unknown (None) or not (False)."""
    if selected in make_graph.lint_targets:
        return True
    if selected in make_graph.uncertain_targets or selected not in make_graph.graph:
        return None
    return False


def make_lint_step_status(run: str) -> bool | None:
    """Recognize direct lint calls and literal local paths such as `make all`."""
    make_graph = _make_lint_targets()
    if make_graph is None:
        return None if re.search(r"\bmake\b", run) else False
    found_lint = False
    unresolved = False
    for invocation in re.finditer(r"\bmake\b([^\n;&|]*)", run.replace("\\\n", " ")):
        target, is_unresolved = _parse_make_arguments(invocation.group(1).split())
        # Once any invocation is unresolvable, later ones are not trusted either.
        unresolved = unresolved or is_unresolved
        if unresolved:
            continue
        status = _target_status(target or make_graph.default_target, make_graph)
        found_lint = found_lint or status is True
        unresolved = status is None
    if found_lint:
        return True
    return None if unresolved else False


def _is_step_list(raw_steps: object) -> bool:
    """Report whether `raw_steps` is a list made only of step mappings."""
    return isinstance(raw_steps, list) and all(isinstance(s, dict) for s in raw_steps)


def _classify_step(step: Step) -> tuple[bool, bool]:
    """Return whether a step is on the lint path and whether that is uncertain."""
    command = step.get("run")
    if command is None:
        return False, False
    if not isinstance(command, str):
        return True, True
    route = make_lint_step_status(command)
    return route is not False, route is None


def workflow_lint_steps(job: dict[str, object]) -> tuple[list[Step], list[int], bool]:
    """Find direct or literal Makefile paths to lint; mark unknown paths."""
    raw_steps = job.get("steps")
    if not isinstance(raw_steps, list) or not _is_step_list(raw_steps):
        return [], [], True
    classified = [_classify_step(step) for step in raw_steps]
    lint_indices = [index for index, (on_path, _) in enumerate(classified) if on_path]
    return raw_steps, lint_indices, any(uncertain for _, uncertain in classified)


def action_steps(steps_to_check: list[Step]) -> list[Step]:
    """Find steps that call the shared Whitaker installer action."""
    return [step for step in steps_to_check if calls(step, ACTION)]


def _development_cranelift_default() -> bool | None:
    """Read Cranelift selection from the Linux target's committed Cargo flags."""
    config_path = Path(__file__).resolve().parents[2] / ".cargo" / "config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    target_config = config.get("target", {}).get(TARGET, {})
    rustflags = target_config.get("rustflags")
    if not isinstance(rustflags, list) or not all(
        isinstance(flag, str) for flag in rustflags
    ):
        return None
    return "-Zcodegen-backend=cranelift" in rustflags


def _boolean_input(value: object) -> bool | None:
    """Read YAML booleans and quoted GitHub action boolean inputs."""
    match value:
        case bool():
            return value
        case str():
            return {"true": True, "false": False}.get(value.casefold())
        case _:
            return None


def _action_input_violations(where: str, inputs: dict[object, object]) -> list[str]:
    """Reject forbidden action inputs and a Cranelift choice that drifts."""
    violations = [
        f"{where} Whitaker action must not set {forbidden}"
        for forbidden in sorted(FORBIDDEN_INPUTS.intersection(inputs))
    ]
    selected = _boolean_input(inputs.get("cranelift", False))
    expected = _development_cranelift_default()
    if expected is None:
        violations.append("cannot determine the Linux development Cranelift default")
    elif selected is not expected:
        violations.append(
            "Whitaker action cranelift input must match the Linux development default"
        )
    return violations


def _action_step_violations(where: str, action_step: Step) -> list[str]:
    """Check one Whitaker action step for pinning, conditions and inputs."""
    violations: list[str] = []
    if action_step.get("uses") != ACTION_USE:
        violations.append(f"{where} must pin the approved Whitaker action SHA")
    if "if" in action_step:
        violations.append(f"{where} Whitaker action must be unconditional")
    if continues_on_error(action_step):
        violations.append(f"{where} Whitaker action must not continue on error")
    inputs = action_step.get("with", {})
    if isinstance(inputs, dict):
        violations.extend(_action_input_violations(where, inputs))
    else:
        violations.append(f"{where} Whitaker action inputs must be a mapping")
    return violations


def _lint_step_violations(where: str, lint_step: Step) -> list[str]:
    """Require a lint-path step to be unconditional and hard-failing."""
    violations: list[str] = []
    if "if" in lint_step:
        violations.append(f"{where} lint path must be unconditional")
    if continues_on_error(lint_step):
        violations.append(f"{where} lint path must not continue on error")
    return violations


def lint_job_action_violations(
    where: str, job_steps: list[Step], lint_indices: list[int], route_name: str
) -> list[str]:
    """Require one unconditional, correctly pinned action before the lint path."""
    violations: list[str] = []
    actions = action_steps(job_steps)
    if len(actions) != 1:
        violations.append(f"{where} requires exactly one shared Whitaker action")
    for action_step in actions:
        violations.extend(_action_step_violations(where, action_step))
    for index in lint_indices:
        violations.extend(_lint_step_violations(where, job_steps[index]))
    if len(actions) == 1 and lint_indices:
        action_index = job_steps.index(actions[0])
        if action_index >= min(lint_indices):
            violations.append(f"{where} Whitaker action must run before {route_name}")
    return violations


def direct_setup_violations(documents: dict[str, Document]) -> list[str]:
    """Reject run steps that provision Whitaker or cargo-dylint directly."""
    return [
        f"{name} contains direct Whitaker or cargo-dylint provisioning"
        for name, workflow in documents.items()
        for step in steps(name, workflow)
        if isinstance(step.get("run"), str) and DIRECT_SETUP.search(step["run"])
    ]
