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

#[path = "build_standard_support/ci_steps.rs"]
mod ci_steps;
#[path = "build_standard_support/config.rs"]
mod config;
#[path = "build_standard_support/coverage_contract.rs"]
mod coverage_contract;
#[path = "build_standard_support/make.rs"]
mod make;
#[path = "build_standard_support/properties.rs"]
mod properties;
use ci_steps::{linker_install_problems, workflow_problems};
use config::{
    BACKEND_FLAG,
    CONFIG,
    Flags,
    Pin,
    PinError,
    Problems,
    THREADS_FLAG,
    TOOLCHAIN,
    applies_to_target,
    config_problems,
};
use make::{
    Assignment,
    Host,
    assigned_rustflags,
    commands_from,
    development_problems,
    development_problems_with,
    held_out_problems,
    held_out_problems_with,
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

/// Checks that a fixture configuration draws the expected number of complaints.
fn draws(config: &str, pin: Pin, expected: usize) -> Result<(), String> {
    let found = config_problems(config, pin)?.len();
    if found == expected {
        Ok(())
    } else {
        Err(format!("{config:?}: {found} problems, not {expected}"))
    }
}

/// Scenario: configurations of each shape, read on a nightly and a stable pin.
///
/// Invariant: one Linux cfg table carries development flags for every Linux
/// architecture; x86_64-only configuration and missing flags are reported.
#[rstest]
#[case::compliant_nightly(NIGHTLY_OK, Pin::Nightly, 0)]
#[case::linker_spelled_as_a_pair(NIGHTLY_SPELLED_APART, Pin::Nightly, 0)]
#[case::compliant_stable(STABLE_OK, Pin::Stable, 0)]
#[case::target_selects_unsupported_cranelift(TARGET_SELECTS_CRANELIFT, Pin::Nightly, 1)]
#[case::target_loses_the_frontend(TARGET_LOSES_THREADS, Pin::Nightly, 1)]
#[case::target_loses_the_linker(TARGET_LOSES_LINKER, Pin::Nightly, 1)]
#[case::target_loses_the_pinned_driver(TARGET_LOSES_DRIVER, Pin::Nightly, 1)]
#[case::build_table_leaks_to_all_targets(BUILD_LEAKS_DEVELOPMENT_FLAGS, Pin::Nightly, 3)]
#[case::x86_64_only_linux_table_misses_other_architectures(X86_ONLY_LINUX, Pin::Nightly, 3)]
#[case::cfg_linux_applies_to_every_linux_architecture(NIGHTLY_OK, Pin::Nightly, 0)]
#[case::stable_names_the_frontend(STABLE_WITH_THREADS, Pin::Stable, 1)]
#[case::empty_configuration("", Pin::Nightly, 2)]
fn the_configuration_reader_reports_each_defect(
    #[case] config: &str,
    #[case] pin: Pin,
    #[case] expected: usize,
) -> Result<(), String> {
    draws(config, pin, expected)
}

/// Scenario: a `rustflags` array spread over several lines.
///
/// Invariant: the reader refuses it, because reading half of an entry would let
/// a lost flag pass.
#[test]
fn a_rustflags_array_spread_over_lines_is_refused() -> Result<(), String> {
    match config_problems(SPREAD_ARRAY, Pin::Nightly) {
        Ok(_) => Err("a rustflags array spread over lines was read".to_owned()),
        Err(_) => Ok(()),
    }
}

/// Scenario: toolchain files pinning recognized and malformed channels.
///
/// Invariant: bare and dated nightly channels read as nightly; stable, beta,
/// and numbered channels read as stable. Missing, repeated, unknown, and
/// malformed nightly channels are errors rather than silently being treated
/// as stable.
#[rstest]
#[case::nightly(NIGHTLY, Ok(Pin::Nightly))]
#[case::undated_nightly(UNDATED_NIGHTLY, Ok(Pin::Nightly))]
#[case::stable(STABLE, Ok(Pin::Stable))]
#[case::stable_channel(STABLE_CHANNEL, Ok(Pin::Stable))]
#[case::beta(BETA, Ok(Pin::Stable))]
#[case::missing(NO_CHANNEL, Err(PinError::MissingChannel))]
#[case::repeated(TWO_CHANNELS, Err(PinError::MultipleChannels(2)))]
#[case::unknown(UNKNOWN_CHANNEL, Err(PinError::UnsupportedChannel("weekly".to_owned())))]
#[case::unrecognized_nightly_suffix(
    NIGHTLY_FOO,
    Err(PinError::UnsupportedChannel("nightly-foo".to_owned()))
)]
#[case::malformed_nightly_date(
    MALFORMED_NIGHTLY_DATE,
    Err(PinError::UnsupportedChannel("nightly-2026-5-28".to_owned()))
)]
#[case::malformed_channel_assignment(MALFORMED_CHANNEL, Err(PinError::MalformedChannel))]
fn the_pin_reader_tells_the_channels_apart(
    #[case] toolchain: &str,
    #[case] expected: Result<Pin, PinError>,
) {
    assert_eq!(Pin::read(toolchain), expected);
}

/// Builds the assignment a fixture line is expected to read as.
fn flags(words: &[&str], inherits: bool) -> Assignment {
    Assignment::Flags(Flags::from_words(words.iter().copied()), inherits)
}

/// Scenario: `make -n` output lines in each spelling of an assignment.
///
/// Invariant: a quoted assignment is read, with the caller's inherited flags set
/// aside, and a line assigning none reads as unassigned.
#[rstest]
#[case::plain(
    "RUSTFLAGS=\"-D warnings -Zcodegen-backend=cranelift -Zthreads=8\" cargo test",
    flags(&["-D", "warnings", BACKEND_FLAG, THREADS_FLAG], false)
)]
#[case::inherited_flags_glued_on(
    "RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }-Zcodegen-backend=cranelift -Zthreads=8\" cargo check",
    flags(&[BACKEND_FLAG, THREADS_FLAG], true)
)]
#[case::shell_wrapper_inherits_caller_flags(
    r#"bash -c 'effective_flags="${RUSTFLAGS:+$RUSTFLAGS }$make_flags"; exec env RUSTFLAGS="$effective_flags" cargo test' _ '-D warnings'"#,
    flags(&[], true)
)]
#[case::inherited_flags_only("RUSTFLAGS=\"${RUSTFLAGS-}\" cargo build --release", flags(&[], true))]
#[case::no_assignment("cargo clippy --all-targets", Assignment::Unassigned)]
fn the_command_reader_reads_each_assignment(
    #[case] line: &str,
    #[case] expected: Assignment,
) -> Result<(), String> {
    if assigned_rustflags(line)? == expected {
        Ok(())
    } else {
        Err(format!("`{line}` was read wrongly"))
    }
}

/// Scenario: `make -n` output lines whose assignment the reader cannot parse.
///
/// Invariant: each is refused rather than passed, because an assignment in a
/// form the reader does not understand still replaces the configuration.
#[rstest]
#[case::unquoted("RUSTFLAGS=-Zthreads=8 cargo test")]
#[case::unterminated("RUSTFLAGS=\"-Zthreads=8 cargo test")]
fn the_command_reader_refuses_what_it_cannot_parse(#[case] line: &str) -> Result<(), String> {
    match assigned_rustflags(line) {
        Ok(_) => Err(format!("`{line}` was read, not refused")),
        Err(_) => Ok(()),
    }
}

/// A workflow step that passes the input, quoted.
const STEP_INSTALLS: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: 'true'\n"
);
/// The same, with the bare value.
const STEP_INSTALLS_BARE: &str = concat!(
    "    steps:\n      - uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: true\n"
);
/// A step with no input at all.
const STEP_MISSING_INPUT: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n"
);
/// A step that turns the input off.
const STEP_INPUT_OFF: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "        with:\n          install-mold: 'false'\n"
);
/// A step without the input, followed by a step that has one for another action.
const STEP_BEFORE_A_SIBLING_THAT_INSTALLS: &str = concat!(
    "    steps:\n      - name: Setup Rust\n",
    "        uses: \
     org/shared-actions/.github/actions/setup-rust@0123456789abcdef0123456789abcdef01234567\n",
    "      - name: Other\n        uses: org/other@abc\n        with:\n          install-mold: \
     'true'\n"
);
/// A comment that names the action, and no step.
const COMMENT_NAMING_THE_ACTION: &str =
    "    steps:\n      # setup-rust@abc installs it\n      - run: make\n";

/// Scenario: workflow steps that set up Rust with and without the input.
///
/// Invariant: a step must pass `install-mold: 'true'` itself; another step's
/// input does not count, and a comment naming the action is not a step.
#[rstest]
#[case::quoted_true(STEP_INSTALLS, 0)]
#[case::bare_true(STEP_INSTALLS_BARE, 0)]
#[case::missing_input(STEP_MISSING_INPUT, 1)]
#[case::input_off(STEP_INPUT_OFF, 1)]
#[case::input_on_a_sibling_step(STEP_BEFORE_A_SIBLING_THAT_INSTALLS, 1)]
#[case::comment_only(COMMENT_NAMING_THE_ACTION, 0)]
fn the_workflow_reader_wants_the_input_on_each_step(
    #[case] workflow: &str,
    #[case] expected: usize,
) -> Result<(), String> {
    let found = linker_install_problems("fixture.yml", workflow).len();
    if found == expected {
        Ok(())
    } else {
        Err(format!("{workflow:?}: {found} problems, not {expected}"))
    }
}

/// Every workflow that builds under the standard installs `mold`. A repository
/// whose workflows do not set up Rust through `setup-rust` lists none, and the
/// check then reads nothing; a listed workflow must have a step to read.
#[test]
fn every_setup_rust_step_installs_linker() -> Result<(), String> { none_of(&workflow_problems()) }

/// Scenario: a recipe continued over lines, beside an `echo` and another command.
///
/// Invariant: the continued command is one command, and lines that are not a
/// Cargo or Whitaker command are ignored.
#[test]
fn a_continued_command_is_one_command() -> Result<(), String> {
    let joined = commands_from(concat!(
        "RUSTFLAGS=\"-A\" \\\n",
        "cargo test\necho cargo test\nmake other\n"
    ))?;
    if joined == vec![flags(&["-A"], false)] {
        Ok(())
    } else {
        Err(format!("read wrongly: {joined:?}"))
    }
}

#[test]
fn every_rustflags_source_is_consistent_with_the_pin() -> Result<(), String> {
    none_of(&config_problems(
        CONFIG,
        Pin::read(TOOLCHAIN).map_err(|error| error.to_string())?,
    )?)
}

#[test]
fn the_cfg_source_applies_to_non_x86_linux_targets() -> Result<(), String> {
    if !applies_to_target(CONFIG, "x86_64-unknown-linux-gnu")? {
        return Err("the Linux cfg source does not apply to x86_64 Linux".to_owned());
    }
    if !applies_to_target(CONFIG, "aarch64-unknown-linux-gnu")? {
        return Err("the Linux cfg source does not apply to aarch64 Linux".to_owned());
    }
    if applies_to_target(X86_ONLY_LINUX, "aarch64-unknown-linux-gnu")? {
        return Err("an x86_64-only target table unexpectedly applies to aarch64".to_owned());
    }
    if applies_to_target(CONFIG, "x86_64-apple-darwin")? {
        return Err("the Linux cfg source unexpectedly applies to macOS".to_owned());
    }
    if config_problems(X86_ONLY_LINUX, Pin::Nightly)?.is_empty() {
        return Err("an x86_64-only Linux table must be reported as a defect".to_owned());
    }
    Ok(())
}

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
    let mut runner = |target: &str, host: Host| {
        calls.push((target.to_owned(), host));
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
    let mut runner = |target: &str, _host: Host| Err(format!("cannot inspect {target}"));
    let result = development_problems_with(Host::LinuxX86, Pin::Nightly, &mut runner);
    assert_eq!(result, Err("cannot inspect test".to_owned()));
}

#[test]
fn held_out_routes_require_inherited_caller_flags() -> Result<(), String> {
    let mut runner = |target: &str, _host: Host| {
        let inherited = if target == "coverage" {
            "${RUSTFLAGS:+$RUSTFLAGS }"
        } else {
            ""
        };
        Ok(format!(
            "RUSTFLAGS=\"{inherited}-D warnings\" cargo build\n"
        ))
    };
    let (problems, read) = held_out_problems_with(&mut runner)?;
    if read != 2 {
        return Err(format!("read {read} held-out commands, expected 2"));
    }
    if !matches!(problems.as_slice(), [problem] if problem.contains("release")) {
        return Err(format!("unexpected held-out route findings: {problems:#?}"));
    }
    Ok(())
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
