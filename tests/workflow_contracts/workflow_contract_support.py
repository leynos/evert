"""Strict YAML helpers for Evert's local workflow contract tests.

This module is private to ``tests/workflow_contracts``. It owns file reading
and shape access only; build, coverage, and route policies belong in their
respective ``*_rules`` modules.
"""

import typing as typ
from pathlib import Path

import yaml

if typ.TYPE_CHECKING:
    import collections.abc as cabc

type Document = dict[object, object]
type Step = dict[str, object]
type Workflow = dict[str, Document]
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
            message = f"duplicate key {key!r} at {key_node.start_mark}"
            raise WorkflowError(message)
        seen.add(key)
    return typ.cast("Document", loader.construct_mapping(node, deep=True))


_StrictLoader.add_constructor(_StrictLoader.DEFAULT_MAPPING_TAG, _construct_mapping)


def load_workflow(name: str, text: str) -> Document:
    """Parse one workflow mapping and name syntax errors with its file."""
    loader = _StrictLoader(text)
    try:
        document = loader.get_single_data()
    except yaml.YAMLError as error:
        message = f"{name}: not valid YAML: {error}"
        raise WorkflowError(message) from error
    except WorkflowError as error:
        message = f"{name}: {error}"
        raise WorkflowError(message) from error
    finally:
        loader.dispose()
    if not isinstance(document, dict):
        message = f"{name}: a workflow must be a mapping"
        raise WorkflowError(message)
    return typ.cast("Document", document)


def read_workflows(directory: Path = WORKFLOW_DIRECTORY) -> Workflow:
    """Read every YAML workflow afresh, refusing an empty or invalid set."""
    try:
        paths = sorted(
            path
            for path in directory.iterdir()
            if path.suffix.casefold() in {".yml", ".yaml"}
        )
    except OSError as error:
        message = f"cannot list workflows in {directory}: {error}"
        raise WorkflowError(message) from error
    if not paths:
        message = f"no workflows were read from {directory}"
        raise WorkflowError(message)

    workflows: Workflow = {}
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as error:
            message = f"{path.name}: cannot be read as UTF-8: {error}"
            raise WorkflowError(message) from error
        workflows[path.name] = load_workflow(path.name, text)
    return workflows


# An alias rather than a wrapper: tests ask for a "fresh" parse by intent, and
# read_workflows already re-reads and re-parses every file on each call.
fresh_documents = read_workflows


def jobs(name: str, document: Document) -> dict[str, dict[str, object]]:
    """Return jobs after confirming every job body is a mapping."""
    found = document.get("jobs")
    if not isinstance(found, dict) or not all(
        isinstance(job, dict) for job in found.values()
    ):
        message = f"{name}: `jobs` must map job names to mappings"
        raise WorkflowError(message)
    return typ.cast("dict[str, dict[str, object]]", found)


def steps(name: str, document: Document) -> cabc.Iterator[Step]:
    """Yield validated step mappings in workflow order."""
    for job in jobs(name, document).values():
        raw_steps = job.get("steps", [])
        if not isinstance(raw_steps, list):
            message = f"{name}: a job's `steps` must be a list"
            raise WorkflowError(message)
        for step in raw_steps:
            if not isinstance(step, dict):
                message = f"{name}: a step must be a mapping"
                raise WorkflowError(message)
            yield typ.cast("Step", step)


def calls(step: Step, action: str) -> bool:
    """Return whether a step names the requested action, ignoring its ref."""
    uses = step.get("uses")
    return (
        isinstance(uses, str) and uses.partition("@")[0].casefold() == action.casefold()
    )


def continues_on_error(mapping: dict[str, object]) -> bool:
    """Treat every value except literal false or absence as a soft failure."""
    return mapping.get("continue-on-error", False) is not False


def triggers(name: str, document: Document) -> dict[str, object]:
    """Return workflow events, normalizing PyYAML's YAML 1.1 ``on`` key."""
    spellings = [key for key in ("on", True) if key in document]
    if len(spellings) != 1:
        message = f"{name}: declares `on` {len(spellings)} times, not once"
        raise WorkflowError(message)
    match document[spellings[0]]:
        case str() as event:
            return {event: None}
        case list() as events if all(isinstance(event, str) for event in events):
            return dict.fromkeys(typ.cast("list[str]", events))
        case dict() as events:
            return {str(event): value for event, value in events.items()}
        case other:
            message = f"{name}: cannot read the trigger {other!r}"
            raise WorkflowError(message)


def holding_job(name: str, document: Document, step: Step) -> dict[str, object]:
    """Return the job that contains this exact step object."""
    return next(
        job
        for job in jobs(name, document).values()
        if any(held is step for held in typ.cast("list[object]", job.get("steps", [])))
    )
