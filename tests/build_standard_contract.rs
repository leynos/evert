//! Contract tests for the Rust build standard.
//!
//! The standard keeps rustc's LLVM backend and makes the parallel rustc
//! frontend and pinned `mold` wrapper the defaults for Linux development
//! builds. Cargo reads the latter settings from .cargo/config.toml, but an
//! assigned RUSTFLAGS replaces that target source. Make therefore restates
//! them on supported Linux hosts, while coverage and release keep their own
//! compiler routes.
//!
//!
//! The Makefile clauses run `make -n` and read the commands it would run,
//! rather than the Makefile's text, so a flag lost through a variable or a
//! recipe edit fails here. They check Linux `x86_64`, Linux `aarch64`, and
//! `macOS/x86_64` because the Cargo default is scoped to Linux by operating
//! system. The
//! listed targets and workflows are this repository's own: one that stops
//! being defined fails the contract, so the check cannot quietly stop covering
//! it. Each CI workflow that sets up Rust passes `install-mold: 'true'`, so
//! the Linux jobs have the linker. The readers are driven against fixtures
//! first, because a rule exercised only over this repository's own compliant
//! files would pass whether or not it detects anything.

#[path = "build_standard_support/host.rs"]
mod build_host;
#[path = "build_standard_support/ci_steps.rs"]
mod ci_steps;
#[path = "build_standard_support/config.rs"]
mod config;
#[path = "build_standard_support/config_reader_contract.rs"]
mod config_reader_contract;
#[path = "build_standard_support/coverage_contract.rs"]
mod coverage_contract;
#[path = "build_standard_support/held_out_contract.rs"]
mod held_out_contract;
#[path = "build_standard_support/linux_config_contract.rs"]
mod linux_config_contract;
#[path = "build_standard_support/make.rs"]
mod make;
#[path = "build_standard_support/make_execution.rs"]
mod make_execution;
#[path = "build_standard_support/make_reader_contract.rs"]
mod make_reader_contract;
#[path = "build_standard_support/make_target.rs"]
mod make_target;
#[path = "build_standard_support/properties.rs"]
mod properties;
#[path = "build_standard_support/toolchain_contract.rs"]
mod toolchain_contract;
#[path = "build_standard_support/workflow_contract.rs"]
mod workflow_contract;
use config::{Pin, Problems, TOOLCHAIN};
use make::{
    Host,
    MakeTarget,
    development_problems,
    development_problems_with,
    held_out_problems,
    held_out_target_count,
};
use rstest::rstest;

/// Turns a list of complaints into a test result.
fn none_of(problems: &Problems) -> Result<(), String> {
    if problems.is_empty() {
        Ok(())
    } else {
        Err(format!("{problems:#?}"))
    }
}

/// A toolchain file pinning a nightly channel.
const NIGHTLY: &str = "[toolchain]\nchannel = \"nightly-2026-05-28\"\n";
/// A toolchain file pinning the unqualified nightly channel.
const UNDATED_NIGHTLY: &str = "[toolchain]\nchannel = \"nightly\"\n";
/// A toolchain file pinning a stable channel.
const STABLE: &str = "[toolchain]\nchannel = \"1.94.0\"\n";
/// A toolchain file pinning the stable channel by name.
const STABLE_CHANNEL: &str = "[toolchain]\nchannel = \"stable\"\n";
/// A toolchain file pinning the beta channel.
const BETA: &str = "[toolchain]\nchannel = \"beta\"\n";
/// A toolchain file that names no channel.
const NO_CHANNEL: &str = "[toolchain]\ncomponents = [\"clippy\"]\n";
/// A toolchain file whose channel assignment is not a TOML string.
const MALFORMED_CHANNEL: &str = "[toolchain]\nchannel = nightly\n";
/// A toolchain file that names two channels.
const TWO_CHANNELS: &str = "[toolchain]\nchannel = \"stable\"\nchannel = \"nightly\"\n";
/// A toolchain file naming a channel the standard does not know.
const UNKNOWN_CHANNEL: &str = "[toolchain]\nchannel = \"weekly\"\n";
/// A toolchain file with an unrecognized nightly suffix.
const NIGHTLY_FOO: &str = "[toolchain]\nchannel = \"nightly-foo\"\n";
/// A toolchain file whose nightly date has a short month field.
const MALFORMED_NIGHTLY_DATE: &str = "[toolchain]\nchannel = \"nightly-2026-5-28\"\n";

/// A compliant nightly configuration: the supported Linux route is selected by OS.
const NIGHTLY_OK: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The same target, with the linker flag spelled as the `-C` pair Cargo accepts.
const NIGHTLY_SPELLED_APART: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-C\", \
     \"link-arg=-fuse-ld=mold\"]\n"
);
/// A compliant stable configuration with no development flags.
const STABLE_OK: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = []\n"
);
/// The exact target selects the unsupported Cranelift backend.
const TARGET_SELECTS_CRANELIFT: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zcodegen-backend=cranelift\", \"-Zthreads=8\", ",
    "\"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The exact target lost the parallel frontend flag.
const TARGET_LOSES_THREADS: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The exact target lost the `mold` linker argument.
const TARGET_LOSES_LINKER: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\"]\n"
);
/// The exact target lost the pinned linker wrapper.
const TARGET_LOSES_DRIVER: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// Development flags in `[build]` would leak to every target.
const BUILD_LEAKS_DEVELOPMENT_FLAGS: &str = concat!(
    "[build]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// An x86_64-only Linux table misses other Linux target architectures.
const X86_ONLY_LINUX: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// A stable configuration that names the nightly-only frontend flag.
const STABLE_WITH_THREADS: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\"]\n"
);
/// A `rustflags` array spread over several lines, which the reader refuses.
const SPREAD_ARRAY: &str =
    "[target.'cfg(target_os = \"linux\")']\nrustflags = [\n  \"-Zthreads=8\",\n]\n";

#[test]
fn development_targets_restate_the_flags_on_x86_64_gnu_linux() -> Result<(), String> {
    let pin = Pin::read(TOOLCHAIN).map_err(|error| error.to_string())?;
    let (problems, read) = development_problems(Host::LinuxX86, pin)?;
    none_of(&problems)?;
    if read == 0 {
        return Err(
            "no development target assigns RUSTFLAGS, so the check proves nothing".to_owned(),
        );
    }
    Ok(())
}

#[rstest]
#[case::linux_aarch64(Host::LinuxArm)]
#[case::macos_x86_64(Host::Darwin)]
fn development_targets_route_by_host(#[case] host: Host) -> Result<(), String> {
    let pin = Pin::read(TOOLCHAIN).map_err(|error| error.to_string())?;
    none_of(&development_problems(host, pin)?.0)
}

#[test]
fn development_contract_uses_an_injected_runner() -> Result<(), String> {
    let mut calls = Vec::new();
    let mut runner = |target: MakeTarget, host: Host| {
        calls.push((target, host));
        Ok(concat!(
            "RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }-Zthreads=8 ",
            "-Clinker=evert-clang-mold -Clink-arg=-fuse-ld=mold\" cargo check\n"
        )
        .to_owned())
    };
    let (problems, read) = development_problems_with(Host::LinuxX86, Pin::Nightly, &mut runner)?;
    none_of(&problems)?;
    if read != 4 || calls.len() != 4 {
        return Err(format!(
            "runner read {read} commands over {} calls",
            calls.len()
        ));
    }
    Ok(())
}

#[test]
fn development_contract_propagates_runner_failures() {
    let mut runner =
        |target: MakeTarget, _host: Host| Err(format!("cannot inspect {}", target.as_str()));
    let result = development_problems_with(Host::LinuxX86, Pin::Nightly, &mut runner);
    assert_eq!(result, Err("cannot inspect test".to_owned()));
}

/// Coverage measures and release ships, so both omit development flags from
/// their own route and select their own compiler settings. Each listed target
/// must run a Cargo command so the check cannot pass without measuring a route.
#[test]
fn coverage_and_release_take_neither_flag() -> Result<(), String> {
    let (problems, read) = held_out_problems()?;
    none_of(&problems)?;
    if held_out_target_count() > 0 && read == 0 {
        return Err(
            "the held-out targets run no cargo command, so the check proves nothing".to_owned(),
        );
    }
    Ok(())
}
