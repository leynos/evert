//! Regression cases for Makefile shell-wrapper `RUSTFLAGS` assignments.

use rstest::rstest;

use super::{
    Assignment,
    Flags,
    INHERIT_DASH,
    INHERIT_PLUS,
    assigned_rustflags,
    has_glued_inherited_flags,
    inherits_caller_flags,
    quoted_assignment,
    shell_wrapper_assignment,
};

const VALID_WRAPPER: &str = r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"' _ '-D warnings' cargo test"#;

/// Scenario: wrapper markers or arguments are valid, missing, or malformed.
///
/// Invariant: readable arguments preserve caller flags; the first failing
/// check keeps its established diagnostic.
#[rstest]
#[case::valid(VALID_WRAPPER, &["-D", "warnings"], None)]
#[case::missing_expected_flags(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS-}$make_flags"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"' _ '-D warnings' cargo test"#,
    &[],
    Some("unreadable shell RUSTFLAGS wrapper")
)]
#[case::missing_expected_assignment(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env -u OTHER RUSTFLAGS="$effective_flags" "$@"' _ '-D warnings' cargo test"#,
    &[],
    Some("unreadable shell RUSTFLAGS wrapper")
)]
#[case::missing_argument_separator(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"'_' -D warnings' cargo test"#,
    &[],
    Some("shell RUSTFLAGS wrapper has no make_flags argument")
)]
#[case::missing_argument_quote(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"' _ '-D warnings cargo test"#,
    &[],
    Some("shell RUSTFLAGS wrapper has an unreadable make_flags argument")
)]
#[case::empty_make_flags(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"' _ '' cargo test"#,
    &[],
    None
)]
fn wrapper_assignment_cases(
    #[case] line: &str,
    #[case] words: &[&str],
    #[case] message: Option<&str>,
) {
    let assignment = Assignment::Flags(Flags::from_words(words.iter().copied()), true);
    let expected = message.map_or(Ok(assignment), |details| {
        Err(format!("{details} in `{line}`"))
    });
    assert_eq!(shell_wrapper_assignment(line), expected,);
}

/// Scenario: quoted values contain own flags or one supported inheritance form.
///
/// Invariant: only own flags remain in the returned `Flags` value.
#[rstest]
#[case::own_flags_only(
    "RUSTFLAGS=\"-Zthreads=8 -D warnings\" cargo test",
    "-Zthreads=8 -D warnings\" cargo test",
    &["-Zthreads=8", "-D", "warnings"],
    false
)]
#[case::dash_expansion_only(
    "RUSTFLAGS=\"${RUSTFLAGS-}\" cargo test",
    "${RUSTFLAGS-}\" cargo test",
    &[],
    true
)]
#[case::plus_expansion_prefix(
    "RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }-Zthreads=8\" cargo test",
    "${RUSTFLAGS:+$RUSTFLAGS }-Zthreads=8\" cargo test",
    &["-Zthreads=8"],
    true
)]
fn quoted_assignment_keeps_only_own_flags(
    #[case] line: &str,
    #[case] rest: &str,
    #[case] words: &[&str],
    #[case] inherits: bool,
) {
    let expected = Assignment::Flags(Flags::from_words(words.iter().copied()), inherits);
    assert_eq!(quoted_assignment(line, rest), Ok(expected));
}

/// Scenario: quoted assignments cannot be read safely.
///
/// Invariant: glued inherited flags and missing closing quotes stay errors.
#[rstest]
#[case::glued_inheritance(
    "RUSTFLAGS=\"${RUSTFLAGS-}-Zthreads=8\" cargo test",
    "${RUSTFLAGS-}-Zthreads=8\" cargo test",
    "inherited RUSTFLAGS glued to the next flag"
)]
#[case::unterminated_quote(
    "RUSTFLAGS=\"-Zthreads=8 cargo test",
    "-Zthreads=8 cargo test",
    "unterminated RUSTFLAGS"
)]
fn quoted_assignment_reports_reading_errors(
    #[case] line: &str,
    #[case] rest: &str,
    #[case] message: &str,
) {
    assert_eq!(
        quoted_assignment(line, rest),
        Err(format!("{message} in `{line}`"))
    );
}

/// Scenario: dispatch receives an unquoted assignment or no assignment.
///
/// Invariant: an unreadable bare value is rejected, while no assignment is safe.
#[rstest]
#[case::bare_assignment(
    "RUSTFLAGS=-Zthreads=8 cargo test",
    Err("unreadable RUSTFLAGS assignment in `RUSTFLAGS=-Zthreads=8 cargo test`".to_owned())
)]
#[case::no_assignment("cargo test", Ok(Assignment::Unassigned))]
fn assigned_rustflags_dispatches_bare_and_missing_assignments(
    #[case] line: &str,
    #[case] expected: Result<Assignment, String>,
) {
    assert_eq!(assigned_rustflags(line), expected);
}

/// Scenario: inheritance comes from either assignment or wrapper expansion.
///
/// Invariant: the four existing locations are recognized independently.
#[rstest]
#[case::plus_in_assigned(INHERIT_PLUS, "", true)]
#[case::dash_in_assigned(INHERIT_DASH, "", true)]
#[case::plus_after_effective_flags("", "effective_flags=\"${RUSTFLAGS:+$RUSTFLAGS }x", true)]
#[case::dash_after_effective_flags("", "effective_flags=\"${RUSTFLAGS-}x", true)]
#[case::no_inheritance("-Zthreads=8", "RUSTFLAGS=\"-Zthreads=8\"", false)]
fn inheritance_locations_keep_the_four_way_contract(
    #[case] assigned: &str,
    #[case] line: &str,
    #[case] expected: bool,
) {
    assert_eq!(inherits_caller_flags(assigned, line), expected);
}

/// Scenario: a dash expansion is adjacent to a following token.
///
/// Invariant: only a non-empty suffix without a separating space is glued.
#[rstest]
#[case::glued("${RUSTFLAGS-}-Zthreads=8", true)]
#[case::separated("${RUSTFLAGS-} -Zthreads=8", false)]
#[case::empty_suffix("${RUSTFLAGS-}", false)]
#[case::plus_expansion_is_spaced("${RUSTFLAGS:+$RUSTFLAGS }-Zthreads=8", false)]
fn glued_inheritance_requires_a_missing_separator(#[case] assigned: &str, #[case] expected: bool) {
    assert_eq!(has_glued_inherited_flags(assigned), expected);
}
