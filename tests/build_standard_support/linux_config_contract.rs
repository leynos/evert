//! Focused fixtures for the Linux-wide Cargo configuration contract.

use rstest::rstest;

use super::{
    NIGHTLY_OK,
    X86_ONLY_LINUX,
    config::{Pin, applies_to_target, config_problems},
};

/// The generic Cargo cfg fixture must cover Linux regardless of architecture.
/// An x86_64-only target section cannot satisfy that repository contract.
#[rstest]
#[case::x86_64("x86_64-unknown-linux-gnu")]
#[case::aarch64("aarch64-unknown-linux-gnu")]
#[case::armv7("armv7-unknown-linux-gnueabihf")]
#[case::riscv64("riscv64gc-unknown-linux-gnu")]
fn linux_configuration_fixture_covers_each_linux_target(
    #[case] target: &str,
) -> Result<(), String> {
    if !applies_to_target(NIGHTLY_OK, target)? {
        return Err(format!(
            "the cfg(target_os = \"linux\") fixture misses {target}"
        ));
    }
    if !config_problems(NIGHTLY_OK, Pin::Nightly)?.is_empty() {
        return Err("the all-Linux fixture does not satisfy the nightly contract".to_owned());
    }
    if applies_to_target(X86_ONLY_LINUX, target)? {
        return Err(format!(
            "the x86_64-only fixture unexpectedly applies to {target}"
        ));
    }
    if config_problems(X86_ONLY_LINUX, Pin::Nightly)?.is_empty() {
        return Err("the x86_64-only fixture replaced the required Linux cfg source".to_owned());
    }
    Ok(())
}
