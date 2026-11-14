"""Policy for the Whitaker action's `cranelift` input."""


def _boolean_input(value: object) -> bool | None:
    """Read YAML booleans and quoted GitHub action boolean inputs."""
    match value:
        case bool():
            return value
        case str():
            return {"true": True, "false": False}.get(value.casefold())
        case _:
            return None


def cranelift_input_violations(
    inputs: dict[object, object], *, expected_cranelift: bool | None
) -> list[str]:
    """List the complaints about the `cranelift` input, if any."""
    # The input must be true while the development default selects Cranelift;
    # once Cranelift is an opt-in it is optional, but must still be a boolean.
    if expected_cranelift is None:
        return ["cannot determine the Linux development Cranelift default"]
    selected = _boolean_input(inputs.get("cranelift", False))
    if selected is None:
        return ["Whitaker action cranelift input must be a boolean"]
    if expected_cranelift and not selected:
        message = (
            "Whitaker action cranelift input must be true while the Linux "
            "development default selects Cranelift"
        )
        return [message]
    return []
