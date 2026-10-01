//! Contract tests for the Rust build standard.
//!
//! The standard keeps rustc's LLVM backend and makes the parallel rustc
//! frontend and pinned `mold` wrapper the defaults for `x86_64` GNU/Linux
//! development builds. Cargo reads the latter settings from .cargo/config.toml,
//! but an assigned RUSTFLAGS replaces that target source. Make therefore
//! restates them for the same host, while other hosts and coverage or release
//! routes keep their own toolchains.
//!
//!
//! The Makefile clauses run `make -n` and read the commands it would run,
//! rather than the Makefile's text, so a flag lost through a variable or a
//! recipe edit fails here. They check `x86_64` GNU/Linux, Linux/aarch64, and
//! `macOS/x86_64` because the default is scoped to one exact target triple. The
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
use ci_steps::{linker_install_problems, workflow_problems};
use config::{
    BACKEND_FLAG,
    CONFIG,
    Flags,
    Pin,
    Problems,
    THREADS_FLAG,
    TOOLCHAIN,
    config_problems,
};
use make::{
    Assignment,
    Host,
    assigned_rustflags,
    commands_from,
    development_problems,
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
/// A toolchain file that names two channels.
const TWO_CHANNELS: &str = "[toolchain]\nchannel = \"stable\"\nchannel = \"nightly\"\n";
/// A toolchain file naming a channel the standard does not know.
const UNKNOWN_CHANNEL: &str = "[toolchain]\nchannel = \"weekly\"\n";
/// A toolchain file with an unrecognized nightly suffix.
const NIGHTLY_FOO: &str = "[toolchain]\nchannel = \"nightly-foo\"\n";
/// A toolchain file whose nightly date has a short month field.
const MALFORMED_NIGHTLY_DATE: &str = "[toolchain]\nchannel = \"nightly-2026-5-28\"\n";

/// A compliant nightly configuration: supported development flags on the exact
/// `x86_64` GNU/Linux target and nowhere else.
const NIGHTLY_OK: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The same target, with the linker flag spelled as the `-C` pair Cargo accepts.
const NIGHTLY_SPELLED_APART: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-C\", \
     \"link-arg=-fuse-ld=mold\"]\n"
);
/// A compliant stable configuration with no development flags.
const STABLE_OK: &str = concat!("[target.x86_64-unknown-linux-gnu]\n", "rustflags = []\n");
/// The exact target selects the unsupported Cranelift backend.
const TARGET_SELECTS_CRANELIFT: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zcodegen-backend=cranelift\", \"-Zthreads=8\", ",
    "\"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The exact target lost the parallel frontend flag.
const TARGET_LOSES_THREADS: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// The exact target lost the `mold` linker argument.
const TARGET_LOSES_LINKER: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\"]\n"
);
/// The exact target lost the pinned linker wrapper.
const TARGET_LOSES_DRIVER: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// Development flags in `[build]` would leak to every target.
const BUILD_LEAKS_DEVELOPMENT_FLAGS: &str = concat!(
    "[build]\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// A broad Linux condition would also select Linux architectures without proof.
const BROAD_LINUX_LEAKS_DEVELOPMENT_FLAGS: &str = concat!(
    "[target.'cfg(target_os = \"linux\")']\n",
    "rustflags = [\"-Zthreads=8\", \"-Clinker=evert-clang-mold\", \"-Clink-arg=-fuse-ld=mold\"]\n"
);
/// A stable configuration that names the nightly-only frontend flag.
const STABLE_WITH_THREADS: &str = concat!(
    "[target.x86_64-unknown-linux-gnu]\n",
    "rustflags = [\"-Zthreads=8\"]\n"
);
/// A `rustflags` array spread over several lines, which the reader refuses.
const SPREAD_ARRAY: &str =
    "[target.x86_64-unknown-linux-gnu]\nrustflags = [\n  \"-Zthreads=8\",\n]\n";

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
/// Invariant: only the exact target triple carries supported development flags;
/// each missing flag and broad-source leak is reported, and stable refuses
/// nightly-only flags.
#[rstest]
#[case::compliant_nightly(NIGHTLY_OK, Pin::Nightly, 0)]
#[case::linker_spelled_as_a_pair(NIGHTLY_SPELLED_APART, Pin::Nightly, 0)]
#[case::compliant_stable(STABLE_OK, Pin::Stable, 0)]
#[case::target_selects_unsupported_cranelift(TARGET_SELECTS_CRANELIFT, Pin::Nightly, 1)]
#[case::target_loses_the_frontend(TARGET_LOSES_THREADS, Pin::Nightly, 1)]
#[case::target_loses_the_linker(TARGET_LOSES_LINKER, Pin::Nightly, 1)]
#[case::target_loses_the_pinned_driver(TARGET_LOSES_DRIVER, Pin::Nightly, 1)]
#[case::build_table_leaks_to_all_targets(BUILD_LEAKS_DEVELOPMENT_FLAGS, Pin::Nightly, 3)]
#[case::broad_linux_table_leaks_to_other_architectures(
    BROAD_LINUX_LEAKS_DEVELOPMENT_FLAGS,
    Pin::Nightly,
    3
)]
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
#[case::nightly(NIGHTLY, Some(Pin::Nightly))]
#[case::undated_nightly(UNDATED_NIGHTLY, Some(Pin::Nightly))]
#[case::stable(STABLE, Some(Pin::Stable))]
#[case::stable_channel(STABLE_CHANNEL, Some(Pin::Stable))]
#[case::beta(BETA, Some(Pin::Stable))]
#[case::missing(NO_CHANNEL, None)]
#[case::repeated(TWO_CHANNELS, None)]
#[case::unknown(UNKNOWN_CHANNEL, None)]
#[case::unrecognized_nightly_suffix(NIGHTLY_FOO, None)]
#[case::malformed_nightly_date(MALFORMED_NIGHTLY_DATE, None)]
fn the_pin_reader_tells_the_channels_apart(#[case] toolchain: &str, #[case] expected: Option<Pin>) {
    assert_eq!(Pin::read(toolchain).ok(), expected);
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
    none_of(&config_problems(CONFIG, Pin::read(TOOLCHAIN)?)?)
}

#[test]
fn development_targets_restate_the_flags_on_x86_64_gnu_linux() -> Result<(), String> {
    let (problems, read) = development_problems(Host::LinuxX86, Pin::read(TOOLCHAIN)?)?;
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
fn development_targets_do_not_leak_flags_to_other_hosts(#[case] host: Host) -> Result<(), String> {
    none_of(&development_problems(host, Pin::read(TOOLCHAIN)?)?.0)
}

/// Coverage measures and release ships, so both clear the development flags
/// and select their own compiler route. Each listed target must run at least
/// one Cargo command so the check cannot pass without measuring a route.
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
