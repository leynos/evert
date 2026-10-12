//! Contract tests for reading `RUSTFLAGS` from evaluated Make output.

use rstest::rstest;

use super::{
    config::{BACKEND_FLAG, Flags, THREADS_FLAG},
    make::{Assignment, assigned_rustflags, commands_from},
};

/// Expected result for a valid Make command or an unsupported assignment.
enum CommandExpectation {
    Parsed(Assignment),
    Refused,
}

const SHELL_WRAPPER_ASSIGNMENT: &str = concat!(
    r#"bash -c 'make_flags=$1; shift; effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; "#,
    r#"exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$effective_flags" "$@"' "#,
    "_ '-D warnings' cargo test",
);

/// One Make output line paired with its expected parser result.
struct CommandCase {
    line: &'static str,
    expectation: CommandExpectation,
}

/// Builds the parsed assignment expected from one fixture's flag words.
///
/// ```text
/// flags(&["-D", "warnings"], false) -> a non-inheriting flag assignment
/// ```
fn flags(words: &[&str], inherits: bool) -> Assignment {
    Assignment::Flags(Flags::from_words(words.iter().copied()), inherits)
}

/// Scenario: Make output lines in the supported and rejected assignment forms.
///
/// Invariant: recognized assignments retain their values; unreadable forms fail.
#[rstest]
#[case::plain(CommandCase {
    line: concat!(
        "RUSTFLAGS=\"-D warnings ",
        "-Zcodegen-backend=cranelift -Zthreads=8\" cargo test"
    ),
    expectation: CommandExpectation::Parsed(flags(
        &["-D", "warnings", BACKEND_FLAG, THREADS_FLAG],
        false,
    )),
})]
#[case::inherited_flags_glued_on(CommandCase {
    line: concat!(
        "RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }",
        "-Zcodegen-backend=cranelift -Zthreads=8\" cargo check"
    ),
    expectation: CommandExpectation::Parsed(flags(&[BACKEND_FLAG, THREADS_FLAG], true)),
})]
#[case::shell_wrapper_inherits_caller_flags(CommandCase {
    line: SHELL_WRAPPER_ASSIGNMENT,
    expectation: CommandExpectation::Parsed(flags(&["-D", "warnings"], true)),
})]
#[case::inherited_flags_only(CommandCase {
    line: "RUSTFLAGS=\"${RUSTFLAGS-}\" cargo build --release",
    expectation: CommandExpectation::Parsed(flags(&[], true)),
})]
#[case::no_assignment(CommandCase {
    line: "cargo clippy --all-targets",
    expectation: CommandExpectation::Parsed(Assignment::Unassigned),
})]
#[case::unquoted(CommandCase {
    line: "RUSTFLAGS=-Zthreads=8 cargo test",
    expectation: CommandExpectation::Refused,
})]
#[case::unterminated(CommandCase {
    line: "RUSTFLAGS=\"-Zthreads=8 cargo test",
    expectation: CommandExpectation::Refused,
})]
fn the_command_reader_matches_each_case(#[case] case: CommandCase) -> Result<(), String> {
    let actual = assigned_rustflags(case.line);
    let expected_description = match &case.expectation {
        CommandExpectation::Parsed(expected) => format!("{expected:?}"),
        CommandExpectation::Refused => "a parsing error".to_owned(),
    };
    let matches = match &case.expectation {
        CommandExpectation::Parsed(expected) => actual.as_ref() == Ok(expected),
        CommandExpectation::Refused => actual.is_err(),
    };
    if matches {
        Ok(())
    } else {
        Err(format!(
            "{line:?}: expected {expected_description}, got {actual:?}",
            line = case.line
        ))
    }
}

/// Scenario: a recipe continued over lines beside `echo` and another command.
///
/// Invariant: the continued command is one command; unrelated lines are ignored.
#[test]
fn a_continued_command_is_one_command() -> Result<(), String> {
    let joined = commands_from(concat!(
        "RUSTFLAGS=\"-A\" \\\n",
        "cargo test\necho cargo test\nmake other\n"
    ))?;
    if joined == vec![flags(&["-A"], false)] {
        Ok(())
    } else {
        Err(format!("read wrongly: {joined:?}"))
    }
}
