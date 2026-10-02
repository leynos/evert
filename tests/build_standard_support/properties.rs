//! Generated contracts for the small readers used by the build-standard tests.

use proptest::{prelude::*, test_runner::TestCaseError};

use super::{
    ci_steps::{coverage_problems, linker_install_problems},
    config::{Flags, Pin, PinError, applies_to_target, config_problems},
    make::{Assignment, assigned_rustflags, commands_from, held_out_problems_with},
};

/// Flags required by the nightly Linux development route.
const DEVELOPMENT_FLAGS: [&str; 3] = [
    "-Zthreads=8",
    "-Clinker=evert-clang-mold",
    "-Clink-arg=-fuse-ld=mold",
];

/// Converts reader diagnostics into proptest's rejected-case error type.
fn property_result<T>(result: Result<T, String>) -> Result<T, TestCaseError> {
    result.map_err(TestCaseError::fail)
}

proptest! {
    /// Checks that the generic Linux source continues to apply across architectures.
    #[test]
    fn cfg_linux_source_covers_generated_linux_targets(
        extra_flags in prop::collection::vec("[a-z][a-z0-9-]{0,10}", 0..8),
        architecture in "[a-z][a-z0-9_]{0,10}",
    ) {
        let flags = DEVELOPMENT_FLAGS
            .iter()
            .map(|flag| (*flag).to_owned())
            .chain(extra_flags.into_iter().map(|flag| format!("-Cmetadata={flag}")))
            .collect::<Vec<_>>();
        let rustflags = flags.join("\", \"");
        let config = format!(
            "[target.'cfg(target_os = \"linux\")']\nrustflags = [\"{rustflags}\"]\n"
        );
        let target = format!("{architecture}-unknown-linux-gnu");

        prop_assert!(
            property_result(applies_to_target(&config, &target))?,
            "generic Linux cfg did not cover target {target}"
        );
        prop_assert!(
            !property_result(applies_to_target(&config, "x86_64-apple-darwin"))?,
            "generic Linux cfg unexpectedly covered a macOS target"
        );
        prop_assert_eq!(
            property_result(config_problems(&config, Pin::Nightly))?,
            Vec::<String>::new(),
            "a valid cfg source with harmless metadata was rejected"
        );
    }

    /// Architecture-specific Linux tables must not stand in for the cfg source.
    #[test]
    fn generated_architecture_tables_are_not_generic_linux_sources(
        architecture in "[a-z][a-z0-9_]{0,10}",
    ) {
        let config = format!(
            "[target.{architecture}-unknown-linux-gnu]\nrustflags = [{}]\n",
            DEVELOPMENT_FLAGS
                .iter()
                .map(|flag| format!("\"{flag}\""))
                .collect::<Vec<_>>()
                .join(", ")
        );
        prop_assert!(
            !property_result(applies_to_target(&config, "aarch64-unknown-linux-gnu"))?,
            "architecture-specific source was mistaken for the generic Linux cfg"
        );
        prop_assert!(
            !property_result(config_problems(&config, Pin::Nightly))?.is_empty(),
            "architecture-specific table escaped the source-scope checks"
        );
    }

    /// Split `-C value` pairs normalize to the same words as compact flags.
    #[test]
    fn compiler_flag_pairs_normalize(
        values in prop::collection::vec("[a-z][a-z0-9-]{0,12}", 0..12),
    ) {
        let split: Vec<String> = values
            .iter()
            .flat_map(|value| ["-C".to_owned(), value.clone()])
            .collect();
        let joined: Vec<String> = values.iter().map(|value| format!("-C{value}")).collect();

        prop_assert_eq!(
            Flags::from_words(split.iter().map(String::as_str)),
            Flags::from_words(joined.iter().map(String::as_str)),
            "split and compact compiler flags must have one normalized form"
        );
    }

    /// Quoted shell assignments preserve caller flags and read every own token.
    #[test]
    fn shell_assignments_preserve_generated_flag_sequences(
        words in prop::collection::vec("-[A-Za-z][A-Za-z0-9_-]{0,12}", 0..12),
    ) {
        let own_flags = words.join(" ");
        let command = format!(
            "RUSTFLAGS=\"${{RUSTFLAGS:+$RUSTFLAGS }}{own_flags}\" cargo check"
        );
        let expected = Assignment::Flags(
            Flags::from_words(words.iter().map(String::as_str)),
            true,
        );

        prop_assert_eq!(
            property_result(assigned_rustflags(&command))?,
            expected,
            "quoted assignment did not preserve the generated flag sequence"
        );
    }

    /// The shell wrapper exposes Make's own flags to the held-out route reader.
    #[test]
    fn shell_wrappers_normalize_recipe_flags_and_reject_development_flags(
        ordinary_flags in prop::collection::vec("-[A-Za-z][A-Za-z0-9_-]{0,12}", 0..8),
        forbidden_index in prop_oneof![Just(None), (0usize..4).prop_map(Some)],
    ) {
        let forbidden_flags = [
            "-Zcodegen-backend=cranelift",
            "-Zthreads=8",
            "-Clinker=evert-clang-mold",
            "-Clink-arg=-fuse-ld=mold",
        ];
        let mut recipe_flags = ordinary_flags;
        if let Some(index) = forbidden_index {
            let flag = forbidden_flags
                .get(index)
                .ok_or_else(|| TestCaseError::fail("generated flag index was out of range"))?;
            recipe_flags.push((*flag).to_owned());
        }
        let make_flags = recipe_flags.join(" ");
        let command = format!(
            "bash -c 'make_flags=$1; shift; effective_flags=\"${{RUSTFLAGS:+$RUSTFLAGS }}$make_flags\"; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"$effective_flags\" \"$@\"' _ '{make_flags}' cargo build\n"
        );
        let parsed = property_result(assigned_rustflags(&command))?;
        prop_assert_eq!(
            parsed,
            Assignment::Flags(Flags::from_words(recipe_flags.iter().map(String::as_str)), true),
            "the wrapper reader must retain its own positional flags"
        );

        let mut runner = |_target: &str, _host| Ok(command.clone());
        let (problems, read) = property_result(held_out_problems_with(&mut runner))?;
        prop_assert_eq!(read, 2, "both held-out routes must be inspected");
        prop_assert_eq!(
            problems.is_empty(),
            forbidden_index.is_none(),
            "caller flags remain inherited; standard flags in make_flags are recipe flags"
        );
    }

    /// Backslash continuations keep a generated assignment attached to Cargo.
    #[test]
    fn continued_commands_remain_one_assignment(
        words in prop::collection::vec("-[A-Za-z][A-Za-z0-9_-]{0,12}", 0..12),
    ) {
        let own_flags = words.join(" ");
        let command = format!(
            "RUSTFLAGS=\"{own_flags}\" \\\ncargo test\necho cargo test\nmake other\n"
        );
        let expected = vec![Assignment::Flags(
            Flags::from_words(words.iter().map(String::as_str)),
            false,
        )];

        prop_assert_eq!(
            property_result(commands_from(&command))?,
            expected,
            "continued Cargo assignment split or included a neighbouring command"
        );
    }

    /// Workflow steps are judged independently, including every generated omission.
    #[test]
    fn setup_workflow_steps_require_linker_installation(
        installations in prop::collection::vec(any::<bool>(), 0..12),
    ) {
        let mut workflow = String::from("jobs:\n  build:\n    steps:\n");
        for installs in &installations {
            workflow.push_str(
                "      - uses: org/shared-actions/.github/actions/setup-rust@abc\n",
            );
            workflow.push_str("        with:\n          install-mold: ");
            workflow.push_str(if *installs { "'true'\n" } else { "'false'\n" });
        }
        let expected = installations.iter().filter(|installs| !**installs).count();

        prop_assert_eq!(
            linker_install_problems("generated.yml", &workflow).len(),
            expected,
            "workflow findings must match the steps that omit the linker"
        );
    }

    /// Coverage steps may use arbitrary ordinary flags but no development flag.
    #[test]
    fn coverage_steps_report_each_development_flag(
        development_flag_steps in prop::collection::vec(
            prop::collection::vec(any::<bool>(), 4),
            0..10,
        ),
    ) {
        let development_flags = [
            "-Zcodegen-backend=cranelift",
            "-Zthreads=8",
            "-Clinker=evert-clang-mold",
            "-Clink-arg=-fuse-ld=mold",
        ];
        let mut workflow = String::from("jobs:\n  coverage:\n    steps:\n");
        let mut expected = 0;
        for selected in &development_flag_steps {
            workflow.push_str(
                "      - uses: org/shared-actions/.github/actions/generate-coverage@abc\n",
            );
            workflow.push_str("        env:\n          RUSTFLAGS: -D warnings");
            let has_development_flag = selected.iter().any(|included| *included);
            if has_development_flag {
                expected += 1;
            }
            for (included, flag) in selected.iter().zip(development_flags) {
                if *included {
                    workflow.push(' ');
                    workflow.push_str(flag);
                }
            }
            workflow.push('\n');
        }

        prop_assert_eq!(
            coverage_problems("generated.yml", &workflow).len(),
            expected,
            "coverage findings must match steps carrying development flags"
        );
    }

    /// Numeric release overrides are accepted as stable toolchain pins.
    #[test]
    fn generated_numbered_toolchain_overrides_are_stable(
        components in prop::collection::vec(0u16..1000, 2..5),
    ) {
        let version = components
            .iter()
            .map(ToString::to_string)
            .collect::<Vec<_>>()
            .join(".");
        let toolchain = format!("[toolchain]\nchannel = \"{version}\"\n");

        prop_assert_eq!(Pin::read(&toolchain), Ok(Pin::Stable));
    }

    /// Dated nightly overrides remain nightly across generated date components.
    #[test]
    fn generated_dated_nightly_overrides_are_nightly(
        year in 2020u16..2030,
        month in 1u8..13,
        day in 1u8..29,
    ) {
        let channel = format!("nightly-{year:04}-{month:02}-{day:02}");
        let toolchain = format!("[toolchain]\nchannel = \"{channel}\"\n");

        prop_assert_eq!(Pin::read(&toolchain), Ok(Pin::Nightly));
    }

    /// Unknown and malformed toolchain overrides fail with distinct errors.
    #[test]
    fn unsupported_and_unquoted_toolchain_overrides_are_rejected(
        suffix in "[a-z][a-z0-9-]{0,12}",
    ) {
        let unknown = format!("canary-{suffix}");
        let unsupported = format!("[toolchain]\nchannel = \"{unknown}\"\n");
        let malformed = format!("[toolchain]\nchannel = {unknown}\n");

        prop_assert_eq!(
            Pin::read(&unsupported),
            Err(PinError::UnsupportedChannel(unknown)),
            "unknown toolchain overrides must not fall through to stable"
        );
        prop_assert_eq!(
            Pin::read(&malformed),
            Err(PinError::MalformedChannel),
            "unquoted toolchain overrides must be rejected as malformed"
        );
    }

    /// Unterminated or mismatched quotes never become valid channel strings.
    #[test]
    fn malformed_toolchain_quoting_is_rejected(
        channel in "[a-z][a-z0-9-]{0,12}",
    ) {
        let unterminated = format!("[toolchain]\nchannel = \"{channel}\n");
        let mismatched = format!("[toolchain]\nchannel = '{channel}\"\n");

        prop_assert_eq!(
            Pin::read(&unterminated),
            Err(PinError::MalformedChannel),
            "an unterminated channel string must be rejected"
        );
        prop_assert_eq!(
            Pin::read(&mismatched),
            Err(PinError::MalformedChannel),
            "a channel with mismatched delimiters must be rejected"
        );
    }

    /// Similar keys are not mistaken for the exact `channel` assignment.
    #[test]
    fn channel_like_keys_do_not_satisfy_toolchain_channel(
        suffix in "[a-z][a-z0-9-]{0,12}",
    ) {
        let toolchain = format!(
            "[toolchain]\nchannel-{suffix} = \"nightly\"\ndefault-channel = \"stable\"\n"
        );

        prop_assert_eq!(
            Pin::read(&toolchain),
            Err(PinError::MissingChannel),
            "only the exact channel key satisfies the toolchain pin"
        );
    }

    /// Missing channels and repeated channels have explicit reader errors.
    #[test]
    fn toolchain_channel_cardinality_is_checked(repetitions in 2usize..8) {
        let assignments = (0..repetitions)
            .map(|_| "channel = \"stable\"\n")
            .collect::<String>();
        let repeated = format!("[toolchain]\n{assignments}");

        prop_assert_eq!(Pin::read("[toolchain]\ncomponents = []\n"), Err(PinError::MissingChannel));
        prop_assert_eq!(
            Pin::read(&repeated),
            Err(PinError::MultipleChannels(repetitions)),
            "repeated channel assignments must not be accepted"
        );
    }
}
