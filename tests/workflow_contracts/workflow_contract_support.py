"""Strict YAML helpers for Evert's local workflow contract tests.

This module is private to ``tests/workflow_contracts``. It owns file reading
and shape access only; build, coverage, and route policies belong in their
respective ``*_rules`` modules.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast

import yaml

Document = dict[object, object]
Step = dict[str, object]
Workflow = dict[str, Document]
WORKFLOW_DIRECTORY = Path(__file__).resolve().parents[2] / ".github" / "workflows"


class WorkflowError(ValueError):
    """Raised when a workflow cannot be read or has an invalid shape."""


class _StrictLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects repeated mapping keys."""


def _construct_mapping(loader: _StrictLoader, node: yaml.MappingNode) -> Document:
    """Construct one mapping while refusing ambiguous duplicate keys."""
    seen: set[object] = set()
    for key_node, _ in node.value:
        key = loader.construct_object(key_node, deep=True)
        if key in seen:
            raise WorkflowError(f"duplicate key {key!r} at {key_node.start_mark}")
        seen.add(key)
    return cast(Document, loader.construct_mapping(node, deep=True))


_StrictLoader.add_constructor(_StrictLoader.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_workflow(name: str, text: str) -> Document:
    """Parse one workflow mapping and name syntax errors with its file."""
    loader = _StrictLoader(text)
    try:
        document = loader.get_single_data()
    except yaml.YAMLError as error:
        raise WorkflowError(f"{name}: not valid YAML: {error}") from error
    except WorkflowError as error:
        raise WorkflowError(f"{name}: {error}") from error
    finally:
        loader.dispose()
    if not isinstance(document, dict):
        raise WorkflowError(f"{name}: a workflow must be a mapping")
    return cast(Document, document)


def read_workflows(directory: Path = WORKFLOW_DIRECTORY) -> Workflow:
    """Read every YAML workflow afresh, refusing an empty or invalid set."""
    try:
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.suffix.casefold() in {".yml", ".yaml"}
        )
    except OSError as error:
        raise WorkflowError(f"cannot list workflows in {directory}: {error}") from error
    if not paths:
        raise WorkflowError(f"no workflows were read from {directory}")

    workflows: Workflow = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            raise WorkflowError(f"{path.name}: cannot be read as UTF-8: {error}") from error
        workflows[path.name] = load_workflow(path.name, text)
    return workflows


def fresh_documents(directory: Path = WORKFLOW_DIRECTORY) -> Workflow:
    """Return a new mutable copy of every parsed workflow for one test."""
    return read_workflows(directory)


def jobs(name: str, document: Document) -> dict[str, dict[str, object]]:
    """Return jobs after confirming every job body is a mapping."""
    found = document.get("jobs")
    if not isinstance(found, dict) or not all(
        isinstance(job, dict) for job in found.values()
    ):
        raise WorkflowError(f"{name}: `jobs` must map job names to mappings")
    return cast(dict[str, dict[str, object]], found)


def steps(name: str, document: Document) -> Iterator[Step]:
    """Yield validated step mappings in workflow order."""
    for job in jobs(name, document).values():
        raw_steps = job.get("steps", [])
        if not isinstance(raw_steps, list):
            raise WorkflowError(f"{name}: a job's `steps` must be a list")
        for step in raw_steps:
            if not isinstance(step, dict):
                raise WorkflowError(f"{name}: a step must be a mapping")
            yield cast(Step, step)


def calls(step: Step, action: str) -> bool:
    """Return whether a step names the requested action, ignoring its ref."""
    uses = step.get("uses")
    return isinstance(uses, str) and uses.partition("@")[0].casefold() == action.casefold()


def continues_on_error(mapping: dict[str, object]) -> bool:
    """Treat every value except literal false or absence as a soft failure."""
    return mapping.get("continue-on-error", False) is not False


def triggers(name: str, document: Document) -> dict[str, object]:
    """Return workflow events, normalizing PyYAML's YAML 1.1 ``on`` key."""
    spellings = [key for key in ("on", True) if key in document]
    if len(spellings) != 1:
        raise WorkflowError(f"{name}: declares `on` {len(spellings)} times, not once")
    match document[spellings[0]]:
        case str() as event:
            return {event: None}
        case list() as events if all(isinstance(event, str) for event in events):
            return dict.fromkeys(cast(list[str], events))
        case dict() as events:
            return {str(event): value for event, value in events.items()}
        case other:
            raise WorkflowError(f"{name}: cannot read the trigger {other!r}")


def holding_job(name: str, document: Document, step: Step) -> dict[str, object]:
    """Return the job that contains this exact step object."""
    return next(
        job
        for job in jobs(name, document).values()
        if any(held is step for held in cast(list[object], job.get("steps", [])))
    )
