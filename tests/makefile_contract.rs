//! Contract tests for Make's evaluated Cargo routes.
//!
//! These tests ask Make to expand each build target with an injected Cargo
//! executable. They guard the actual commands, caller flag inheritance,
//! development preflight ordering, and the explicit routes used for coverage
//! and stable release builds.

use std::{io, process::Command};

use rstest::rstest;

/// Cargo executable substituted into evaluated Make commands.
const PROBE_CARGO: &str = "probe-cargo";
const NATIVE_TARGET: &str = "x86_64-unknown-linux-gnu";
const CROSS_TARGET: &str = "aarch64-unknown-linux-gnu";
const NATIVE_SPLIT_TARGET: &str = "--target x86_64-unknown-linux-gnu";
const NATIVE_JOINED_TARGET: &str = "--target=x86_64-unknown-linux-gnu";
const CROSS_SPLIT_TARGET: &str = "--target aarch64-unknown-linux-gnu";
const CROSS_JOINED_TARGET: &str = "--target=aarch64-unknown-linux-gnu";
const DEVELOPMENT_FLAGS: [&str; 3] = [
    "-Zthreads=8",
    "-Clinker=evert-clang-mold",
    "-Clink-arg=-fuse-ld=mold",
];
const HOSTILE_RUST_FLAGS: &str = concat!(
    "-D warnings -Zcodegen-backend=cranelift ",
    "-Zthreads=8 -Clinker=evert-clang-mold ",
    "-Clink-arg=-fuse-ld=mold"
);

/// Captured status and output from an evaluated Make target.
struct MakeDryRun {
    /// Whether Make completed successfully.
    succeeded: bool,
    /// Commands that Make would execute.
    stdout: String,
    /// Diagnostics emitted while Make evaluated the target.
    stderr: String,
}

/// Evaluates a Make target without running its recipe commands.
fn make_dry_run(target: &str, build_host: &str, build_arch: &str) -> io::Result<MakeDryRun> {
    make_dry_run_with_options(target, build_host, build_arch, &[])
}

/// Evaluates a Make route with explicit command-line variable assignments.
fn make_dry_run_with_options(
    target: &str,
    build_host: &str,
    build_arch: &str,
    options: &[(&str, &str)],
) -> io::Result<MakeDryRun> {
    let build_host_assignment = format!("BUILD_HOST_OS={build_host}");
    let build_arch_assignment = format!("BUILD_HOST_ARCH={build_arch}");
    let mut command = Command::new("make");
    command
        .args([
            "--dry-run",
            "--always-make",
            "--no-print-directory",
            target,
            &build_host_assignment,
            &build_arch_assignment,
            "CARGO=probe-cargo",
        ])
        .env("RUSTFLAGS", HOSTILE_RUST_FLAGS)
        .env("CARGO_ENCODED_RUSTFLAGS", "encoded-caller-flags")
        .env("GITHUB_ACTIONS", "false")
        .current_dir(env!("CARGO_MANIFEST_DIR"));
    for (name, value) in options {
        command.arg(format!("{name}={value}"));
    }
    let output = command.output()?;
    Ok(MakeDryRun {
        succeeded: output.status.success(),
        stdout: String::from_utf8_lossy(&output.stdout).into_owned(),
        stderr: String::from_utf8_lossy(&output.stderr).into_owned(),
    })
}

/// Finds logical Cargo commands in evaluated Make output, including continuations.
fn cargo_invocation_lines(output: &str) -> Vec<String> {
    let mut logical_lines = Vec::new();
    let mut pending = String::new();
    for line in output.lines() {
        let trimmed = line.trim_end();
        let is_continued = trimmed.ends_with('\\');
        let content = trimmed.strip_suffix('\\').unwrap_or(trimmed).trim();
        if !pending.is_empty() {
            pending.push(' ');
        }
        pending.push_str(content);
        if !is_continued {
            logical_lines.push(std::mem::take(&mut pending));
        }
    }
    if !pending.is_empty() {
        logical_lines.push(pending);
    }

    logical_lines
        .into_iter()
        .filter(|line| {
            line.split_whitespace().any(|word| {
                word == PROBE_CARGO
                    || word == "cargo"
                    || word == "cargo.exe"
                    || word.ends_with("/cargo")
                    || word.ends_with("/cargo.exe")
            })
        })
        .collect()
}

/// Isolates the compiler environment applied after a cross-route preflight.
fn effective_cargo_route(command: &str) -> &str {
    command
        .split_once("exec env -u CARGO_ENCODED_RUSTFLAGS ")
        .map_or(command, |(_, route)| route)
}

/// Checks that a development command keeps the standard flags for its host.
fn has_development_route(command: &str, build_host: &str, build_arch: &str) -> bool {
    let required_flags = ["env -u CARGO_ENCODED_RUSTFLAGS", "-D warnings"];
    let development_is_supported =
        build_host == "Linux" && matches!(build_arch, "x86_64" | "aarch64");
    let effective_route = effective_cargo_route(command);
    let has_guarded_flags = command.contains("bash -c 'make_flags=$1; shift; effective_flags=");
    let rustflags_assignment = if has_guarded_flags {
        "RUSTFLAGS=\"$effective_flags\""
    } else {
        "RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }"
    };

    required_flags.iter().all(|flag| command.contains(flag))
        && effective_route.contains(rustflags_assignment)
        && DEVELOPMENT_FLAGS
            .iter()
            .all(|flag| effective_route.contains(flag) == development_is_supported)
}

/// Confirms every development Cargo line uses the caller's injected binary,
/// preserves inherited `RUSTFLAGS`, and carries the selected host flags.
#[rstest]
#[case::linux_x86_64_build("build", 1, "Linux", "x86_64")]
#[case::darwin_build_excludes_dev_flags("build", 1, "Darwin", "x86_64")]
#[case::linux_aarch64_build("build", 1, "Linux", "aarch64")]
#[case::linux_x86_64_test("test", 2, "Linux", "x86_64")]
#[case::darwin_test_excludes_dev_flags("test", 2, "Darwin", "x86_64")]
#[case::linux_aarch64_test("test", 2, "Linux", "aarch64")]
#[case::linux_x86_64_lint("lint", 2, "Linux", "x86_64")]
#[case::darwin_lint_excludes_dev_flags("lint", 2, "Darwin", "x86_64")]
#[case::linux_aarch64_lint("lint", 2, "Linux", "aarch64")]
#[case::linux_x86_64_typecheck("typecheck", 1, "Linux", "x86_64")]
#[case::darwin_typecheck_excludes_dev_flags("typecheck", 1, "Darwin", "x86_64")]
#[case::linux_aarch64_typecheck("typecheck", 1, "Linux", "aarch64")]
fn development_targets_expand_each_cargo_command(
    #[case] target: &str,
    #[case] expected_commands: usize,
    #[case] build_host: &str,
    #[case] build_arch: &str,
) {
    let run = make_dry_run(target, build_host, build_arch).expect("make --dry-run must run");
    assert!(
        run.succeeded,
        "`make --dry-run {target}` failed for {build_host}: {}",
        run.stderr
    );

    let commands = cargo_invocation_lines(&run.stdout);
    assert_eq!(
        commands.len(),
        expected_commands,
        "`make --dry-run {target}` must expose every Cargo invocation: {}",
        run.stdout
    );
    for command in &commands {
        assert!(
            command.split_whitespace().any(|word| word == PROBE_CARGO),
            "`make --dry-run {target}` bypassed CARGO=probe-cargo: {command}"
        );
        assert!(
            has_development_route(command, build_host, build_arch),
            "`make --dry-run {target}` selected the wrong development route for \
             {build_host}/{build_arch}: {command}"
        );
    }

    let (preflight_position, first_cargo_position) =
        whitaker_binding::preflight_and_cargo_positions(&run.stdout)
            .expect("development targets must preflight before exposing Cargo commands");
    assert!(
        preflight_position < first_cargo_position,
        "`make --dry-run {target}` must check build tools before compilation: {}",
        run.stdout
    );
}

/// Keeps the lint suite on its own toolchain and away from development flags.
#[test]
fn whitaker_does_not_inherit_development_flags() {
    let run = make_dry_run_with_options(
        "lint",
        "Linux",
        "x86_64",
        &[("RUST_FLAGS", HOSTILE_RUST_FLAGS)],
    )
    .expect("make --dry-run must run");
    assert!(
        run.succeeded,
        "`make --dry-run lint` failed: {}",
        run.stderr
    );
    let commands: Vec<_> = run
        .stdout
        .lines()
        .filter(|line| line.split_whitespace().any(|word| word == "whitaker"))
        .collect();
    assert_eq!(
        commands.len(),
        1,
        "lint must expose one Whitaker invocation: {}",
        run.stdout
    );
    let command = commands
        .first()
        .expect("lint must expose a Whitaker command");
    assert!(
        command.contains("env -u CARGO_ENCODED_RUSTFLAGS"),
        "Whitaker must receive an isolated compiler environment: {command}"
    );
    assert!(
        command.contains("RUSTFLAGS=\"-D warnings\""),
        "Whitaker must use its isolated warnings policy: {command}"
    );
    assert!(
        !command.contains("${RUSTFLAGS") && !command.contains("encoded-caller-flags"),
        "Whitaker must not inherit ambient compiler flags: {command}"
    );
    for development_flag in DEVELOPMENT_FLAGS {
        assert!(
            !command.contains(development_flag),
            "Whitaker must not inherit the repository development route: {command}"
        );
    }
}

/// Keeps coverage and stable release compilation outside the development
/// backend, frontend, and linker route.
#[rstest]
#[case::linux_x86_64_coverage("coverage", 1, "Linux", "x86_64")]
#[case::linux_x86_64_release("release", 1, "Linux", "x86_64")]
#[case::linux_aarch64_release("release", 1, "Linux", "aarch64")]
#[case::darwin_x86_64_release("release", 1, "Darwin", "x86_64")]
fn excluded_targets_expand_their_own_cargo_commands(
    #[case] target: &str,
    #[case] expected_commands: usize,
    #[case] build_host: &str,
    #[case] build_arch: &str,
) {
    let run = make_dry_run(target, build_host, build_arch).expect("make --dry-run must run");
    assert!(
        run.succeeded,
        "`make --dry-run {target}` failed for {build_host}: {}",
        run.stderr
    );

    let commands = cargo_invocation_lines(&run.stdout);
    assert_eq!(
        commands.len(),
        expected_commands,
        "`make --dry-run {target}` must expose every Cargo invocation: {}",
        run.stdout
    );
    for command in &commands {
        assert!(
            command.split_whitespace().any(|word| word == PROBE_CARGO),
            "`make --dry-run {target}` bypassed CARGO=probe-cargo: {command}"
        );
        assert!(
            command.contains("env -u CARGO_ENCODED_RUSTFLAGS"),
            "`make --dry-run {target}` must clear encoded flags before applying its route: \
             {command}"
        );
        assert!(
            command.contains("RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }"),
            "held-out target {target} must preserve caller RUSTFLAGS: {command}"
        );
        for development_flag in DEVELOPMENT_FLAGS {
            assert!(
                !command.contains(development_flag),
                "`make --dry-run {target}` inherited {development_flag}: {command}"
            );
        }
    }

    if target == "coverage" {
        let coverage_command = commands
            .first()
            .expect("coverage must expose its Cargo invocation");
        assert!(
            coverage_command.contains("CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=clang")
                && coverage_command.contains("-fuse-ld=lld")
                && coverage_command.contains("RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }"),
            "coverage must retain its LLVM-compatible linker route: {coverage_command}"
        );
    } else {
        let release_command = commands
            .first()
            .expect("release must expose its Cargo invocation");
        assert!(
            release_command.contains("probe-cargo +stable")
                && release_command.contains("RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }"),
            "release must select stable Rust and preserve caller compiler flags: {release_command}"
        );
    }
}

/// Confirms a missing pinned build tool stops typechecking with repair guidance.
#[cfg(target_os = "linux")]
#[test]
fn failed_build_tools_preflight_stops_typecheck_before_cargo() {
    let output = Command::new("make")
        .args([
            "--always-make",
            "--no-print-directory",
            "typecheck",
            "CARGO=echo CARGO_WAS_RUN",
        ])
        .env("BUILD_TOOLS_PREFIX", "/dev/null/evert-pr64-missing")
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
        .expect("make typecheck must run");
    let diagnostics = format!(
        "{}\n{}",
        String::from_utf8_lossy(&output.stdout),
        String::from_utf8_lossy(&output.stderr)
    );

    assert!(
        !output.status.success(),
        "typecheck must stop when the pinned build tools are unavailable: {diagnostics}"
    );
    assert!(
        diagnostics.contains("make install-build-tools"),
        "the failed preflight must explain how to install the required tools: {diagnostics}"
    );
    assert!(
        !diagnostics.contains("CARGO_WAS_RUN"),
        "the typecheck Cargo recipe must not run after a failed preflight: {diagnostics}"
    );
}

/// Checks failure propagation after the successful Cargo command stubs.
#[path = "makefile_contract_support/whitaker_binding.rs"]
mod whitaker_binding;

#[path = "makefile_contract_support/clippy_target_route.rs"]
mod clippy_target_route;

#[cfg(target_os = "linux")]
#[path = "makefile_contract_support/cross_caller_flags.rs"]
mod cross_caller_flags;
