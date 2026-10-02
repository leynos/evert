//! Checks that the selected Linux host uses rustc's LLVM backend and stable release
//! routes clear development compiler flags before invoking rustc.
//!
//! Cargo permits nightly `-Z` flags in its configuration, but stable release
//! commands must replace those defaults before the compiler runs. This
//! contract checks the intended flag source and both release entry points; a
//! separate verbose build records the actual rustc arguments.

use std::{io, process::Command};

use rstest::rstest;

#[path = "build_backend_contract_support/toml.rs"]
mod toml;
use toml::{rustflags_include, tables_with_rustflag};

/// Regression tests for quoted TOML hash handling.
#[path = "build_backend_contract_support/quoted_hash.rs"]
mod quoted_hash_tests;

/// Repository Cargo configuration inspected by the routing contract.
const CARGO_CONFIG: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/.cargo/config.toml"));
/// Pinned toolchain whose components must not include the unsupported backend.
const TOOLCHAIN: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/rust-toolchain.toml"));
/// Release workflow whose stable build route must exclude development flags.
const RELEASE_WORKFLOW: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/.github/workflows/release.yml"
));
/// Supported matrix targets whose release routes must remain isolated.
const RELEASE_TARGETS: [&str; 6] = [
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "x86_64-pc-windows-gnu",
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-unknown-freebsd",
];
/// Supported development flags scoped to the generic Linux cfg source.
const DEVELOPMENT_FLAGS: [&str; 3] = ["-Zthreads=8", "fuse-ld=mold", "-Clinker=evert-clang-mold"];
/// The Cargo cfg table that applies to every Linux target architecture.
const DEVELOPMENT_TABLE: &str = "target.'cfg(target_os = \"linux\")'";

/// Cranelift must remain out of Cargo's defaults and the pinned toolchain until
/// the unwind probes pass under a reviewed component and toolchain.
#[test]
fn cranelift_is_absent_from_defaults_and_toolchain() {
    assert!(!CARGO_CONFIG.contains("cranelift"));
    assert!(!TOOLCHAIN.contains("cranelift"));
}

/// Reports whether any workflow, job, or step assigns encoded rustflags.
fn has_encoded_rustflags_binding(workflow: &str) -> bool {
    workflow.lines().any(|raw_line| {
        let line = raw_line.trim();
        !line.starts_with('#')
            && (line.contains("CARGO_ENCODED_RUSTFLAGS:")
                || line.contains("CARGO_ENCODED_RUSTFLAGS="))
    })
}

/// Recognizes a stable release command after both Cargo flag sources have
/// been cleared or replaced, with no development-only flag passed directly.
fn stable_release_is_isolated(route: &str) -> bool {
    unique_stable_release_command(route)
        .as_deref()
        .is_some_and(|command| release_command_is_isolated(route, command))
}

/// Returns the normalized release command only when the route has exactly one.
///
/// ```text
/// unique_stable_release_command("cross +stable build --release") -> Some(..)
/// unique_stable_release_command("cross build --release\\ncross build --release") -> None
/// ```
fn unique_stable_release_command(route: &str) -> Option<String> {
    let mut release_command = None;
    for line in route.lines() {
        let normalized = line.split_whitespace().collect::<Vec<_>>().join(" ");
        if !normalized.contains("build --release") {
            continue;
        }
        if release_command.is_some() {
            return None;
        }
        release_command = Some(normalized);
    }
    release_command
}

/// Checks the standard flag policy for one already-selected release command.
///
/// ```text
/// release_command_is_isolated("", "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" cross +stable build --release") -> true
/// release_command_is_isolated("", "cross +stable build --release") -> false
/// ```
fn release_command_is_isolated(route: &str, command: &str) -> bool {
    let replaces_rustflags = command.contains("RUSTFLAGS=\"\"")
        || command.contains("RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }\"")
        || route.lines().any(|line| line.trim() == "RUSTFLAGS: \"\"");
    let clears_encoded_rustflags = command.contains("env -u CARGO_ENCODED_RUSTFLAGS")
        && !route.contains("CARGO_ENCODED_RUSTFLAGS=")
        && !route.contains("CARGO_ENCODED_RUSTFLAGS:");
    let has_stable_release_command = command.contains("+stable");
    let carries_no_development_flags = [
        "-Zcodegen-backend=cranelift",
        "-Zthreads=8",
        "fuse-ld=mold",
        "evert-clang-mold",
        "tools/dev-fast",
    ]
    .into_iter()
    .all(|flag| !command.contains(flag));

    replaces_rustflags
        && clears_encoded_rustflags
        && has_stable_release_command
        && carries_no_development_flags
}

/// Returns the named GitHub Actions step containing `command`, if exactly one
/// such step exists.
fn release_step_for_command(workflow: &str, command: &str) -> Option<String> {
    let mut current_step = String::new();
    let mut matching_steps = Vec::new();

    for line in workflow.lines() {
        let is_step_item = line.starts_with("      - ");
        if is_step_item {
            let has_invocation = current_step
                .lines()
                .any(|step_line| release_run_line_has_command(step_line, command));
            if has_invocation {
                matching_steps.push(std::mem::take(&mut current_step));
            } else {
                current_step.clear();
            }
        }
        if !current_step.is_empty() || is_step_item {
            current_step.push_str(line);
            current_step.push('\n');
        }
    }
    let has_invocation = current_step
        .lines()
        .any(|step_line| release_run_line_has_command(step_line, command));
    if has_invocation {
        matching_steps.push(current_step);
    }

    if matching_steps.len() == 1 {
        matching_steps.into_iter().next()
    } else {
        None
    }
}

/// Matches inline YAML `run:` commands and commands in a run block.
fn release_run_line_has_command(line: &str, command: &str) -> bool {
    let trimmed_line = line.trim_start();
    let command_line = trimmed_line
        .strip_prefix("run:")
        .unwrap_or(trimmed_line)
        .trim_start();
    command_line.starts_with("env -u CARGO_ENCODED_RUSTFLAGS") && command_line.contains(command)
}

/// Forces the release recipe to print even when its binary is up to date.
fn release_dry_run() -> io::Result<std::process::Output> {
    Command::new("make")
        .args([
            "--dry-run",
            "--always-make",
            "--no-print-directory",
            "release",
            "CARGO=probe-cargo",
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
}

/// The generic Linux cfg source selects all development flags and no other
/// rustflags table carries any of them.
#[test]
fn development_flags_are_scoped_to_every_linux_target() {
    assert!(
        rustflags_include(CARGO_CONFIG, DEVELOPMENT_TABLE, &DEVELOPMENT_FLAGS,),
        "the generic Linux cfg source must select the required development flags"
    );
    for flag in DEVELOPMENT_FLAGS {
        let tables = tables_with_rustflag(CARGO_CONFIG, flag);
        assert_eq!(tables.len(), 1, "unexpected tables for {flag}: {tables:?}");
        assert_eq!(
            tables.first().map(String::as_str),
            Some(DEVELOPMENT_TABLE),
            "{flag} must appear only in [{DEVELOPMENT_TABLE}]"
        );
    }
    assert!(
        tables_with_rustflag(CARGO_CONFIG, "-Zcodegen-backend=cranelift").is_empty(),
        "the unsupported Cranelift backend must not be selected by Cargo defaults"
    );
}

/// Synthetic cases ensure the stable-route predicate rejects missing or
/// overridden isolation, as well as development flags passed to stable.
#[rstest]
#[case::clears_both_sources(
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" cross +stable build --release",
    true
)]
#[case::preserves_caller_flags(
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }\" cross +stable build \
     --release",
    true
)]
#[case::workflow_environment_and_command(
    "env:\n  RUSTFLAGS: \"\"\nrun: env -u CARGO_ENCODED_RUSTFLAGS cross +stable build --release\n",
    true
)]
#[case::encoded_flags_not_cleared("RUSTFLAGS=\"\" cross +stable build --release", false)]
#[case::configured_flags_not_overridden(
    "env -u CARGO_ENCODED_RUSTFLAGS cross +stable build --release",
    false
)]
#[case::encoded_flags_reassigned(
    concat!(
        "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" ",
        "CARGO_ENCODED_RUSTFLAGS=\"-Zthreads=8\" cross +stable build --release"
    ),
    false
)]
#[case::backend_flag_passed_to_stable(
    concat!(
        "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" ",
        "cross +stable build --release -Zcodegen-backend=cranelift"
    ),
    false
)]
#[case::frontend_flag_passed_to_stable(
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" cross +stable build --release -Zthreads=8",
    false
)]
#[case::pinned_linker_passed_to_stable(
    concat!(
        "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" ",
        "cross +stable build --release -C link-arg=-fuse-ld=mold"
    ),
    false
)]
#[case::non_stable_release(
    "env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"\" cross +nightly build --release",
    false
)]
fn stable_route_predicate_checks_flag_isolation(#[case] route: &str, #[case] expected: bool) {
    assert_eq!(stable_release_is_isolated(route), expected, "{route}");
}

/// The Make release target must substitute `CARGO`, preserve caller flags,
/// override Cargo defaults and add no development flags of its own.
#[test]
fn make_release_route_preserves_caller_flags() {
    let output = release_dry_run().expect("make --dry-run release should run");
    assert!(
        output.status.success(),
        "make --dry-run release failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("make output should be UTF-8");
    let release_commands: Vec<&str> = stdout
        .lines()
        .filter(|line| {
            let normalized = line.split_whitespace().collect::<Vec<_>>().join(" ");
            normalized.contains("probe-cargo +stable build --release")
        })
        .collect();

    assert_eq!(
        release_commands.len(),
        1,
        "unexpected Make release route: {stdout}"
    );
    let command = release_commands
        .first()
        .copied()
        .expect("one release command was asserted");
    assert!(
        command.contains("probe-cargo +stable"),
        "release must use the injected Cargo executable on stable: {command}"
    );
    assert!(
        stable_release_is_isolated(command),
        concat!(
            "Make release route carries development flags or fails to override Cargo flag ",
            "sources: {}"
        ),
        command
    );
}

/// The release workflow must use the same stable flag isolation as Make.
#[test]
fn release_workflow_clears_development_flags() {
    let step = release_step_for_command(RELEASE_WORKFLOW, "cross +stable build --release")
        .expect("the release workflow must have one stable build step");
    assert!(
        step.contains("--target ${{ matrix.target }}"),
        "stable release must route every matrix target through this isolated step: {step}"
    );
    for target in RELEASE_TARGETS {
        assert!(
            RELEASE_WORKFLOW.contains(target),
            "release workflow is missing target {target}"
        );
    }
    assert!(
        stable_release_is_isolated(&step),
        concat!(
            "stable release step carries development flags or fails to clear Cargo flag ",
            "sources:\n{}"
        ),
        step
    );
    assert!(
        !has_encoded_rustflags_binding(RELEASE_WORKFLOW),
        "workflow, job, and step environments must not bind CARGO_ENCODED_RUSTFLAGS"
    );
    let rustflags_bindings: Vec<&str> = RELEASE_WORKFLOW
        .lines()
        .map(str::trim)
        .filter(|line| !line.starts_with('#') && line.contains("RUSTFLAGS:"))
        .collect();
    assert!(
        !rustflags_bindings.is_empty()
            && rustflags_bindings
                .iter()
                .all(|line| *line == "RUSTFLAGS: \"\""),
        concat!(
            "release workflow RUSTFLAGS bindings must explicitly clear inherited development ",
            "flags: {:?}"
        ),
        rustflags_bindings
    );
}

/// Catching an unwind must remain available under the LLVM development backend.
#[test]
fn catch_unwind_observes_an_intentional_panic() {
    let outcome = std::panic::catch_unwind(|| panic!("intentional unwind probe"));
    assert!(outcome.is_err(), "catch_unwind must observe the panic");
}

/// A joined thread must report that its closure panicked.
#[test]
fn joining_a_panicking_thread_reports_its_panic() {
    let outcome = std::thread::spawn(|| panic!("intentional thread panic probe")).join();
    assert!(outcome.is_err(), "joining the thread must report its panic");
}

/// The test harness must still recognize the standard should-panic route.
#[test]
#[should_panic(expected = "intentional should-panic probe")]
fn should_panic_observes_an_intentional_panic() {
    panic!("intentional should-panic probe");
}
