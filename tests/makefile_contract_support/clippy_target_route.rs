//! Contracts for target selection in Make's Clippy recipe.

use rstest::rstest;

use super::{
    CROSS_JOINED_TARGET,
    CROSS_SPLIT_TARGET,
    CROSS_TARGET,
    DEVELOPMENT_FLAGS,
    MakeDryRun,
    NATIVE_JOINED_TARGET,
    NATIVE_SPLIT_TARGET,
    NATIVE_TARGET,
    cargo_invocation_lines,
    effective_cargo_route,
    has_development_route,
    make_dry_run_with_options,
};

/// Native, cross, malformed, and unrelated target-like options select routes.
#[rstest]
#[case::cross_build_target_setting("CARGO_BUILD_TARGET", CROSS_TARGET, false)]
#[case::cross_split_cargo_target("CARGO_FLAGS", CROSS_SPLIT_TARGET, false)]
#[case::cross_joined_cargo_target("CARGO_FLAGS", CROSS_JOINED_TARGET, false)]
#[case::cross_split_test_target("TEST_FLAGS", CROSS_SPLIT_TARGET, false)]
#[case::cross_joined_test_target("TEST_FLAGS", CROSS_JOINED_TARGET, false)]
#[case::test_target_after_separator_is_ignored(
    "TEST_FLAGS",
    "--all-targets --all-features -- --target=aarch64-unknown-linux-gnu",
    true
)]
#[case::malformed_target("CARGO_FLAGS", "--target=", false)]
#[case::multiple_targets(
    "CARGO_FLAGS",
    "--target x86_64-unknown-linux-gnu --target aarch64-unknown-linux-gnu",
    false
)]
#[case::native_build_target_setting("CARGO_BUILD_TARGET", NATIVE_TARGET, true)]
#[case::native_split_cargo_target("CARGO_FLAGS", NATIVE_SPLIT_TARGET, true)]
#[case::native_joined_cargo_target("CARGO_FLAGS", NATIVE_JOINED_TARGET, true)]
#[case::native_split_test_target("TEST_FLAGS", NATIVE_SPLIT_TARGET, true)]
#[case::native_joined_test_target("TEST_FLAGS", NATIVE_JOINED_TARGET, true)]
#[case::target_directory_is_not_a_target("CARGO_FLAGS", "--target-dir target", true)]
fn explicit_target_selects_development_route(
    #[case] variable: &str,
    #[case] value: &str,
    #[case] should_keep_development_flags: bool,
) {
    assert!(
        matches!(
            variable,
            "CARGO_BUILD_TARGET" | "CARGO_FLAGS" | "TEST_FLAGS"
        ),
        "each routing case names a known Make variable"
    );
    let target = if variable == "CARGO_FLAGS" {
        "lint"
    } else {
        "test"
    };
    let run = make_dry_run_with_options(target, "Linux", "x86_64", &[(variable, value)])
        .expect("make --dry-run must run");
    assert!(
        run.succeeded,
        "target-selection dry run failed: {}",
        run.stderr
    );
    let commands = cargo_invocation_lines(&run.stdout);
    assert_eq!(
        commands.len(),
        2,
        "`make --dry-run {target}` must expose both Cargo invocations: {}",
        run.stdout
    );
    for (index, command) in commands.iter().enumerate() {
        assert!(
            command.contains("-D warnings"),
            "warning policy was lost: {command}"
        );
        let command_uses_selected_target = variable == "CARGO_BUILD_TARGET"
            || (variable == "CARGO_FLAGS" && index == 1)
            || (variable == "TEST_FLAGS" && index == 0);
        let command_should_keep_development_flags =
            !command_uses_selected_target || should_keep_development_flags;
        if command_should_keep_development_flags {
            assert!(
                has_development_route(command, "Linux", "x86_64"),
                "Cargo command lost the expected development route: {command}"
            );
        } else {
            let effective_route = effective_cargo_route(command);
            for excluded in DEVELOPMENT_FLAGS {
                assert!(
                    !effective_route.contains(excluded),
                    "cross or ambiguous target's effective flags contain {excluded}: {command}"
                );
            }
        }
    }
}

/// Checks Make routing when rustc-only target text follows `CARGO_FLAGS` `--`.
/// This dry run covers Make's parser, not Cargo's acceptance of the command.
#[test]
fn typecheck_ignores_rustc_target_after_cargo_separator() {
    let run = make_dry_run_with_options(
        "typecheck",
        "Linux",
        "x86_64",
        &[(
            "CARGO_FLAGS",
            "--all-targets --all-features -- --target aarch64-unknown-linux-gnu",
        )],
    )
    .expect("make --dry-run must run");
    assert!(run.succeeded, "typecheck dry run failed: {}", run.stderr);

    let commands = cargo_invocation_lines(&run.stdout);
    let [command] = commands.as_slice() else {
        panic!(
            "typecheck should invoke Cargo once; found {}",
            commands.len()
        );
    };
    assert!(
        has_development_route(command, "Linux", "x86_64"),
        "Make counted rustc-only target text as a Cargo cross target: {command}"
    );
}

/// `CARGO_BUILD_TARGET` controls commands without a Clippy `--target` option.
#[rstest]
#[case::cross_environment_target(Some(CROSS_TARGET), "--all-targets --all-features", false, false)]
#[case::native_clippy_overrides_cross_environment(
    Some(CROSS_TARGET),
    "--all-targets --all-features --target=x86_64-unknown-linux-gnu",
    false,
    true
)]
#[case::cross_clippy_overrides_native_environment(
    Some(NATIVE_TARGET),
    "--all-targets --all-features --target=aarch64-unknown-linux-gnu",
    true,
    false
)]
fn clippy_target_flags_route_rustdoc_and_clippy_separately(
    #[case] cargo_build_target: Option<&str>,
    #[case] clippy_flags: &str,
    #[case] rustdoc_keeps_development_flags: bool,
    #[case] clippy_keeps_development_flags: bool,
) {
    assert_lint_routes(
        clippy_flags,
        cargo_build_target,
        rustdoc_keeps_development_flags,
        clippy_keeps_development_flags,
    );
}

/// Clippy target options select the Clippy route while rustdoc stays native.
#[rstest]
#[case::cross_split_target(CROSS_SPLIT_TARGET, false)]
#[case::cross_joined_target(CROSS_JOINED_TARGET, false)]
#[case::native_split_target(NATIVE_SPLIT_TARGET, true)]
#[case::native_joined_target(NATIVE_JOINED_TARGET, true)]
fn clippy_flags_select_its_target_route(
    #[case] target_option: &str,
    #[case] clippy_keeps_development_flags: bool,
) {
    let clippy_flags = format!("--all-targets --all-features {target_option}");
    assert_lint_routes(&clippy_flags, None, true, clippy_keeps_development_flags);
}

/// Target-like rustc options after Cargo's separator do not select its route.
#[rstest]
#[case::split_target_after_separator("--target aarch64-unknown-linux-gnu")]
#[case::joined_target_after_separator("--target=aarch64-unknown-linux-gnu")]
fn clippy_ignores_rustc_targets_after_separator(#[case] rustc_target: &str) {
    let clippy_flags = format!("--all-targets --all-features -- {rustc_target}");
    assert_lint_routes(&clippy_flags, None, true, true);
}

/// Evaluates lint-clippy and asserts the independent rustdoc and Clippy routes.
fn assert_lint_routes(
    clippy_flags: &str,
    cargo_build_target: Option<&str>,
    rustdoc_keeps_development_flags: bool,
    clippy_keeps_development_flags: bool,
) {
    let run = lint_clippy_dry_run(clippy_flags, cargo_build_target);
    assert!(run.succeeded, "lint-clippy dry run failed: {}", run.stderr);

    let commands = cargo_invocation_lines(&run.stdout);
    let [rustdoc_command, clippy_command] = commands.as_slice() else {
        panic!(
            "lint-clippy must expose rustdoc and Clippy commands: {}",
            run.stdout
        );
    };
    assert_route(rustdoc_command, rustdoc_keeps_development_flags, "rustdoc");
    assert_route(clippy_command, clippy_keeps_development_flags, "Clippy");
}

/// Expands lint-clippy with explicit Cargo flags and optional environment target.
fn lint_clippy_dry_run(clippy_flags: &str, cargo_build_target: Option<&str>) -> MakeDryRun {
    let mut options = vec![("CLIPPY_FLAGS", clippy_flags)];
    if let Some(target) = cargo_build_target {
        options.push(("CARGO_BUILD_TARGET", target));
    }
    match make_dry_run_with_options("lint-clippy", "Linux", "x86_64", &options) {
        Ok(run) => run,
        Err(error) => panic!("make --dry-run must run: {error}"),
    }
}

/// Checks warnings and the selected native or cross compiler route.
fn assert_route(command: &str, should_keep_development_flags: bool, tool: &str) {
    assert!(
        command.contains("-D warnings"),
        "{tool} lost the warnings policy: {command}"
    );
    if should_keep_development_flags {
        assert!(
            has_development_route(command, "Linux", "x86_64"),
            "{tool} lost the expected development route: {command}"
        );
    } else {
        let effective_route = effective_cargo_route(command);
        for excluded in DEVELOPMENT_FLAGS {
            assert!(
                !effective_route.contains(excluded),
                "{tool}'s effective flags contain {excluded} for a cross target: {command}"
            );
        }
    }
}
