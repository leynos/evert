//! Fixtures for coverage and release flag isolation and inheritance.

use rstest::rstest;

use super::make::{Host, held_out_problems_with};

/// A valid held-out command retains the caller's flags and adds no development
/// flags of its own.
const CALLER_FLAGS: &str = "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS \
                            }-D warnings\" cargo build\n";
/// Caller-supplied development flags remain opaque to this recipe check.
const CALLER_SUPPLIES_DEVELOPMENT_FLAGS: &str =
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }\" cargo build\n";
/// This recipe replaces rather than preserves caller-supplied `RUSTFLAGS`.
const DROPS_CALLER_FLAGS: &str =
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"-D warnings\" cargo build\n";
/// This recipe appends a development flag after the inherited caller flags.
const ADDS_DEVELOPMENT_FLAG: &str = "env -u CARGO_ENCODED_RUSTFLAGS \
                                     RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }-D warnings \
                                     -Zthreads=8\" cargo build\n";
/// A shell wrapper hides its own flags in the positional `make_flags` value.
const WRAPPER_ADDS_DEVELOPMENT_FLAG: &str = concat!(
    "bash -c 'make_flags=$1; shift; ",
    "effective_flags=\"${RUSTFLAGS:+$RUSTFLAGS }$make_flags\"; ",
    "exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"$effective_flags\" \"$@\"' ",
    "_ '-D warnings -Zthreads=8' cargo build\n"
);
/// An unassigned command falls back to Cargo's Linux development config.
const USES_CONFIGURATION: &str = "cargo build\n";

/// Each held-out target is checked independently against supplied Make output.
/// The sibling target receives the compliant fixture so a finding belongs to
/// the named command.
#[rstest]
#[case::coverage_preserves_caller_flags("coverage", CALLER_FLAGS, false)]
#[case::release_preserves_caller_flags("release", CALLER_FLAGS, false)]
#[case::coverage_keeps_caller_development_flags(
    "coverage",
    CALLER_SUPPLIES_DEVELOPMENT_FLAGS,
    false
)]
#[case::release_keeps_caller_development_flags("release", CALLER_SUPPLIES_DEVELOPMENT_FLAGS, false)]
#[case::coverage_rejects_lost_caller_flags("coverage", DROPS_CALLER_FLAGS, true)]
#[case::release_rejects_lost_caller_flags("release", DROPS_CALLER_FLAGS, true)]
#[case::coverage_rejects_recipe_development_flags("coverage", ADDS_DEVELOPMENT_FLAG, true)]
#[case::release_rejects_recipe_development_flags("release", ADDS_DEVELOPMENT_FLAG, true)]
#[case::coverage_rejects_wrapper_development_flags("coverage", WRAPPER_ADDS_DEVELOPMENT_FLAG, true)]
#[case::release_rejects_wrapper_development_flags("release", WRAPPER_ADDS_DEVELOPMENT_FLAG, true)]
#[case::coverage_rejects_configuration_fallback("coverage", USES_CONFIGURATION, true)]
#[case::release_rejects_configuration_fallback("release", USES_CONFIGURATION, true)]
fn held_out_routes_preserve_caller_flags_and_exclude_development_flags(
    #[case] checked_target: &str,
    #[case] checked_output: &str,
    #[case] expected_problem: bool,
) -> Result<(), String> {
    let mut runner = |target: &str, _host: Host| {
        Ok(if target == checked_target {
            checked_output
        } else {
            CALLER_FLAGS
        }
        .to_owned())
    };
    let (problems, read) = held_out_problems_with(&mut runner)?;
    if read != 2 {
        return Err(format!("read {read} held-out commands, expected 2"));
    }
    if problems.is_empty() == expected_problem
        || problems
            .iter()
            .any(|problem| !problem.contains(checked_target))
    {
        return Err(format!(
            "unexpected {checked_target} route findings: {problems:#?}"
        ));
    }
    Ok(())
}
