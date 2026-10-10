//! Checks that stable Cargo can read the repository configuration after the
//! release route clears the development rustflags.
//!
//! This probe deliberately asks for a missing binary, so Cargo must load the
//! project configuration but never invokes rustc or compiles the repository.
//! The build-backend contract checks both stable release command routes; the
//! verbose release probe records the compiler arguments separately.

use std::process::Command;

use rstest::rstest;

/// Stable Cargo's diagnostic when it cannot accept the configuration.
const CONFIG_REFUSAL: &str = "is not valid";
/// What stable Cargo reports once the configuration has loaded.
const ACCEPTED: &str = "no bin target named";

/// Judges the diagnostics stable Cargo printed for the probe build.
///
/// Only the missing-target message proves the configuration loaded. Any other
/// output, including a stable toolchain that is not installed, is reported
/// rather than read as a pass, so an environment that cannot run the probe
/// cannot certify the configuration.
fn judge(stderr: &str) -> Result<(), String> {
    if stderr.contains(CONFIG_REFUSAL) {
        return Err(format!(
            "stable Cargo refused the repository configuration:\n{stderr}"
        ));
    }
    if !stderr.contains(ACCEPTED) {
        return Err(format!(
            concat!(
                "the probe did not reach the target lookup, so the configuration was not ",
                "judged (is the stable toolchain installed? `rustup toolchain install stable ",
                "--profile minimal`):\n{}"
            ),
            stderr
        ));
    }
    Ok(())
}

/// Scenario: the diagnostics stable Cargo prints for the probe in each state.
///
/// Invariant: only the missing-target message passes; a refused profile and
/// unrecognized output, such as a missing toolchain, both fail.
#[rstest]
#[case::configuration_loaded("error: no bin target named `no-such-bin`\n", true)]
#[case::unsupported_configuration_refused(
    concat!(
        "error: config profile `dev` is not valid (defined in `.cargo/config.toml`)\n\n",
        "Caused by:\n  feature `codegen-backend` is required\n"
    ),
    false
)]
#[case::toolchain_missing(
    "error: toolchain 'stable-x86_64-unknown-linux-gnu' is not installed\n",
    false
)]
#[case::no_output("", false)]
fn the_probe_output_is_judged_strictly(#[case] stderr: &str, #[case] passes: bool) {
    assert_eq!(judge(stderr).is_ok(), passes, "{stderr:?}");
}

/// Scenario: stable Cargo, run through `rustup` so the pinned nightly does not
/// answer for it, is asked to build a binary that does not exist.
///
/// Invariant: it reaches the target lookup, so it accepted the configuration.
#[test]
fn stable_cargo_accepts_configuration_with_release_flag_overrides() {
    let output = Command::new("rustup")
        .args([
            "run",
            "stable",
            "cargo",
            "build",
            "--release",
            "--offline",
            "--bin",
            "no-such-bin",
        ])
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        // The release clears both Cargo flag sources before stable Cargo
        // starts. This probe uses the same environment while leaving the
        // repository's configuration in place for Cargo to discover.
        .env("RUSTFLAGS", "")
        .env_remove("CARGO_ENCODED_RUSTFLAGS")
        .output()
        .expect("running `rustup run stable cargo`");
    if let Err(reason) = judge(&String::from_utf8_lossy(&output.stderr)) {
        panic!("{reason}");
    }
}
