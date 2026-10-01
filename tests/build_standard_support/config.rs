//! Readers for the Cargo configuration half of the build standard: the
//! toolchain pin, the flag lists, and the `rustflags` sources in
//! `.cargo/config.toml`. Everything is read as text, so the contract needs no
//! parser dependency.

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

/// A list of complaints about the repository.
pub type Problems = Vec<String>;

/// The channel the toolchain file pins.
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Pin {
    Nightly,
    Stable,
}

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
    /// Returns the reason when the channel is missing, repeated or unsupported.
    pub fn read(toolchain: &str) -> Result<Self, String> {
        let channels: Vec<&str> = toolchain
            .lines()
            .map(str::trim)
            .filter(|line| line.starts_with("channel"))
            .filter_map(|line| line.split('"').nth(1))
            .collect();
        match channels.as_slice() {
            [] => Err("rust-toolchain.toml names no channel".to_owned()),
            [channel] => Self::classify(channel),
            _ => Err(format!(
                "rust-toolchain.toml names more than one channel: {channels:?}"
            )),
        }
    }

    /// Classifies one channel name.
    fn classify(channel: &str) -> Result<Self, String> {
        let is_date_component = |part: &str, width: usize| {
            part.len() == width && part.bytes().all(|byte| byte.is_ascii_digit())
        };
        let is_dated_nightly = channel.strip_prefix("nightly-").is_some_and(|date| {
            let mut parts = date.split('-');
            matches!(
                (parts.next(), parts.next(), parts.next(), parts.next()),
                (Some(year), Some(month), Some(day), None)
                    if is_date_component(year, 4)
                        && [month, day]
                            .into_iter()
                            .all(|part| is_date_component(part, 2))
            )
        });
        let is_nightly = channel == "nightly" || is_dated_nightly;
        let is_release = channel.split('.').count() >= 2
            && channel
                .split('.')
                .all(|part| !part.is_empty() && part.chars().all(|c| c.is_ascii_digit()));
        if is_nightly {
            Ok(Self::Nightly)
        } else if is_release || matches!(channel, "stable" | "beta") {
            Ok(Self::Stable)
        } else {
            Err(format!(
                "the channel `{channel}` is not one the standard knows"
            ))
        }
    }

    /// Returns whether the pin takes `-Zthreads`, which is a nightly flag.
    pub const fn takes_threads(self) -> bool { matches!(self, Self::Nightly) }
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
    /// Returns whether this is the target whose development route was selected.
    fn is_development_target(&self) -> bool { self.table == "target.x86_64-unknown-linux-gnu" }

    /// Returns a flag mismatch: supported development settings belong on the
    /// selected target alone when its toolchain is nightly.
    fn problem(&self, pin: Pin) -> Option<String> {
        let reason = self
            .flags
            .meets(pin.takes_threads() && self.is_development_target())
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

/// Returns complaints about source scope: the supported target alone may
/// inherit nightly development flags from Cargo defaults.
fn shape_problems(found: &[Source], pin: Pin) -> Problems {
    let checks = [
        (
            pin.takes_threads() && found.is_empty(),
            "no rustflags source",
        ),
        (
            pin.takes_threads() && !found.iter().any(Source::is_development_target),
            "no x86_64 GNU/Linux target table carries rustflags",
        ),
        (
            found.iter().any(|source| !source.is_development_target()),
            "another target or [build] carries rustflags",
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
/// config_problems(CONFIG, Pin::read(TOOLCHAIN)) == Ok(vec![])   // a compliant repository
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
