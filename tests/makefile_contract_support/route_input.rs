//! Closed input types for Makefile route variables and Cargo target options.

use super::make_target::MakeTarget;

/// A finite Make route target accepted by the route contract runner.
pub(super) trait MakeTargetName {
    /// Returns the Make target represented by this closed input.
    ///
    /// ```text
    /// MakeTargetName::into_make_target(MakeTarget::Build) == "build"
    /// ```
    fn into_make_target(self) -> &'static str;
}

impl MakeTargetName for MakeTarget {
    fn into_make_target(self) -> &'static str { Self::as_str(self) }
}

/// The Clippy-only Make target used by the target-selection contract.
#[derive(Clone, Copy, Debug)]
pub(super) enum ClippyTarget {
    /// Expands the combined Rustdoc and Clippy route.
    LintClippy,
}

impl MakeTargetName for ClippyTarget {
    fn into_make_target(self) -> &'static str {
        match self {
            Self::LintClippy => "lint-clippy",
        }
    }
}

/// A Make variable that selects or influences a Cargo route.
#[derive(Clone, Copy, Debug)]
pub(super) enum MakeVariable {
    /// Environment target used when the Cargo command has no explicit target.
    CargoBuildTarget,
    /// Flags passed to Cargo commands.
    CargoFlags,
    /// Flags passed to Rustdoc or Cargo tests.
    TestFlags,
    /// Clippy-specific Cargo flags.
    ClippyFlags,
    /// Deliberately hostile flags used to test Whitaker isolation.
    RustFlags,
}

impl MakeVariable {
    /// Returns the Make variable name supplied by a contract test.
    ///
    /// ```text
    /// MakeVariable::TestFlags.as_str() == "TEST_FLAGS"
    /// MakeVariable::RustFlags.as_str() == "RUST_FLAGS"
    /// ```
    pub(super) const fn as_str(self) -> &'static str {
        match self {
            Self::CargoBuildTarget => "CARGO_BUILD_TARGET",
            Self::CargoFlags => "CARGO_FLAGS",
            Self::TestFlags => "TEST_FLAGS",
            Self::ClippyFlags => "CLIPPY_FLAGS",
            Self::RustFlags => "RUST_FLAGS",
        }
    }
}

/// A Cargo target option whose spelling selects a route in Make.
#[derive(Clone, Copy, Debug)]
pub(super) enum CargoTargetOption {
    /// `--target <triple>` for the native host.
    NativeSplit,
    /// `--target=<triple>` for the native host.
    NativeJoined,
    /// `--target <triple>` for a cross host.
    CrossSplit,
    /// `--target=<triple>` for a cross host.
    CrossJoined,
}

impl CargoTargetOption {
    /// Returns the Cargo syntax represented by this target option.
    ///
    /// ```text
    /// CargoTargetOption::CrossSplit.as_str() == "--target aarch64-unknown-linux-gnu"
    /// CargoTargetOption::NativeJoined.as_str() == "--target=x86_64-unknown-linux-gnu"
    /// ```
    pub(super) const fn as_str(self) -> &'static str {
        match self {
            Self::NativeSplit => "--target x86_64-unknown-linux-gnu",
            Self::NativeJoined => "--target=x86_64-unknown-linux-gnu",
            Self::CrossSplit => "--target aarch64-unknown-linux-gnu",
            Self::CrossJoined => "--target=aarch64-unknown-linux-gnu",
        }
    }
}
