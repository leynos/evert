"""Test Whitaker source-read and parse failures at their orchestration boundary."""

import tomllib
import typing as typ

import pytest
from whitaker_provisioning_inputs import read_provisioning_inputs
from workflow_contract_support import WorkflowError

if typ.TYPE_CHECKING:
    from pathlib import Path

VALID_MAKEFILE = "lint:\nall: lint\n"
VALID_CARGO_CONFIG = '[target.\'cfg(target_os = "linux")\']\nrustflags = []\n'


@pytest.mark.parametrize("invalid_source", ["missing", "invalid-utf8"])
def test_makefile_read_errors_name_source_and_preserve_cause(
    tmp_path: Path, invalid_source: str
) -> None:
    """Makefile I/O and decoding failures become a caused workflow error."""
    makefile = tmp_path / "Makefile"
    if invalid_source == "invalid-utf8":
        makefile.write_bytes(b"lint:\n\xff\n")
        expected_cause = UnicodeDecodeError
    else:
        expected_cause = FileNotFoundError

    with pytest.raises(WorkflowError, match="Makefile") as raised:
        read_provisioning_inputs(makefile, tmp_path / "config.toml")

    assert isinstance(raised.value.__cause__, expected_cause), raised.value.__cause__


@pytest.mark.parametrize("invalid_source", ["missing", "invalid-utf8"])
def test_cargo_config_read_errors_name_source_and_preserve_cause(
    tmp_path: Path, invalid_source: str
) -> None:
    """Cargo config I/O and decoding failures become caused workflow errors."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(VALID_MAKEFILE, encoding="utf-8")
    cargo_config = tmp_path / "config.toml"
    if invalid_source == "invalid-utf8":
        cargo_config.write_bytes(b"[target]\n\xff\n")
        expected_cause = UnicodeDecodeError
    else:
        expected_cause = FileNotFoundError

    with pytest.raises(WorkflowError, match="Cargo configuration") as raised:
        read_provisioning_inputs(makefile, cargo_config)

    assert isinstance(raised.value.__cause__, expected_cause), raised.value.__cause__


def test_invalid_cargo_toml_names_source_and_preserves_cause(tmp_path: Path) -> None:
    """Malformed Cargo TOML becomes a caused workflow error at the boundary."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(VALID_MAKEFILE, encoding="utf-8")
    cargo_config = tmp_path / "config.toml"
    cargo_config.write_text("[target\n", encoding="utf-8")

    with pytest.raises(WorkflowError, match="Cargo configuration TOML") as raised:
        read_provisioning_inputs(makefile, cargo_config)

    assert isinstance(raised.value.__cause__, tomllib.TOMLDecodeError), (
        raised.value.__cause__
    )


def test_injected_sources_produce_policy_inputs_without_repository_reads(
    tmp_path: Path,
) -> None:
    """The boundary can parse temporary sources independently of the checkout."""
    makefile = tmp_path / "Makefile"
    makefile.write_text(VALID_MAKEFILE, encoding="utf-8")
    cargo_config = tmp_path / "config.toml"
    cargo_config.write_text(VALID_CARGO_CONFIG, encoding="utf-8")

    inputs = read_provisioning_inputs(makefile, cargo_config)

    assert inputs.make_graph is not None, "lint route must be present"
    assert inputs.make_graph.lint_targets == {"lint", "all"}, inputs.make_graph
    assert inputs.cranelift_default is False, inputs
