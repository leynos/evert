//! Exercises Make's lint routes and their build-tools preflight.

use std::process::{Command, Output};

use rstest::rstest;

/// Finds the evaluated positions of the preflight and first Cargo command.
pub(super) fn preflight_and_cargo_positions(output: &str) -> Option<(usize, usize)> {
    let preflight = output
        .lines()
        .position(|line| line.contains("scripts/check-build-tools.sh"))?;
    let cargo = output
        .lines()
        .position(|line| !super::cargo_invocation_lines(line).is_empty())?;
    Some((preflight, cargo))
}

/// Checks that Make reaches the injected failure only after the successful Cargo stubs.
#[rstest]
#[case::composite_lint("lint", true)]
#[case::whitaker_leaf("lint-whitaker", false)]
fn failing_whitaker_propagates_after_clippy(#[case] target: &str, #[case] parallel: bool) {
    let output = match run_make_with_failing_whitaker(target, parallel) {
        Ok(output) => output,
        Err(error) => panic!("make must run with the controlled executables: {error}"),
    };
    let diagnostics = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );
    let lines: Vec<_> = diagnostics.lines().collect();

    assert!(
        !output.status.success(),
        "the controlled Whitaker failure must propagate through `make {target}`: {diagnostics}"
    );
    let doc_commands: Vec<_> = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| line.contains("true doc --no-deps"))
        .collect();
    let clippy_commands: Vec<_> = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| line.contains("true clippy"))
        .collect();
    let whitaker_commands: Vec<_> = lines
        .iter()
        .enumerate()
        .filter(|(_, line)| line.split_whitespace().any(|word| word == "false"))
        .collect();

    assert_eq!(
        doc_commands.len(),
        1,
        concat!(
            "the normal build-tools preflight must succeed before the rustdoc stub runs; ",
            "if the preflight reports missing tools, run `make install-build-tools`; ",
            "expected one rustdoc invocation; output: {diagnostics}"
        ),
        diagnostics = diagnostics
    );
    assert_eq!(
        clippy_commands.len(),
        1,
        "the requested lint route must invoke Clippy exactly once: {diagnostics}"
    );
    assert_eq!(
        whitaker_commands.len(),
        1,
        "the requested lint route must invoke Whitaker exactly once: {diagnostics}"
    );
    let ordered_commands = matches!(
        (doc_commands.first(), clippy_commands.first(), whitaker_commands.first()),
        (Some(doc), Some(clippy), Some(whitaker))
            if doc.0 < clippy.0 && clippy.0 < whitaker.0
    );
    assert!(
        ordered_commands,
        concat!(
            "the rustdoc, Clippy, and failing Whitaker commands must run in that order: ",
            "{diagnostics}"
        ),
        diagnostics = diagnostics
    );
}

/// Runs the selected lint recipe with Cargo succeeding and Whitaker failing.
///
/// For example, `run_make_with_failing_whitaker("lint", true)` runs the
/// composite recipe in parallel so the test can inspect failure propagation.
fn run_make_with_failing_whitaker(target: &str, parallel: bool) -> std::io::Result<Output> {
    let mut command = Command::new("make");
    if parallel {
        command.arg("-j");
    }
    command
        .args([
            "--no-print-directory",
            target,
            "CARGO=true",
            "WHITAKER=false",
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
}
