//! Coverage workflow fixtures for the build-standard exclusion contract.

use rstest::rstest;

use super::ci_steps::coverage_problems;

/// A coverage step that assigns `RUSTFLAGS` without a standard flag.
const COVERAGE_OK: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "        env:\n          RUSTFLAGS: -D warnings\n"
);
/// A coverage step with no assignment.
const COVERAGE_UNASSIGNED: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n"
);
/// A coverage step that takes the frontend flag.
const COVERAGE_WITH_THREADS: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "        env:\n          RUSTFLAGS: -D warnings -Zthreads=8\n"
);
/// A coverage step that takes the Cranelift backend.
const COVERAGE_WITH_BACKEND: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "        env:\n          RUSTFLAGS: -Zcodegen-backend=cranelift\n"
);
/// A coverage step that takes the pinned linker wrapper.
const COVERAGE_WITH_DRIVER: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "        env:\n          RUSTFLAGS: -Clinker=evert-clang-mold\n"
);
/// A coverage step that takes `mold`.
const COVERAGE_WITH_LINKER: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "        env:\n          RUSTFLAGS: -Clink-arg=-fuse-ld=mold\n"
);
/// A coverage step whose assignment belongs to the next step.
const COVERAGE_BORROWING_A_SIBLING: &str = concat!(
    "    steps:\n      - name: Cover\n",
    "        uses: ",
    "org/shared-actions/.github/actions/generate-coverage@",
    "0123456789abcdef0123456789abcdef01234567\n",
    "      - name: Other\n        env:\n          RUSTFLAGS: -D warnings\n"
);

/// Scenario: coverage steps with and without an explicit assignment.
///
/// Invariant: the step assigns `RUSTFLAGS` itself without development flags;
/// a sibling step's assignment does not count.
#[rstest]
#[case::assigned(COVERAGE_OK, 0)]
#[case::unassigned(COVERAGE_UNASSIGNED, 1)]
#[case::with_the_frontend_flag(COVERAGE_WITH_THREADS, 1)]
#[case::with_the_backend(COVERAGE_WITH_BACKEND, 1)]
#[case::with_the_driver(COVERAGE_WITH_DRIVER, 1)]
#[case::with_the_linker(COVERAGE_WITH_LINKER, 1)]
#[case::assignment_on_a_sibling_step(COVERAGE_BORROWING_A_SIBLING, 1)]
fn the_coverage_reader_wants_an_explicit_assignment(
    #[case] workflow: &str,
    #[case] expected: usize,
) -> Result<(), String> {
    let found = coverage_problems("fixture.yml", workflow).len();
    if found == expected {
        Ok(())
    } else {
        Err(format!("{workflow:?}: {found} problems, not {expected}"))
    }
}
