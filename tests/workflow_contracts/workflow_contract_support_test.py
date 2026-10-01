"""Hold the shape-walking helpers every workflow contract test relies on.

``mapping_at`` and ``sequence_at`` replace chained subscripts such as
``documents["ci.yml"]["jobs"]["build"]["steps"]``. They must return the live
objects, because tests mutate them to build violating workflows, and they must
fail with a named path when the shape is wrong.
"""

import typing as typ

import pytest
from workflow_contract_support import WorkflowError, mapping_at, sequence_at

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
    steps = sequence_at(DOCUMENT, "jobs", "build", "steps")
    before = len(DOCUMENT["jobs"]["build"]["steps"])
    steps.append({"run": "extra"})
    after = len(DOCUMENT["jobs"]["build"]["steps"])
    steps.pop()
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
