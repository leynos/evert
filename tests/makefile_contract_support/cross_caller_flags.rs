//! Contracts for caller flags on explicit non-native Cargo routes.

use std::process::{Command, Output};

use rstest::rstest;

use super::DEVELOPMENT_FLAGS;

const PROBE_CARGO: &str = "probe-cargo";
const PRINT_FLAGS_CARGO: &str = r#"sh -c 'printf "observed=%s\n" "$RUSTFLAGS"'"#;
const PRINT_FLAGS_AND_ARGS_CARGO: &str = concat!(
    r#"sh -c 'printf "flags=%s\n" "$RUSTFLAGS"; "#,
    r#"printf "arg=%s\n" "$0" "$@"' probe-cargo"#,
);

/// Runs Make with a cross target and controlled Rust flags.
fn make_cross_route(
    inherited_flags: &str,
    make_flags: Option<&str>,
    cargo: &str,
    dry_run: bool,
) -> std::io::Result<Output> {
    let mut command = Command::new("make");
    command.args([
        "--always-make",
        "--old-file=check-build-tools",
        "--no-print-directory",
    ]);
    if dry_run {
        command.arg("--dry-run");
    } else {
        command.arg("--silent");
    }
    command.args([
        "typecheck-rust",
        "BUILD_HOST_OS=Linux",
        "BUILD_HOST_ARCH=x86_64",
        "CARGO_BUILD_TARGET=aarch64-unknown-linux-gnu",
    ]);
    // Make re-expands recursive command-line variables in recipes. Escape
    // shell variables in this test double so they reach the fake Cargo intact.
    command.arg(format!("CARGO={}", cargo.replace('$', "$$")));
    if let Some(flags) = make_flags {
        command.arg(format!("RUST_FLAGS={flags}"));
    }
    command
        .env("RUSTFLAGS", inherited_flags)
        .env("CARGO_ENCODED_RUSTFLAGS", "encoded-caller-flags")
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()
}

/// Returns the evaluated Cargo route from a dry-run transcript.
fn evaluated_probe_route(output: &Output) -> Option<String> {
    String::from_utf8_lossy(&output.stdout)
        .lines()
        .find(|line| line.contains(&format!("{PROBE_CARGO} check")))
        .map(str::to_owned)
}

/// Confirms a cross route checks caller flags before preserving the Cargo call.
#[rstest]
#[case::inherited_compact_backend("-Zcodegen-backend=cranelift", None)]
#[case::make_split_backend("", Some("-Z codegen-backend=cranelift"))]
#[case::inherited_compact_frontend("-Zthreads=8", None)]
#[case::make_split_frontend("", Some("-Z threads=8"))]
#[case::inherited_joined_evert_wrapper("-Clinker=/opt/tools/evert-clang-mold", None)]
#[case::make_split_c_evert_wrapper("", Some("-C linker=/opt/tools/evert-clang-mold"))]
#[case::inherited_split_clinker_evert_wrapper("-Clinker /opt/tools/evert-clang-mold", None)]
#[case::inherited_joined_ld_linker("-Clinker=/usr/bin/ld.mold", None)]
#[case::make_split_c_ld_linker("", Some("-C linker=/usr/bin/ld.mold"))]
#[case::inherited_split_clinker_ld_linker("-Clinker /usr/bin/ld.mold", None)]
#[case::inherited_compact_link_arg("-Clink-arg=-fuse-ld=mold", None)]
#[case::make_split_link_arg("", Some("-C link-arg=-fuse-ld=mold"))]
#[case::inherited_split_link_arg("-Clink-arg -fuse-ld=mold", None)]
#[case::malformed_backend_value("-Zcodegen-backend=cranelift-probe", None)]
#[case::malformed_frontend_value("-Zthreads=8-probe", None)]
fn cross_route_rejects_development_flags_before_cargo(
    #[case] inherited_flags: &str,
    #[case] make_flags: Option<&str>,
) {
    let dry_run = make_cross_route(inherited_flags, make_flags, PROBE_CARGO, true)
        .expect("Make dry-run must evaluate");
    assert!(
        dry_run.status.success(),
        "Make dry-run failed: {}",
        String::from_utf8_lossy(&dry_run.stderr)
    );
    let route = evaluated_probe_route(&dry_run).expect("dry-run must expose the Cargo route");
    assert!(
        route.contains("bash -c 'make_flags=$1; shift; effective_flags=")
            && route.contains("incompatible flag from inherited RUSTFLAGS or Make RUST_FLAGS")
            && route.contains("exec env -u CARGO_ENCODED_RUSTFLAGS")
            && route.contains("probe-cargo check --all-targets --all-features"),
        "cross route must inspect caller flags before the unchanged Cargo selection: {route}"
    );

    let run = make_cross_route(inherited_flags, make_flags, "echo CARGO_WAS_RUN", false)
        .expect("controlled Make route must run");
    let diagnostics = format!(
        "{}\n{}",
        String::from_utf8_lossy(&run.stdout),
        String::from_utf8_lossy(&run.stderr)
    );
    assert!(
        !run.status.success(),
        "cross route must reject the development flag: {diagnostics}"
    );
    assert!(
        diagnostics.contains("incompatible flag"),
        "failure must identify the incompatible caller flag: {diagnostics}"
    );
    assert!(
        diagnostics.contains("inherited RUSTFLAGS or Make RUST_FLAGS"),
        "failure must name the caller flag sources: {diagnostics}"
    );
    assert!(
        !diagnostics.contains("CARGO_WAS_RUN"),
        "Cargo must not run after the cross-route preflight fails: {diagnostics}"
    );
}

/// Confirms benign inherited and Make flags survive the cross-route preflight.
#[test]
fn cross_route_preserves_benign_flags_from_both_callers() {
    let make_flags = "-C opt-level=1";
    let output = make_cross_route(
        "-D warnings -C debuginfo=1",
        Some(make_flags),
        PRINT_FLAGS_CARGO,
        false,
    )
    .expect("controlled Make route must run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "benign cross-route flags must pass: {stdout}{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        stdout.trim(),
        "observed=-D warnings -C debuginfo=1 -C opt-level=1",
        "the cross route must preserve inherited and Make flags exactly"
    );
}

/// Confirms the quoted Make-flag transport does not split or execute metacharacters.
#[test]
fn cross_route_preserves_single_quotes_and_shell_metacharacters() {
    let make_flags = "-C link-arg=quote'and;token";
    let output = make_cross_route("-D warnings", Some(make_flags), PRINT_FLAGS_CARGO, false)
        .expect("controlled Make route must run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "quoted benign flags must pass: {stdout}{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        stdout.trim(),
        "observed=-D warnings -C link-arg=quote'and;token",
        "single quotes and semicolons must remain flag data"
    );
}

/// Allows a directory name containing `mold` when the linker basename is benign.
#[test]
fn cross_route_allows_linker_path_and_preserves_cargo_argv() {
    let make_flags = "-Clinker=/opt/moldings/clang";
    let output = make_cross_route(
        "-D warnings",
        Some(make_flags),
        PRINT_FLAGS_AND_ARGS_CARGO,
        false,
    )
    .expect("controlled Make route must run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "a benign directory name containing `mold` must pass: {stdout}{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        stdout.trim(),
        concat!(
            "flags=-D warnings -Clinker=/opt/moldings/clang\n",
            "arg=probe-cargo\n",
            "arg=check\n",
            "arg=--all-targets\n",
            "arg=--all-features"
        ),
        "the benign route must preserve its flags and Cargo argv order"
    );
}

/// Allows a linker symbol with a tool-specific name and preserves Cargo arguments.
#[test]
fn cross_route_allows_linker_symbol_and_preserves_cargo_argv() {
    let make_flags = "-Clink-arg=-Wl,--undefined=mold_init";
    let output = make_cross_route(
        "-D warnings",
        Some(make_flags),
        PRINT_FLAGS_AND_ARGS_CARGO,
        false,
    )
    .expect("controlled Make route must run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "a linker symbol must pass: {stdout}{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(
        stdout.trim(),
        concat!(
            "flags=-D warnings -Clink-arg=-Wl,--undefined=mold_init\n",
            "arg=probe-cargo\n",
            "arg=check\n",
            "arg=--all-targets\n",
            "arg=--all-features"
        ),
        "the benign route must preserve its flags and Cargo argv order"
    );
}

/// Confirms an intentionally native route retains the selected backend flag.
#[cfg(target_os = "linux")]
#[test]
fn native_route_keeps_the_development_flag() {
    let mut command = Command::new("make");
    command.args([
        "--always-make",
        "--old-file=check-build-tools",
        "--no-print-directory",
        "--silent",
        "typecheck-rust",
        "BUILD_HOST_OS=Linux",
        "BUILD_HOST_ARCH=x86_64",
        "CARGO=sh -c 'printf \"observed=%s\\n\" \"$$RUSTFLAGS\"'",
    ]);
    command
        .env("RUSTFLAGS", "-Zcodegen-backend=cranelift")
        .env("CARGO_ENCODED_RUSTFLAGS", "encoded-caller-flags")
        .current_dir(env!("CARGO_MANIFEST_DIR"));
    let output = command.output().expect("native Make route must run");
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "native route may retain its development flags: {stdout}{}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(
        stdout
            .lines()
            .any(|line| line.starts_with("observed=-Zcodegen-backend=cranelift ")),
        "native route must pass through the caller's selected backend: {stdout}"
    );
    assert!(
        DEVELOPMENT_FLAGS.iter().all(|flag| stdout.contains(flag)),
        "native route must retain the complete development flag set: {stdout}"
    );
}
