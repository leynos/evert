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

/// One target-selection input and the expected route for each Cargo command.
struct TargetRouteCase {
    target: &'static str,
    variable: &'static str,
    value: &'static str,
    expected_development_routes: [bool; 2],
}

/// Native, cross, malformed, and unrelated target-like options select routes.
#[rstest]
#[case::cross_build_target_setting(TargetRouteCase { target: "test", variable: "CARGO_BUILD_TARGET", value: CROSS_TARGET, expected_development_routes: [false, false] })]
#[case::cross_split_cargo_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: CROSS_SPLIT_TARGET, expected_development_routes: [true, false] })]
#[case::cross_joined_cargo_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: CROSS_JOINED_TARGET, expected_development_routes: [true, false] })]
#[case::cross_split_test_target(TargetRouteCase { target: "test", variable: "TEST_FLAGS", value: CROSS_SPLIT_TARGET, expected_development_routes: [false, true] })]
#[case::cross_joined_test_target(TargetRouteCase { target: "test", variable: "TEST_FLAGS", value: CROSS_JOINED_TARGET, expected_development_routes: [false, true] })]
#[case::test_target_after_separator_is_ignored(
    TargetRouteCase {
        target: "test",
        variable: "TEST_FLAGS",
        value: "--all-targets --all-features -- --target=aarch64-unknown-linux-gnu",
        expected_development_routes: [true, true],
    }
)]
#[case::malformed_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: "--target=", expected_development_routes: [true, false] })]
#[case::multiple_targets(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: "--target x86_64-unknown-linux-gnu --target aarch64-unknown-linux-gnu", expected_development_routes: [true, false] })]
#[case::native_build_target_setting(TargetRouteCase { target: "test", variable: "CARGO_BUILD_TARGET", value: NATIVE_TARGET, expected_development_routes: [true, true] })]
#[case::native_split_cargo_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: NATIVE_SPLIT_TARGET, expected_development_routes: [true, true] })]
#[case::native_joined_cargo_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: NATIVE_JOINED_TARGET, expected_development_routes: [true, true] })]
#[case::native_split_test_target(TargetRouteCase { target: "test", variable: "TEST_FLAGS", value: NATIVE_SPLIT_TARGET, expected_development_routes: [true, true] })]
#[case::native_joined_test_target(TargetRouteCase { target: "test", variable: "TEST_FLAGS", value: NATIVE_JOINED_TARGET, expected_development_routes: [true, true] })]
#[case::target_directory_is_not_a_target(TargetRouteCase { target: "lint", variable: "CARGO_FLAGS", value: "--target-dir target", expected_development_routes: [true, true] })]
fn explicit_target_selects_development_route(#[case] case: TargetRouteCase) {
    assert!(
        matches!(
            case.variable,
            "CARGO_BUILD_TARGET" | "CARGO_FLAGS" | "TEST_FLAGS"
        ),
        "each routing case names a known Make variable"
    );
    let run = make_dry_run_with_options(
        case.target,
        "Linux",
        "x86_64",
        &[(case.variable, case.value)],
    )
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
        "`make --dry-run {}` must expose both Cargo invocations: {}",
        case.target,
        run.stdout
    );
    let [first, second] = commands.as_slice() else {
        panic!(
            "target-selection should expose two Cargo commands: {}",
            run.stdout
        );
    };
    assert_route(
        first,
        case.expected_development_routes[0],
        "first Cargo command",
    );
    assert_route(
        second,
        case.expected_development_routes[1],
        "second Cargo command",
    );
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
