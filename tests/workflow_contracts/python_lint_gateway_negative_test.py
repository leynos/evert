"""Prove gateway prerequisite contracts reject isolated Makefile regressions."""

import re
import typing as typ

import pytest
import python_lint_gateway_test as gateway_test

if typ.TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    "case",
    [
        pytest.param(
            (
                "all",
                "typecheck",
                "all: lint ## Aggregate; typecheck is only mentioned here\n",
                "all must depend on typecheck, found ['lint']",
            ),
            id="all-edge-missing",
        ),
        pytest.param(
            (
                "lint",
                "lint-python",
                "lint: lint-clippy lint-whitaker\n",
                (
                    "lint must depend on lint-python, found "
                    "['lint-clippy', 'lint-whitaker']"
                ),
            ),
            id="lint-edge-missing",
        ),
        pytest.param(
            (
                "typecheck",
                "typecheck-python",
                "typecheck: typecheck-rust\n",
                "typecheck must depend on typecheck-python, found ['typecheck-rust']",
            ),
            id="python-typecheck-edge-missing",
        ),
        pytest.param(
            (
                "typecheck",
                "typecheck-rust",
                "typecheck: typecheck-python\n",
                "typecheck must depend on typecheck-rust, found ['typecheck-python']",
            ),
            id="rust-typecheck-edge-missing",
        ),
        pytest.param(
            (
                "all",
                "typecheck",
                "all-extra: typecheck\n",
                "Makefile does not define all",
            ),
            id="all-declaration-missing-prefix-is-not-enough",
        ),
        pytest.param(
            (
                "lint",
                "lint-python",
                "lint-python: lint\n",
                "Makefile does not define lint",
            ),
            id="lint-declaration-missing",
        ),
        pytest.param(
            (
                "typecheck",
                "typecheck-python",
                "typecheck-python: lint\n",
                "Makefile does not define typecheck",
            ),
            id="typecheck-declaration-missing",
        ),
        pytest.param(
            (
                "typecheck",
                "typecheck-rust",
                "typecheck-rust: lint\n",
                "Makefile does not define typecheck",
            ),
            id="typecheck-rust-declaration-missing",
        ),
        pytest.param(
            (
                "all",
                "typecheck",
                "all: lint ## typecheck\n",
                "all must depend on typecheck, found ['lint']",
            ),
            id="help-suffix-is-not-a-prerequisite",
        ),
    ],
)
def test_gateway_prerequisite_contract_rejects_broken_makefiles(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: tuple[str, str, str, str],
) -> None:
    """Missing edges and declarations fail against isolated Makefile text."""
    target, prerequisite, source, message = case
    fixture_makefile = tmp_path / "Makefile"
    fixture_makefile.write_text(source, encoding="utf-8")
    monkeypatch.setattr(gateway_test, "MAKEFILE", fixture_makefile)

    with pytest.raises(AssertionError, match=re.escape(message)):
        gateway_test.test_make_target_requires_gateway_prerequisite(
            target, prerequisite
        )
