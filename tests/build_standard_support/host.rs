//! Supported host combinations shared by Rust build-route contract tests.

/// A host operating-system and architecture combination supported by the
/// repository's build-route contracts.
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub(crate) enum Host {
    /// Linux on `x86_64`, where development flags are enabled.
    LinuxX86,
    /// Linux on aarch64, where development flags are enabled.
    LinuxArm,
    /// macOS on `x86_64`, where the Linux development flags are disabled.
    Darwin,
}

impl Host {
    /// Returns the operating-system and architecture values passed to Make.
    ///
    /// ```text
    /// Host::LinuxArm.make_values() == ("Linux", "aarch64")
    /// Host::Darwin.make_values() == ("Darwin", "x86_64")
    /// ```
    pub(crate) const fn make_values(self) -> (&'static str, &'static str) {
        match self {
            Self::LinuxX86 => ("Linux", "x86_64"),
            Self::LinuxArm => ("Linux", "aarch64"),
            Self::Darwin => ("Darwin", "x86_64"),
        }
    }

    /// Returns whether this host uses the Linux development compiler route.
    ///
    /// ```text
    /// Host::LinuxX86.takes_development_flags() == true
    /// Host::Darwin.takes_development_flags() == false
    /// ```
    pub(crate) const fn takes_development_flags(self) -> bool {
        matches!(self, Self::LinuxX86 | Self::LinuxArm)
    }
}
