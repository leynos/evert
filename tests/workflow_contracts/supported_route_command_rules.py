"""Validate the exact stable Cross command used by the release route."""


def _release_build_command_errors(
    build: tuple[int, dict[str, object]] | None,
) -> list[str]:
    """Check prefix isolation and exact matrix-target Cross build spelling.

    Returns
    -------
    list[str]
        Ordered prefix-isolation and exact-command diagnostics.

    Examples
    --------
    >>> _release_build_command_errors(None)
    []
    """
    if build is None:
        return []
    cleared = "env -u CARGO_ENCODED_RUSTFLAGS "
    command = " ".join(str(build[1].get("run", "")).split())
    errors: list[str] = []
    if not command.startswith(cleared):
        errors.append("release.yml Build release binary must clear encoded flags")
    expected = (
        f"{cleared}cross +stable build --release --target ${{{{ matrix.target }}}}"
    )
    if command != expected:
        errors.append("release.yml must build every matrix target with cross +stable")
    return errors
