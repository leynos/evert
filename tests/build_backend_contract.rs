//! Checks how the repository selects its development flags and backend.
//!
//! LLVM is the development default; the Cranelift `[profile.dev]` key in
//! `.cargo/config.toml` is commented out and is never a `rustflags` entry. Development-only
//! rustflags stay in the generic Linux source, and the Make release route
//! assigns `RUSTFLAGS` so none of them reach a release build, which keeps the
//! LLVM backend.

use std::{io, process::Command};

#[path = "build_backend_contract_support/toml.rs"]
mod toml;
use toml::{rustflags_include, tables_with_rustflag};

/// Regression tests for quoted TOML hash handling.
#[path = "build_backend_contract_support/quoted_hash.rs"]
mod quoted_hash_tests;

/// Repository Cargo configuration inspected by the routing contract.
const CARGO_CONFIG: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/.cargo/config.toml"));
/// Supported development flags scoped to the generic Linux cfg source.
const DEVELOPMENT_FLAGS: [&str; 3] = ["-Zthreads=8", "fuse-ld=mold", "-Clinker=evert-clang-mold"];
/// The Cargo cfg table that applies to every Linux target architecture.
const DEVELOPMENT_TABLE: &str = "target.'cfg(target_os = \"linux\")'";

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
        "the backend defaults to LLVM, and an opt-in uses the dev profile key, not a rustflags entry"
    );
}

/// The Make release target must substitute `CARGO`, replace the Cargo flag
/// sources and add no development flags of its own.
#[test]
fn make_release_route_preserves_caller_flags() {
    let output = release_dry_run().expect("make --dry-run release should run");
    assert!(
        output.status.success(),
        "make --dry-run release failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    let stdout = String::from_utf8(output.stdout).expect("make output should be UTF-8");
    let release_commands: Vec<String> = stdout
        .lines()
        .map(|line| line.split_whitespace().collect::<Vec<_>>().join(" "))
        .filter(|line| line.contains("probe-cargo") && line.contains("build"))
        .filter(|line| line.contains("--release"))
        .collect();

    assert_eq!(
        release_commands.len(),
        1,
        "unexpected Make release route: {stdout}"
    );
    let command = release_commands
        .first()
        .expect("one release command was asserted");
    assert!(
        command.contains("env -u CARGO_ENCODED_RUSTFLAGS") && command.contains("RUSTFLAGS="),
        "release must replace both Cargo flag sources: {command}"
    );
    for flag in [
        "-Zcodegen-backend=cranelift",
        "-Zthreads=8",
        "fuse-ld=mold",
        "evert-clang-mold",
    ] {
        assert!(
            !command.contains(flag),
            "release must not carry the development flag {flag}: {command}"
        );
    }
}
