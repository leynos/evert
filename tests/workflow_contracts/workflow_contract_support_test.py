"""Hold the shape-walking helpers every workflow contract test relies on.

``mapping_at`` and ``sequence_at`` replace chained subscripts such as
``documents["ci.yml"]["jobs"]["build"]["steps"]``. They must return the live
objects, because tests mutate them to build violating workflows, and they must
fail with a named path when the shape is wrong.
"""

import typing as typ

import pytest
import workflow_contract_support as workflow_support
import yaml
from workflow_contract_support import (
    Document,
    WorkflowError,
    load_workflow,
    mapping_at,
    sequence_at,
    steps,
)

if typ.TYPE_CHECKING:
    import collections.abc as cabc

DOCUMENT = {"jobs": {"build": {"steps": [{"run": "make"}], "name": "Build"}}}


def test_mapping_at_returns_the_live_mapping() -> None:
    """Mutating the result changes the document, as the contract tests need."""
    build = mapping_at(DOCUMENT, "jobs", "build")
    build["name"] = "Changed"
    assert DOCUMENT["jobs"]["build"]["name"] == "Changed", "result was a copy"
    build["name"] = "Build"


def test_sequence_at_returns_the_live_list() -> None:
    """Appending to the result appends to the document."""
    step_list = sequence_at(DOCUMENT, "jobs", "build", "steps")
    before = len(DOCUMENT["jobs"]["build"]["steps"])
    step_list.append({"run": "extra"})
    after = len(DOCUMENT["jobs"]["build"]["steps"])
    step_list.pop()
    assert after == before + 1, "result was a copy"


def test_an_empty_path_checks_the_node_itself() -> None:
    """With no keys, the node must itself be the requested kind."""
    assert mapping_at(DOCUMENT) is DOCUMENT, "an empty path must return the node"
    with pytest.raises(WorkflowError, match="must be a list"):
        sequence_at(DOCUMENT)


@pytest.mark.parametrize(
    ("walk", "message"),
    [
        pytest.param(
            lambda: mapping_at(DOCUMENT, "jobs", "missing"),
            "jobs.missing",
            id="missing-key",
        ),
        pytest.param(
            lambda: mapping_at(DOCUMENT, "jobs", "build", "name", "deeper"),
            "jobs.build.name.deeper",
            id="walks-into-a-scalar",
        ),
        pytest.param(
            lambda: mapping_at(DOCUMENT, "jobs", "build", "steps"),
            "must be a mapping",
            id="wrong-kind-mapping",
        ),
        pytest.param(
            lambda: sequence_at(DOCUMENT, "jobs", "build"),
            "must be a list",
            id="wrong-kind-list",
        ),
    ],
)
def test_a_bad_shape_fails_with_the_path(
    walk: cabc.Callable[[], object], message: str
) -> None:
    """Every malformed path raises ``WorkflowError`` naming where it went wrong."""
    with pytest.raises(WorkflowError, match=message.replace(".", r"\.")):
        walk()


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        pytest.param("name: ci\n", {"name": "ci"}, id="named-mapping"),
        pytest.param("{}\n", {}, id="empty-mapping"),
    ],
)
def test_load_workflow_constructs_mappings(
    source: str, expected: dict[str, object]
) -> None:
    """A single YAML mapping, including an empty one, is returned unchanged."""
    assert load_workflow("ci.yml", source) == expected, "mapping was not preserved"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("", id="empty-input"),
        pytest.param("# comment only\n", id="comment-only-input"),
    ],
)
def test_workflow_without_a_yaml_node_is_rejected(source: str) -> None:
    """Empty streams keep the filename-prefixed root diagnostic."""
    with pytest.raises(WorkflowError, match=r"ci\.yml: a workflow must be a mapping"):
        load_workflow("ci.yml", source)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("workflow", id="scalar-root"),
        pytest.param("- workflow\n", id="sequence-root"),
        pytest.param("null\n", id="explicit-null-root"),
    ],
)
def test_non_mapping_workflow_roots_are_rejected(source: str) -> None:
    """Scalar, sequence, and null roots share the existing shape error."""
    with pytest.raises(WorkflowError, match=r"ci\.yml: a workflow must be a mapping"):
        load_workflow("ci.yml", source)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("jobs: [\n", id="invalid-syntax"),
        pytest.param("---\njobs: {}\n---\nother: {}\n", id="multiple-documents"),
        pytest.param("!unsupported value\n", id="unsupported-tag"),
    ],
)
def test_yaml_parser_errors_keep_the_filename_and_cause(source: str) -> None:
    """Parser failures retain safe-loader errors as their chained cause."""
    with pytest.raises(WorkflowError, match=r"ci\.yml: not valid YAML:") as failure:
        load_workflow("ci.yml", source)

    assert isinstance(failure.value.__cause__, yaml.YAMLError), (
        "parser cause was not preserved"
    )


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("jobs: first\njobs: second\n", id="root-mapping"),
        pytest.param(
            "jobs:\n  build:\n    name: first\n    name: second\n",
            id="nested-mapping",
        ),
        pytest.param(
            "jobs:\n  - build:\n      name: first\n      name: second\n",
            id="mapping-in-sequence",
        ),
    ],
)
def test_duplicate_keys_keep_the_filename_and_cause(source: str) -> None:
    """Duplicate keys are rejected before PyYAML folds mappings into dicts."""
    with pytest.raises(WorkflowError, match=r"ci\.yml: duplicate key") as failure:
        load_workflow("ci.yml", source)

    cause = failure.value.__cause__
    assert isinstance(cause, WorkflowError), "duplicate-key cause was not preserved"
    assert "duplicate key" in str(cause), "duplicate-key cause lost its detail"


def test_shared_yaml_aliases_remain_shared() -> None:
    """Two references to one anchored mapping keep object identity."""
    document = load_workflow(
        "aliases.yml",
        "shared: &shared\n  enabled: true\nfirst: *shared\nsecond: *shared\n",
    )

    assert document["first"] is document["second"], "shared alias was copied"


def test_recursive_yaml_value_alias_is_constructed() -> None:
    """Recursive value aliases remain accepted by the safe loader."""
    document = load_workflow("recursive.yml", "loop: &loop [*loop]\n")
    recursive_value = document["loop"]

    assert isinstance(recursive_value, list), "recursive alias did not construct a list"
    assert recursive_value[0] is recursive_value, "recursive alias lost its identity"


@pytest.mark.parametrize(
    ("source", "expected_error"),
    [
        pytest.param("jobs: {}\n", None, id="success"),
        pytest.param("", "a workflow must be a mapping", id="empty-input"),
        pytest.param("jobs: [\n", "not valid YAML", id="syntax-error"),
        pytest.param(
            "jobs: first\njobs: second\n", "duplicate key", id="duplicate-key"
        ),
    ],
)
def test_safe_loader_is_disposed_once(
    monkeypatch: pytest.MonkeyPatch, source: str, expected_error: str | None
) -> None:
    """The real safe loader is disposed once on each exit path."""
    safe_loader = workflow_support.yaml.SafeLoader
    original_dispose = safe_loader.dispose
    disposed_loaders: list[yaml.SafeLoader] = []

    def count_disposal(loader: yaml.SafeLoader) -> None:
        """Record disposal while retaining PyYAML's implementation."""
        disposed_loaders.append(loader)
        original_dispose(loader)

    monkeypatch.setattr(safe_loader, "dispose", count_disposal)
    if expected_error is None:
        assert load_workflow("ci.yml", source) == {"jobs": {}}, (
            "the valid workflow was not constructed"
        )
    else:
        with pytest.raises(WorkflowError, match=expected_error):
            load_workflow("ci.yml", source)

    assert len(disposed_loaders) == 1, "SafeLoader must be disposed exactly once"


@pytest.mark.parametrize(
    "job",
    [
        pytest.param({}, id="missing-steps"),
        pytest.param({"steps": []}, id="empty-steps"),
    ],
)
def test_missing_or_empty_job_steps_yield_nothing(job: dict[str, object]) -> None:
    """Jobs without steps and jobs with an empty list both yield no steps."""
    assert not list(steps("ci.yml", {"jobs": {"build": job}})), (
        "unexpected steps were yielded"
    )


@pytest.mark.parametrize(
    "invalid_steps",
    [
        pytest.param(None, id="null"),
        pytest.param({"run": "make"}, id="mapping"),
        pytest.param("make", id="string"),
        pytest.param(3, id="integer"),
    ],
)
def test_non_list_job_steps_name_the_workflow(
    invalid_steps: object,
) -> None:
    """A non-list steps value raises the filename-prefixed shape error."""
    document: Document = {"jobs": {"build": {"steps": invalid_steps}}}
    with pytest.raises(
        WorkflowError, match=r"ci\.yml: a job's `steps` must be a list"
    ) as failure:
        list(steps("ci.yml", document))

    assert failure.value.__cause__ is None, "shape error gained a cause"


def test_non_mapping_job_step_names_the_workflow() -> None:
    """A list member that is not a mapping raises the existing diagnostic."""
    with pytest.raises(
        WorkflowError, match=r"ci\.yml: a step must be a mapping"
    ) as failure:
        list(steps("ci.yml", {"jobs": {"build": {"steps": ["make"]}}}))

    assert failure.value.__cause__ is None, "shape error gained a cause"


def test_steps_preserve_job_order_step_order_and_identity() -> None:
    """The generator yields each original mapping in document order."""
    first = {"run": "first"}
    second = {"run": "second"}
    third = {"run": "third"}
    yielded = list(
        steps(
            "ci.yml",
            {
                "jobs": {
                    "one": {"steps": [first, second]},
                    "two": {"steps": [third]},
                }
            },
        )
    )

    expected = (first, second, third)
    assert len(yielded) == len(expected), "not every step was yielded"
    assert all(
        actual is original for actual, original in zip(yielded, expected, strict=True)
    ), "step order or identity changed"


def test_a_later_bad_step_fails_only_after_the_first_step_is_yielded() -> None:
    """Step validation stays lazy at each yield boundary."""
    first = {"run": "make"}
    iterator = steps("ci.yml", {"jobs": {"build": {"steps": [first, None]}}})

    assert next(iterator) is first, "valid first step was not yielded"
    with pytest.raises(WorkflowError, match="a step must be a mapping"):
        next(iterator)


def test_invalid_job_body_fails_before_any_step_is_yielded() -> None:
    """Job mappings are checked before the step generator starts yielding."""
    first = {"run": "make"}
    iterator = steps(
        "ci.yml",
        {"jobs": {"valid": {"steps": [first]}, "invalid": "not a mapping"}},
    )

    with pytest.raises(
        WorkflowError,
        match=r"ci\.yml: `jobs` must map job names to mappings",
    ):
        next(iterator)
