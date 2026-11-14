"""Policy for the Whitaker action's `cranelift` input."""


def cranelift_input_violations(
    *, selected: bool | None, expected_cranelift: bool | None
) -> list[str]:
    """List the complaints about the parsed `cranelift` input, if any."""
    # The input must be true while the development default selects Cranelift;
    # once Cranelift is an opt-in it is optional, but must still be a boolean.
    if expected_cranelift is None:
        return ["cannot determine the Linux development Cranelift default"]
    if selected is None:
        return ["Whitaker action cranelift input must be a boolean"]
    if expected_cranelift and not selected:
        message = (
            "Whitaker action cranelift input must be true while the Linux "
            "development default selects Cranelift"
        )
        return [message]
    return []
