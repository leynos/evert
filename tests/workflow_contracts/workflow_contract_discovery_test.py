"""Hold workflow file discovery and fresh-read contracts."""

import typing as typ
from pathlib import Path

import pytest
import workflow_contract_support as workflow_support
from workflow_contract_support import WorkflowError, fresh_documents, read_workflows


def test_read_workflows_discovers_sorted_case_insensitive_yaml_suffixes(
    tmp_path: Path,
) -> None:
    """Only sorted .yml and .yaml files, regardless of suffix case, are read."""
    for filename in ("z.YmL", "a.YAML", "m.yml", "ignored.yaml.txt"):
        (tmp_path / filename).write_text("jobs: {}\n", encoding="utf-8")

    found = read_workflows(tmp_path)

    assert list(found) == ["a.YAML", "m.yml", "z.YmL"], (
        "workflow discovery or sorting changed"
    )


def test_read_workflows_rejects_an_empty_directory(tmp_path: Path) -> None:
    """An empty workflow directory retains its named error."""
    with pytest.raises(WorkflowError, match="no workflows were read"):
        read_workflows(tmp_path)


def test_read_workflows_preserves_directory_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Directory-listing failures keep their cause and directory name."""
    expected = OSError("directory is unavailable")

    def fail_listing(_path: Path) -> typ.NoReturn:
        """Simulate failure while listing the workflow directory."""
        raise expected

    monkeypatch.setattr(Path, "iterdir", fail_listing)
    with pytest.raises(WorkflowError, match="cannot list workflows") as failure:
        read_workflows(tmp_path)

    assert failure.value.__cause__ is expected, "directory error cause was lost"


def test_read_workflows_rejects_invalid_utf8_with_its_cause(tmp_path: Path) -> None:
    """Invalid UTF-8 is reported as a file error with exception chaining."""
    (tmp_path / "broken.yml").write_bytes(b"jobs: \xff\n")
    with pytest.raises(
        WorkflowError, match=r"broken\.yml: cannot be read as UTF-8"
    ) as failure:
        read_workflows(tmp_path)

    assert isinstance(failure.value.__cause__, UnicodeDecodeError), (
        "decode error cause was lost"
    )


def test_read_workflows_preserves_file_oserror(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """File-reading failures preserve the filename and original cause."""
    blocked = tmp_path / "blocked.yml"
    blocked.write_text("jobs: {}\n", encoding="utf-8")
    expected = OSError("file is unavailable")
    original_read_text = Path.read_text

    def fail_read(
        path: Path, *, encoding: str | None = None, errors: str | None = None
    ) -> str:
        """Fail only the selected file while preserving normal reads elsewhere."""
        if path == blocked:
            raise expected
        return original_read_text(path, encoding=encoding, errors=errors)

    monkeypatch.setattr(Path, "read_text", fail_read)
    with pytest.raises(
        WorkflowError, match=r"blocked\.yml: cannot be read as UTF-8"
    ) as failure:
        read_workflows(tmp_path)

    assert failure.value.__cause__ is expected, "file error cause was lost"


def test_fresh_documents_aliases_fresh_reads_and_parses(tmp_path: Path) -> None:
    """Each read uses current bytes and creates new document objects."""
    path = tmp_path / "ci.yml"
    path.write_text("jobs: {}\n", encoding="utf-8")
    first = fresh_documents(tmp_path)
    second = fresh_documents(tmp_path)
    path.write_text("jobs: {build: {steps: []}}\n", encoding="utf-8")
    third = read_workflows(tmp_path)

    assert first is not second, "fresh read reused the result dictionary"
    assert first["ci.yml"] is not second["ci.yml"], "fresh read reused a document"
    assert third["ci.yml"] == {"jobs": {"build": {"steps": []}}}, (
        "updated file contents were not read"
    )


def test_fresh_documents_remains_a_direct_alias() -> None:
    """The convenience name stays identical to the underlying reader."""
    assert fresh_documents is workflow_support.read_workflows, (
        "fresh_documents became a wrapper"
    )
