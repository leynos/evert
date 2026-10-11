//! Supported Make targets shared by build-route contract tests.

/// A Make target exercised by the build-standard and route contracts.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum MakeTarget {
    /// Standard compiler build route.
    Build,
    /// Rust test route.
    Test,
    /// Lint route.
    Lint,
    /// Type-check route.
    Typecheck,
    /// Coverage route.
    Coverage,
    /// Stable release route.
    Release,
}

impl MakeTarget {
    /// Returns the target name passed to Make.
    ///
    /// ```text
    /// MakeTarget::Typecheck.as_str() == "typecheck"
    /// ```
    pub(crate) const fn as_str(self) -> &'static str {
        match self {
            Self::Build => "build",
            Self::Test => "test",
            Self::Lint => "lint",
            Self::Typecheck => "typecheck",
            Self::Coverage => "coverage",
            Self::Release => "release",
        }
    }
}
