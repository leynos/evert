//! Contract tests for reading toolchain pins and Cargo configuration fixtures.

use rstest::rstest;

use super::{
    BETA,
    BUILD_LEAKS_DEVELOPMENT_FLAGS,
    MALFORMED_CHANNEL,
    MALFORMED_NIGHTLY_DATE,
    NIGHTLY,
    NIGHTLY_FOO,
    NIGHTLY_OK,
    NIGHTLY_SPELLED_APART,
    NO_CHANNEL,
    SPREAD_ARRAY,
    STABLE,
    STABLE_CHANNEL,
    STABLE_OK,
    STABLE_WITH_THREADS,
    TARGET_LOSES_DRIVER,
    TARGET_LOSES_LINKER,
    TARGET_LOSES_THREADS,
    TARGET_SELECTS_CRANELIFT,
    TWO_CHANNELS,
    UNDATED_NIGHTLY,
    UNKNOWN_CHANNEL,
    X86_ONLY_LINUX,
    config,
    config::{Pin, PinError, applies_to_target, config_problems},
    none_of,
};

/// One Cargo config fixture, its toolchain mode, and expected diagnostics.
#[derive(Clone, Copy)]
struct ConfigCase {
    source: &'static str,
    pin: Pin,
    expected_problems: usize,
}

/// Checks that a configuration fixture produces its expected diagnostic count.
///
/// ```text
/// draws(ConfigCase { source: "", pin: Pin::Nightly, expected_problems: 2 }) -> Ok(())
/// ```
fn draws(case: ConfigCase) -> Result<(), String> {
    let found = config_problems(case.source, case.pin)?.len();
    if found == case.expected_problems {
        Ok(())
    } else {
        Err(format!(
            "{:?}: {found} problems, not {}",
            case.source, case.expected_problems
        ))
    }
}

/// Config fixtures pair raw syntax with the pin whose rules interpret it.
#[rstest]
#[case::compliant_nightly(ConfigCase {
    source: NIGHTLY_OK,
    pin: Pin::Nightly,
    expected_problems: 0,
})]
#[case::linker_spelled_as_a_pair(ConfigCase {
    source: NIGHTLY_SPELLED_APART,
    pin: Pin::Nightly,
    expected_problems: 0,
})]
#[case::compliant_stable(ConfigCase {
    source: STABLE_OK,
    pin: Pin::Stable,
    expected_problems: 0,
})]
#[case::target_selects_unsupported_cranelift(ConfigCase {
    source: TARGET_SELECTS_CRANELIFT,
    pin: Pin::Nightly,
    expected_problems: 1,
})]
#[case::target_loses_the_frontend(ConfigCase {
    source: TARGET_LOSES_THREADS,
    pin: Pin::Nightly,
    expected_problems: 1,
})]
#[case::target_loses_the_linker(ConfigCase {
    source: TARGET_LOSES_LINKER,
    pin: Pin::Nightly,
    expected_problems: 1,
})]
#[case::target_loses_the_pinned_driver(ConfigCase {
    source: TARGET_LOSES_DRIVER,
    pin: Pin::Nightly,
    expected_problems: 1,
})]
#[case::build_table_leaks_to_all_targets(ConfigCase {
    source: BUILD_LEAKS_DEVELOPMENT_FLAGS,
    pin: Pin::Nightly,
    expected_problems: 3,
})]
#[case::x86_64_only_linux_table_misses_other_architectures(ConfigCase {
    source: X86_ONLY_LINUX,
    pin: Pin::Nightly,
    expected_problems: 3,
})]
#[case::stable_names_the_frontend(ConfigCase {
    source: STABLE_WITH_THREADS,
    pin: Pin::Stable,
    expected_problems: 1,
})]
#[case::empty_configuration(ConfigCase {
    source: "",
    pin: Pin::Nightly,
    expected_problems: 2,
})]
fn the_configuration_reader_reports_each_defect(#[case] case: ConfigCase) -> Result<(), String> {
    draws(case)
}

/// Scenario: the config reader refuses a multiline `rustflags` array.
///
/// Invariant: it cannot read only part of the array and let a lost flag pass.
#[test]
fn a_rustflags_array_spread_over_lines_is_refused() -> Result<(), String> {
    match config_problems(SPREAD_ARRAY, Pin::Nightly) {
        Ok(_) => Err("a rustflags array spread over several lines was read".to_owned()),
        Err(_) => Ok(()),
    }
}

/// One toolchain source and the pin or parsing error it should produce.
struct ToolchainCase {
    source: &'static str,
    expected: Result<Pin, PinError>,
}

/// Scenarios distinguish supported channels from malformed or unknown values.
#[rstest]
#[case::nightly(ToolchainCase {
    source: NIGHTLY,
    expected: Ok(Pin::Nightly),
})]
#[case::undated_nightly(ToolchainCase {
    source: UNDATED_NIGHTLY,
    expected: Ok(Pin::Nightly),
})]
#[case::stable(ToolchainCase {
    source: STABLE,
    expected: Ok(Pin::Stable),
})]
#[case::stable_channel(ToolchainCase {
    source: STABLE_CHANNEL,
    expected: Ok(Pin::Stable),
})]
#[case::beta(ToolchainCase {
    source: BETA,
    expected: Ok(Pin::Stable),
})]
#[case::missing(ToolchainCase {
    source: NO_CHANNEL,
    expected: Err(PinError::MissingChannel),
})]
#[case::repeated(ToolchainCase {
    source: TWO_CHANNELS,
    expected: Err(PinError::MultipleChannels(2)),
})]
#[case::unknown(ToolchainCase {
    source: UNKNOWN_CHANNEL,
    expected: Err(PinError::UnsupportedChannel("weekly".to_owned())),
})]
#[case::unrecognized_nightly_suffix(ToolchainCase {
    source: NIGHTLY_FOO,
    expected: Err(PinError::UnsupportedChannel("nightly-foo".to_owned())),
})]
#[case::malformed_nightly_date(ToolchainCase {
    source: MALFORMED_NIGHTLY_DATE,
    expected: Err(PinError::UnsupportedChannel("nightly-2026-5-28".to_owned())),
})]
#[case::malformed_channel_assignment(ToolchainCase {
    source: MALFORMED_CHANNEL,
    expected: Err(PinError::MalformedChannel),
})]
fn the_pin_reader_tells_the_channels_apart(#[case] case: ToolchainCase) {
    assert_eq!(Pin::read(case.source), case.expected);
}

/// Checks that the repository's config applies to Linux targets of both arches.
#[test]
fn the_cfg_source_applies_to_non_x86_linux_targets() -> Result<(), String> {
    if !applies_to_target(config::CONFIG, "x86_64-unknown-linux-gnu")? {
        return Err("the Linux cfg source does not apply to x86_64 Linux".to_owned());
    }
    if !applies_to_target(config::CONFIG, "aarch64-unknown-linux-gnu")? {
        return Err("the Linux cfg source does not apply to aarch64 Linux".to_owned());
    }
    if applies_to_target(X86_ONLY_LINUX, "aarch64-unknown-linux-gnu")? {
        return Err("an x86_64-only target table unexpectedly applies to aarch64".to_owned());
    }
    if applies_to_target(config::CONFIG, "x86_64-apple-darwin")? {
        return Err("the Linux cfg source unexpectedly applies to macOS".to_owned());
    }
    if config_problems(X86_ONLY_LINUX, Pin::Nightly)?.is_empty() {
        return Err("an x86_64-only Linux table must be reported as a defect".to_owned());
    }
    Ok(())
}

/// Checks every repository Rust-flags source against its pinned toolchain.
#[test]
fn every_rustflags_source_is_consistent_with_the_pin() -> Result<(), String> {
    none_of(&config_problems(
        config::CONFIG,
        Pin::read(config::TOOLCHAIN).map_err(|error| error.to_string())?,
    )?)
}
