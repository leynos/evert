"""Read and parse repository sources before Whitaker policy evaluation."""

import dataclasses
import tomllib
from pathlib import Path

from whitaker_provisioning_rules import (
    _MakeGraph,
    development_cranelift_default,
    make_lint_targets,
)
from workflow_contract_support import WorkflowError

REPOSITORY = Path(__file__).resolve().parents[2]
MAKEFILE = REPOSITORY / "Makefile"
CARGO_CONFIG = REPOSITORY / ".cargo" / "config.toml"


@dataclasses.dataclass(frozen=True, slots=True)
class ProvisioningInputs:
    """Parsed inputs shared by all Whitaker provisioning policy checks."""

    make_graph: _MakeGraph | None
    cranelift_default: bool | None


def _read_utf8(path: Path, label: str) -> str:
    """Read one named policy source and translate filesystem/encoding errors."""
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        message = f"cannot read {label} as UTF-8 from {path}: {error}"
        raise WorkflowError(message) from error


def read_provisioning_inputs(
    makefile_path: Path = MAKEFILE,
    cargo_config_path: Path = CARGO_CONFIG,
) -> ProvisioningInputs:
    """Load each source once and return immutable policy inputs.

    Returns
    -------
    ProvisioningInputs
        The parsed Make lint graph and Linux development Cranelift default.

    Raises
    ------
    WorkflowError
        If either source cannot be read as UTF-8 or Cargo configuration is
        malformed TOML. The original exception remains available as the cause.
    """
    makefile_source = _read_utf8(makefile_path, "Makefile")
    config_source = _read_utf8(cargo_config_path, "Cargo configuration")
    try:
        cargo_config: object = tomllib.loads(config_source)
    except tomllib.TOMLDecodeError as error:
        message = f"invalid Cargo configuration TOML in {cargo_config_path}: {error}"
        raise WorkflowError(message) from error
    return ProvisioningInputs(
        make_graph=make_lint_targets(makefile_source),
        cranelift_default=development_cranelift_default(cargo_config),
    )
