//! Readers for the Makefile half of the build standard: the commands
//! `make -n` prints for each development, coverage and release target, judged
//! against a toolchain pin and a host. Process execution lives in
//! `make_execution`; reader fixtures consume supplied output directly.

use super::config::{
    BACKEND_FLAG,
    Flags,
    LINKER_DRIVER_FLAG,
    LINKER_FLAG,
    Pin,
    Problems,
    THREADS_FLAG,
};

/// Makefile targets that build for development. A command in one either assigns
/// `RUSTFLAGS` with the standard flags or assigns none and so takes the
/// configuration's. The list is this repository's own, and a target that stops
/// being defined fails the contract rather than dropping out of it.
const DEVELOPMENT_TARGETS: &[&str] = &["test", "typecheck", "lint", "build"];
/// Makefile targets that measure or ship, so every command assigns `RUSTFLAGS`
/// and none carries a standard flag.
const HELD_OUT_TARGETS: &[&str] = &["coverage", "release"];

/// The host `make` is told it runs on, through `BUILD_HOST_OS`.
#[derive(Clone, Copy)]
pub enum Host {
    LinuxX86,
    LinuxArm,
    Darwin,
}

impl Host {
    /// Returns the value `uname -s` reports for the host.
    const fn make_value(self) -> &'static str {
        match self {
            Self::LinuxX86 | Self::LinuxArm => "Linux",
            Self::Darwin => "Darwin",
        }
    }

    /// Returns the host architecture Make uses to scope its development flags.
    const fn arch_value(self) -> &'static str {
        match self {
            Self::LinuxX86 | Self::Darwin => "x86_64",
            Self::LinuxArm => "aarch64",
        }
    }

    /// Returns whether the host takes the selected development route.
    const fn takes_development_flags(self) -> bool {
        matches!(self, Self::LinuxX86 | Self::LinuxArm)
    }
}

/// What one `make -n` command assigns to `RUSTFLAGS`.
#[derive(Debug, PartialEq, Eq)]
pub enum Assignment {
    Unassigned,
    /// An assignment, and whether it keeps the caller's own `RUSTFLAGS`.
    Flags(Flags, bool),
}

/// Reads the `RUSTFLAGS` a `make -n` output line assigns. An unreadable form is
/// an error, because it still replaces the configuration's sources and so must
/// not pass.
///
/// ```text
/// assigned_rustflags("RUSTFLAGS=\"-Zthreads=8\" cargo test") -> Flags(["-Zthreads=8"], inherits: false)
/// assigned_rustflags("RUSTFLAGS=\"${RUSTFLAGS:+$RUSTFLAGS }-Zthreads=8\" cargo test") -> inherits: true
/// assigned_rustflags("cargo test")                           -> Unassigned
/// assigned_rustflags("RUSTFLAGS=-Zthreads=8 cargo test")     -> Err
/// ```
///
/// # Errors
///
/// Returns the reason when an assignment is unreadable or glues inherited
/// flags to the following flag.
pub fn assigned_rustflags(line: &str) -> Result<Assignment, String> {
    if let Some(assignment) = shell_wrapper_assignment(line)? {
        return Ok(assignment);
    }
    quoted_rustflags_assignment(line)
}

/// Reads the Make shell wrapper's assignment when the wrapper markers occur.
///
/// ```text
/// shell_wrapper_assignment("effective_flags=\"${RUSTFLAGS:+$RUSTFLAGS }$make_flags\"") -> Err(..)
/// shell_wrapper_assignment("cargo test") -> Ok(None)
/// ```
///
/// # Errors
///
/// Returns the reason when a marked shell wrapper does not preserve the expected
/// inherited-flags transport or does not expose its argument.
fn shell_wrapper_assignment(line: &str) -> Result<Option<Assignment>, String> {
    if !line.contains("make_flags=$1") && !line.contains("effective_flags=") {
        return Ok(None);
    }
    let expected_flags = "effective_flags=\"${RUSTFLAGS:+$RUSTFLAGS }$make_flags\"";
    let expected_assignment =
        "exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=\"$effective_flags\" \"$@\"";
    if !line.contains(expected_flags) || !line.contains(expected_assignment) {
        return Err(format!("unreadable shell RUSTFLAGS wrapper in `{line}`"));
    }
    let Some((_, arguments)) = line.split_once("' _ '") else {
        return Err(format!(
            "shell RUSTFLAGS wrapper has no make_flags argument in `{line}`"
        ));
    };
    let Some((make_flags, _)) = arguments.split_once('\'') else {
        return Err(format!(
            "shell RUSTFLAGS wrapper has an unreadable make_flags argument in `{line}`"
        ));
    };
    Ok(Some(Assignment::Flags(
        Flags::from_words(make_flags.split_whitespace()),
        true,
    )))
}

/// Reads a conventional quoted `RUSTFLAGS` assignment or reports its defect.
///
/// ```text
/// quoted_rustflags_assignment("RUSTFLAGS=\"-Zthreads=8\" cargo test") -> Flags(..)
/// quoted_rustflags_assignment("cargo test") -> Unassigned
/// ```
///
/// # Errors
///
/// Returns the reason when an assignment is unreadable or glues inherited
/// flags to the following flag.
fn quoted_rustflags_assignment(line: &str) -> Result<Assignment, String> {
    let Some((_, rest)) = line.split_once("RUSTFLAGS=\"") else {
        if line.contains("RUSTFLAGS=") {
            return Err(format!("unreadable RUSTFLAGS assignment in `{line}`"));
        }
        return Ok(Assignment::Unassigned);
    };
    let (assigned, _) = rest
        .split_once('"')
        .ok_or_else(|| format!("unterminated RUSTFLAGS in `{line}`"))?;
    let glued = assigned
        .split("${RUSTFLAGS-}")
        .skip(1)
        .any(|after| !after.is_empty() && !after.starts_with(' '));
    if glued {
        return Err(format!(
            "inherited RUSTFLAGS glued to the next flag in `{line}`"
        ));
    }
    // The recipes prepend the caller's own flags with these expansions; they are
    // not standard flags, and glued to the next word they would hide it.
    let inherits = assigned.contains("${RUSTFLAGS:+$RUSTFLAGS }")
        || assigned.contains("${RUSTFLAGS-}")
        || line.contains("effective_flags=\"${RUSTFLAGS:+$RUSTFLAGS }")
        || line.contains("effective_flags=\"${RUSTFLAGS-}");
    let own = assigned
        .replace("${RUSTFLAGS:+$RUSTFLAGS }", " ")
        .replace("${RUSTFLAGS-}", " ");
    Ok(Assignment::Flags(
        Flags::from_words(own.split_whitespace()),
        inherits,
    ))
}

/// Reads the assignment of each Cargo command `make -n` printed. Whitaker
/// deliberately uses another compiler route, so it is excluded here.
///
/// # Errors
///
/// Returns the reason when a command assigns `RUSTFLAGS` in an unreadable form.
pub fn commands_from(stdout: &str) -> Result<Vec<Assignment>, String> {
    // A recipe continued with a trailing backslash is one command.
    let joined = stdout.replace("\\\n", " ");
    joined
        .lines()
        .filter(|line| !line.trim_start().starts_with("echo"))
        .filter(|line| line.contains("cargo"))
        .map(assigned_rustflags)
        .collect()
}

/// Runs the separate Make process boundary for one host and target.
fn run_make_dry_run(target: &str, host: Host) -> Result<String, String> {
    super::make_execution::run_make_dry_run(target, host.make_value(), host.arch_value())
}

/// Obtains output through the injected runner, then parses it at this boundary.
fn commands_with(
    target: &str,
    host: Host,
    runner: &mut impl FnMut(&str, Host) -> Result<String, String>,
) -> Result<Vec<Assignment>, String> {
    commands_from(&runner(target, host)?)
}

/// Returns the complaint about one development command, if any: an assigned
/// `RUSTFLAGS` keeps the caller's own flags and restates the frontend and
/// linker flags on a nightly pin and the selected Linux target.
fn development_problem(
    target: &str,
    host: Host,
    pin: Pin,
    assignment: &Assignment,
) -> Option<String> {
    let Assignment::Flags(flags, inherits) = assignment else {
        return None;
    };
    if !inherits {
        return Some(format!(
            "`make {target}` on {} drops the caller's RUSTFLAGS",
            host.make_value()
        ));
    }
    let reason = flags
        .meets(pin.takes_threads() && host.takes_development_flags())
        .err()?;
    Some(format!("`make {target}` on {} {reason}", host.make_value()))
}

/// Returns every complaint about the development targets on one host, and how
/// many assignments it read, so a test can refuse to pass over nothing.
///
/// # Errors
///
/// Returns the reason when a listed target is not defined or unreadable.
pub fn development_problems(host: Host, pin: Pin) -> Result<(Problems, usize), String> {
    development_problems_with(host, pin, &mut run_make_dry_run)
}

/// Checks development routes using an injected `make -n` output runner.
///
/// Keeping process execution behind this narrow seam lets the parser and route
/// checks run on structured fixtures without launching Make.
pub fn development_problems_with(
    host: Host,
    pin: Pin,
    runner: &mut impl FnMut(&str, Host) -> Result<String, String>,
) -> Result<(Problems, usize), String> {
    let mut problems = Vec::new();
    let mut read = 0;
    for target in DEVELOPMENT_TARGETS {
        let commands = commands_with(target, host, runner)?;
        read += commands
            .iter()
            .filter(|command| **command != Assignment::Unassigned)
            .count();
        problems.extend(
            commands
                .iter()
                .filter_map(|command| development_problem(target, host, pin, command)),
        );
    }
    Ok((problems, read))
}

/// Returns every complaint about one held-out command: it assigns nothing, so
/// it takes the configuration's flags, or the assignment names a development
/// flag.
fn held_out_command_problems(target: &str, assignment: &Assignment) -> Problems {
    let Assignment::Flags(flags, inherits) = assignment else {
        return vec![format!(
            "`make {target}` runs a command that takes the configuration's flags"
        )];
    };
    if !inherits {
        return vec![format!("`make {target}` drops the caller's RUSTFLAGS")];
    }
    let named = [
        (flags.names_backend(), BACKEND_FLAG),
        (flags.names_threads(), THREADS_FLAG),
        (flags.names_linker_driver(), LINKER_DRIVER_FLAG),
        (flags.names_linker(), LINKER_FLAG),
    ];
    named
        .into_iter()
        .filter(|(is_named, _)| *is_named)
        .map(|(_, flag)| format!("`make {target}` takes {flag}"))
        .collect()
}

/// Returns every complaint about the held-out targets, and how many commands it
/// read: each assigns `RUSTFLAGS`, since only an assignment displaces the
/// configuration's sources.
///
/// # Errors
///
/// Returns the reason when a listed target is not defined or unreadable.
pub fn held_out_problems() -> Result<(Problems, usize), String> {
    held_out_problems_with(&mut run_make_dry_run)
}

/// Checks coverage and release routes with an injected `make -n` output runner.
pub fn held_out_problems_with(
    runner: &mut impl FnMut(&str, Host) -> Result<String, String>,
) -> Result<(Problems, usize), String> {
    let mut problems = Vec::new();
    let mut read = 0;
    for target in HELD_OUT_TARGETS {
        let commands = commands_with(target, Host::LinuxX86, runner)?;
        read += commands.len();
        problems.extend(
            commands
                .iter()
                .flat_map(|command| held_out_command_problems(target, command)),
        );
    }
    Ok((problems, read))
}

/// Returns the number of held-out targets the repository defines.
pub const fn held_out_target_count() -> usize { HELD_OUT_TARGETS.len() }
