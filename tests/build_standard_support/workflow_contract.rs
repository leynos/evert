//! Fixtures for workflow steps that install the Linux linker prerequisite.

use rstest::rstest;

use super::{
    ci_steps::{linker_install_problems, workflow_problems},
    none_of,
};

/// A workflow step that passes the input, quoted.
const STEP_INSTALLS: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: 'true'\n"
);
/// The same, with the bare value.
const STEP_INSTALLS_BARE: &str = concat!(
    "    steps:\n      - uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: true\n"
);
/// A step with no input at all.
const STEP_MISSING_INPUT: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n"
);
/// A step that turns the input off.
const STEP_INPUT_OFF: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: 'false'\n"
);
/// A step without the input, followed by a step that has one for another action.
const STEP_BEFORE_A_SIBLING_THAT_INSTALLS: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "      - name: Other\n        uses: org/other@abc\n        with:\n          install-mold: \
     'true'\n"
);
/// A comment that names the action, and no step.
const COMMENT_NAMING_THE_ACTION: &str =
    "    steps:\n      # setup-rust@abc installs it\n      - run: make\n";

/// Every setup step must provide the linker input itself; sibling steps and
/// comments cannot satisfy the contract.
#[rstest]
#[case::quoted_true(STEP_INSTALLS, 0)]
#[case::bare_true(STEP_INSTALLS_BARE, 0)]
#[case::missing_input(STEP_MISSING_INPUT, 1)]
#[case::input_off(STEP_INPUT_OFF, 1)]
#[case::input_on_a_sibling_step(STEP_BEFORE_A_SIBLING_THAT_INSTALLS, 1)]
#[case::comment_only(COMMENT_NAMING_THE_ACTION, 0)]
fn the_workflow_reader_wants_the_input_on_each_step(
    #[case] workflow: &str,
    #[case] expected: usize,
) -> Result<(), String> {
    let found = linker_install_problems("fixture.yml", workflow).len();
    if found == expected {
        Ok(())
    } else {
        Err(format!("{workflow:?}: {found} problems, not {expected}"))
    }
}

/// Every listed repository workflow that builds under the standard installs
/// the same linker prerequisite.
#[test]
fn every_setup_rust_step_installs_linker() -> Result<(), String> { none_of(&workflow_problems()) }
