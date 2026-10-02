//! Readers for the Cargo configuration half of the build standard: the
//! toolchain pin, the flag lists, and the `rustflags` sources in
//! `.cargo/config.toml`. Everything is read as text, so the contract needs no
//! parser dependency.

use std::{error::Error, fmt};

pub const CONFIG: &str = include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/.cargo/config.toml"));
pub const TOOLCHAIN: &str =
    include_str!(concat!(env!("CARGO_MANIFEST_DIR"), "/rust-toolchain.toml"));

/// An unsupported backend flag that the standard must not select.
pub const BACKEND_FLAG: &str = "-Zcodegen-backend=cranelift";
/// The parallel-frontend flag carried by the selected target's rustflags source.
pub const THREADS_FLAG: &str = "-Zthreads=8";
/// The Linux linker wrapper that verifies and selects the pinned `mold` binary.
pub const LINKER_DRIVER_FLAG: &str = "-Clinker=evert-clang-mold";
/// The linker flag the Linux source adds, normalized to one token.
pub const LINKER_FLAG: &str = "-Clink-arg=-fuse-ld=mold";
/// The target table that applies to every Rust target whose operating system is Linux.
const LINUX_TARGET_TABLE: &str = "target.'cfg(target_os = \"linux\")'";

/// A list of complaints about the repository.
pub type Problems = Vec<String>;

/// The channel the toolchain file pins.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pin {
    Nightly,
    Stable,
}

/// Why a toolchain file does not identify one supported channel.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum PinError {
    /// The file has no `channel` assignment.
    MissingChannel,
    /// The file has more than one `channel` assignment.
    MultipleChannels(usize),
    /// A `channel` assignment is not a quoted TOML string.
    MalformedChannel,
    /// The channel string is not a supported Rust release or nightly.
    UnsupportedChannel(String),
}

impl fmt::Display for PinError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingChannel => formatter.write_str("rust-toolchain.toml names no channel"),
            Self::MultipleChannels(count) => write!(
                formatter,
                "rust-toolchain.toml names {count} channel assignments"
            ),
            Self::MalformedChannel => {
                formatter.write_str("rust-toolchain.toml channel must be a quoted TOML string")
            }
            Self::UnsupportedChannel(channel) => {
                write!(formatter, "the channel `{channel}` is not supported")
            }
        }
    }
}

impl Error for PinError {}

impl Pin {
    /// Reads the pin from a `rust-toolchain.toml`.
    ///
    /// The channel must be named exactly once and be one the standard knows: a
    /// `nightly`, a `nightly-YYYY-MM-DD`, `stable`, `beta`, or a numbered release.
    /// Missing, repeated and unknown channels are errors, not stable pins.
    ///
    /// ```text
    /// Pin::read("channel = \"nightly-2026-05-28\"") == Ok(Pin::Nightly)
    /// Pin::read("channel = \"1.94.0\"") == Ok(Pin::Stable)
    /// ```
    ///
    /// # Errors
    ///
    /// Returns the reason when the channel is missing, repeated, malformed or unsupported.
    pub fn read(toolchain: &str) -> Result<Self, PinError> {
        let mut channels = Vec::new();
        for line in toolchain.lines().map(str::trim) {
            if let Some(channel) = channel_assignment(line)? {
                channels.push(channel);
            }
        }
        match channels.as_slice() {
            [] => Err(PinError::MissingChannel),
            [channel] => Self::classify(channel),
            _ => Err(PinError::MultipleChannels(channels.len())),
        }
    }

    /// Classifies one channel name.
    fn classify(channel: &str) -> Result<Self, PinError> {
        let is_dated_nightly = dated_nightly(channel);
        let is_nightly = channel == "nightly" || is_dated_nightly;
        if is_nightly {
            Ok(Self::Nightly)
        } else if is_numbered_release(channel) || matches!(channel, "stable" | "beta") {
            Ok(Self::Stable)
        } else {
            Err(PinError::UnsupportedChannel(channel.to_owned()))
        }
    }

    /// Returns whether the pin takes `-Zthreads`, which is a nightly flag.
    pub const fn takes_threads(self) -> bool { matches!(self, Self::Nightly) }
}

/// Reads the exact `channel` key; `channel_assignment("channel = \"nightly\"")`
/// returns `Ok(Some("nightly"))`, while a `default-channel` key returns `Ok(None)`.
///
/// # Errors
///
/// Returns `MalformedChannel` when the exact key is not a quoted string.
fn channel_assignment(line: &str) -> Result<Option<&str>, PinError> {
    let Some((key, assignment_value)) = line.split_once('=') else {
        return Ok(None);
    };
    if key.trim() != "channel" {
        return Ok(None);
    }
    let value = assignment_value.trim();
    let Some(quote) = value
        .chars()
        .next()
        .filter(|quote| matches!(quote, '\'' | '"'))
    else {
        return Err(PinError::MalformedChannel);
    };
    let Some(after_opening_quote) = value.strip_prefix(quote) else {
        return Err(PinError::MalformedChannel);
    };
    let Some((channel, trailing_text)) = after_opening_quote.split_once(quote) else {
        return Err(PinError::MalformedChannel);
    };
    let comment_suffix = trailing_text.trim();
    if !comment_suffix.is_empty() && !comment_suffix.starts_with('#') {
        return Err(PinError::MalformedChannel);
    }
    Ok(Some(channel))
}

/// Matches exact-width ASCII numbers; `is_date_component("2026", 4)` is true,
/// while `is_date_component("26", 4)` is false.
fn is_date_component(part: &str, width: usize) -> bool {
    part.len() == width && part.bytes().all(|byte| byte.is_ascii_digit())
}

/// Recognizes dated nightlies by component width; `dated_nightly("nightly-2026-05-28")`
/// is true, while `dated_nightly("nightly-2026-5-28")` is false.
fn dated_nightly(channel: &str) -> bool {
    channel.strip_prefix("nightly-").is_some_and(|date| {
        let mut parts = date.split('-');
        matches!(
            (parts.next(), parts.next(), parts.next(), parts.next()),
            (Some(year), Some(month), Some(day), None)
                if is_date_component(year, 4)
                    && [month, day]
                        .into_iter()
                        .all(|part| is_date_component(part, 2))
        )
    })
}

/// Recognizes dotted numeric releases; `is_numbered_release("1.94.0")` is
/// true, while `is_numbered_release("1..0")` is false.
fn is_numbered_release(channel: &str) -> bool {
    channel.split('.').count() >= 2
        && channel
            .split('.')
            .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()))
}

/// A list of compiler flags, with `-C value` pairs joined into `-Cvalue` so
/// both spellings compare equal.
#[derive(Debug, PartialEq, Eq)]
pub struct Flags(Vec<String>);

impl Flags {
    /// Reads a flag list from its words.
    ///
    /// ```text
    /// Flags::from_words(["-C", "link-arg=-fuse-ld=mold"]) == Flags::from_words(["-Clink-arg=-fuse-ld=mold"])
    /// ```
    pub fn from_words<'a>(words: impl IntoIterator<Item = &'a str>) -> Self {
        let mut joined: Vec<String> = Vec::new();
        for word in words {
            match joined.last_mut() {
                Some(last) if last == "-C" => *last = format!("-C{word}"),
                _ => joined.push(word.to_owned()),
            }
        }
        Self(joined)
    }

    /// Returns whether the list names one flag.
    fn names(&self, flag: &str) -> bool { self.0.iter().any(|candidate| candidate == flag) }

    /// Returns whether the list names the frontend flag.
    pub fn names_threads(&self) -> bool { self.names(THREADS_FLAG) }

    /// Returns whether the list names the unsupported Cranelift backend.
    pub fn names_backend(&self) -> bool { self.names(BACKEND_FLAG) }

    /// Returns whether the list names the linker flag.
    pub fn names_linker(&self) -> bool { self.names(LINKER_FLAG) }

    /// Returns whether the list names the pinned linker wrapper.
    pub fn names_linker_driver(&self) -> bool { self.names(LINKER_DRIVER_FLAG) }

    /// Checks that Cranelift is absent and supported development flags are
    /// present or absent as the route requires.
    ///
    /// ```text
    /// Flags::from_words([]).meets(false) == Ok(())
    /// Flags::from_words([]).meets(true).is_err()
    /// ```
    ///
    /// # Errors
    ///
    /// Returns the reason when the backend, frontend, or linker settings are wrong.
    pub fn meets(&self, takes_development_flags: bool) -> Result<(), String> {
        if self.names_backend() {
            return Err(format!("selects unsupported {BACKEND_FLAG}: {:?}", self.0));
        }
        if self.names_threads() != takes_development_flags {
            return Err(format!("gets {THREADS_FLAG} wrong: {:?}", self.0));
        }
        if self.names_linker() != takes_development_flags {
            return Err(format!("gets the pinned linker wrong: {:?}", self.0));
        }
        if self.names_linker_driver() != takes_development_flags {
            return Err(format!("gets pinned linker wrapper wrong: {:?}", self.0));
        }
        Ok(())
    }
}

/// One `rustflags` source in a Cargo configuration.
struct Source {
    table: String,
    flags: Flags,
}

impl Source {
    /// Returns whether this is the canonical Cargo cfg table for Linux targets.
    fn is_linux(&self) -> bool { self.table == LINUX_TARGET_TABLE }

    /// Returns whether this source applies to a target triple with Linux as its OS.
    pub fn applies_to_target(&self, target: &str) -> bool {
        self.is_linux() && target.split('-').any(|component| component == "linux")
    }

    /// Returns a flag mismatch: supported development settings belong on the
    /// selected target alone when its toolchain is nightly.
    fn problem(&self, pin: Pin) -> Option<String> {
        let reason = self
            .flags
            .meets(pin.takes_threads() && self.is_linux())
            .err()?;
        Some(format!("[{}] {reason}", self.table))
    }
}

/// One line of a Cargo configuration, as far as the standard reads it.
enum Line {
    Table(String),
    Rustflags(Flags),
    Other,
}

/// Returns the quoted strings in one line, in order.
fn quoted(line: &str) -> Vec<&str> { line.split('"').skip(1).step_by(2).collect() }

/// Returns a line up to a `#` that starts a comment, ignoring a `#` inside a
/// quoted string, and without trailing space.
fn without_comment(line: &str) -> &str {
    let mut quote: Option<char> = None;
    for (index, c) in line.char_indices() {
        match (quote, c) {
            (None, '"' | '\'') => quote = Some(c),
            (Some(open), _) if c == open => quote = None,
            (None, '#') => return line.get(..index).unwrap_or(line).trim_end(),
            _ => {}
        }
    }
    line
}

/// Reads one configuration line. A `rustflags` entry is a one-line array of
/// strings, which is the shape the standard prescribes; an entry spread over
/// several lines is refused rather than half read.
///
/// ```text
/// read_line("[build]")                     -> Line::Table("build")
/// read_line("[build] # hosts")             -> Line::Table("build")
/// read_line("rustflags-extra = [\"x\"]")   -> Line::Other
/// read_line("rustflags = [\"-Zthreads=8\"]") -> Line::Rustflags(..)
/// ```
fn read_line(raw: &str) -> Result<Line, String> {
    let line = without_comment(raw);
    if line.starts_with('[') {
        return Ok(Line::Table(
            line.trim_matches(|c| c == '[' || c == ']')
                .trim()
                .to_owned(),
        ));
    }
    let Some(value) = line
        .strip_prefix("rustflags")
        .filter(|value| value.trim_start().starts_with('='))
    else {
        return Ok(Line::Other);
    };
    if !value.contains(']') {
        return Err("a `rustflags` array spans lines; keep it on one".to_owned());
    }
    Ok(Line::Rustflags(Flags::from_words(quoted(value))))
}

/// Returns every `rustflags` source in a Cargo configuration.
fn sources(config: &str) -> Result<Vec<Source>, String> {
    let mut table = String::new();
    let mut found = Vec::new();
    for line in config
        .lines()
        .map(str::trim)
        .filter(|line| !line.starts_with('#'))
    {
        match read_line(line)? {
            Line::Table(name) => table = name,
            Line::Rustflags(flags) => found.push(Source {
                table: table.clone(),
                flags,
            }),
            Line::Other => {}
        }
    }
    Ok(found)
}

/// Checks whether one config file's target sources include the supplied Linux
/// target triple.
///
/// This is a contract query for the architecture-independent cfg table, not a
/// reimplementation of Cargo's complete target matching rules.
///
/// # Errors
///
/// Returns the reason when the config contains an unreadable `rustflags` array.
pub fn applies_to_target(config: &str, target: &str) -> Result<bool, String> {
    Ok(sources(config)?
        .iter()
        .any(|source| source.applies_to_target(target)))
}

/// Returns complaints about source scope: one Linux cfg source carries the
/// development flags, without an architecture-specific substitute.
fn shape_problems(found: &[Source], pin: Pin) -> Problems {
    let checks = [
        (
            pin.takes_threads() && found.is_empty(),
            "no rustflags source",
        ),
        (
            !found.iter().any(Source::is_linux),
            "no cfg(target_os = \"linux\") table carries rustflags",
        ),
        (
            found.iter().any(|source| !source.is_linux()),
            "another target or [build] table carries rustflags",
        ),
        (found.len() > 1, "more than one rustflags source"),
    ];
    checks
        .into_iter()
        .filter(|(failed, _)| *failed)
        .map(|(_, text)| text.to_owned())
        .collect()
}

/// Returns every complaint about the configuration sources.
///
/// ```text
/// Pin::read(TOOLCHAIN) -> Ok(Pin::Nightly)
/// config_problems(CONFIG, Pin::Nightly) -> Ok(vec![])
/// ```
///
/// # Errors
///
/// Returns the reason when the configuration cannot be read.
pub fn config_problems(config: &str, pin: Pin) -> Result<Problems, String> {
    let found = sources(config)?;
    let mut problems = shape_problems(&found, pin);
    problems.extend(found.iter().filter_map(|source| source.problem(pin)));
    Ok(problems)
}
