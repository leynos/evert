//! Reader for the CI half of the build standard: every workflow that builds
//! under the standard installs `mold` through `setup-rust`'s `install-mold`
//! input, so the Linux jobs have the linker the configuration names.
//!
//! The workflows are read as text, one step at a time. Release workflows are
//! not listed: a release stays on the platform linker and never uses `mold`.

use super::config::Problems;

/// The workflows that set up Rust and build under the standard, as name and
/// text. The list is this repository's own, so a workflow that stops setting up
/// Rust fails the contract rather than dropping out of it.
pub const WORKFLOWS: &[(&str, &str)] = &[
    (
        "act-validation.yml",
        include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/.github/workflows/act-validation.yml"
        )),
    ),
    (
        "audit.yml",
        include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/.github/workflows/audit.yml"
        )),
    ),
    (
        "ci.yml",
        include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/.github/workflows/ci.yml"
        )),
    ),
    (
        "coverage-main.yml",
        include_str!(concat!(
            env!("CARGO_MANIFEST_DIR"),
            "/.github/workflows/coverage-main.yml"
        )),
    ),
];

/// A workflow's name and source text, passed together at the parsing boundary.
type WorkflowInput<'a> = (&'a str, &'a str);

/// A parsed workflow with its source lines retained for step-local checks.
struct Workflow<'a> {
    /// The name used in diagnostic messages.
    name: &'a str,
    /// The original text, retained for the listed-workflow presence check.
    source: &'a str,
    /// The source lines with their original line numbers.
    lines: Vec<WorkflowLine<'a>>,
}

/// One source line in a workflow.
#[derive(Clone, Copy)]
struct WorkflowLine<'a> {
    /// The line's original text.
    text: &'a str,
    /// The one-based line number in the workflow.
    number: usize,
}

impl<'a> WorkflowLine<'a> {
    /// Returns the number of leading spaces on this line.
    fn indent(self) -> usize { self.text.len() - self.text.trim_start().len() }

    /// Returns whether this line opens a step: a `- ` list item.
    fn opens_step(self) -> bool { self.text.trim_start().starts_with("- ") }

    /// Returns whether this line is blank after trimming whitespace.
    fn is_blank(self) -> bool { self.text.trim().is_empty() }

    /// Returns whether this line is a comment.
    fn is_comment(self) -> bool { self.text.trim_start().starts_with('#') }

    /// Returns whether this line names the shared Rust setup action.
    fn is_setup_rust(self) -> bool { self.text.contains("setup-rust@") && !self.is_comment() }

    /// Returns whether this line names the coverage action.
    fn is_coverage_action(self) -> bool {
        self.text.contains("generate-coverage@") && !self.is_comment()
    }

    /// Returns this line's `RUSTFLAGS` value, when it assigns one.
    fn rustflags(self) -> Option<RustFlags<'a>> {
        self.text
            .trim()
            .strip_prefix("RUSTFLAGS:")
            .map(str::trim)
            .map(|value| RustFlags { value })
    }

    /// Returns whether this line passes the install-mold action input.
    fn installs_linker(self) -> bool {
        let squeezed: String = self
            .text
            .chars()
            .filter(|character| !matches!(character, ' ' | '\'' | '"'))
            .collect();
        squeezed == "install-mold:true"
    }
}

/// The lines belonging to one workflow step.
struct WorkflowStep<'lines, 'text> {
    /// The step's own list item and all following lines up to the next step.
    lines: &'lines [WorkflowLine<'text>],
}

impl WorkflowStep<'_, '_> {
    /// Returns whether the step passes `install-mold: 'true'` (quoted or bare).
    fn installs_linker(&self) -> bool { self.lines.iter().any(|line| line.installs_linker()) }

    /// Returns the step's assigned `RUSTFLAGS`, if present.
    fn rustflags(&self) -> Option<RustFlags<'_>> {
        self.lines.iter().find_map(|line| line.rustflags())
    }
}

/// A step-local `RUSTFLAGS` value.
struct RustFlags<'a> {
    /// The assigned flag text.
    value: &'a str,
}

impl RustFlags<'_> {
    /// Returns whether flags select any part of the development build standard.
    fn include_development_standard(&self) -> bool {
        [
            "-Zcodegen-backend=cranelift",
            "-Zthreads",
            "-Clinker=evert-clang-mold",
            "mold",
        ]
        .iter()
        .any(|flag| self.value.contains(flag))
    }
}

/// A reason a coverage step's local `RUSTFLAGS` assignment is invalid.
enum CoverageFlagIssue {
    /// The step did not assign `RUSTFLAGS`.
    Missing,
    /// The assigned flags include part of the development build standard.
    DevelopmentStandard {
        /// The offending value, included in the diagnostic.
        value: String,
    },
}

impl CoverageFlagIssue {
    /// Formats this issue with the workflow and action line that caused it.
    fn problem(&self, workflow: &Workflow<'_>, line_number: usize) -> String {
        match self {
            Self::Missing => format!(
                "{}:{line_number}: a coverage step does not assign RUSTFLAGS",
                workflow.name
            ),
            Self::DevelopmentStandard { value } => format!(
                "{}:{line_number}: a coverage step assigns a standard flag: {value}",
                workflow.name
            ),
        }
    }
}

/// Classifies the coverage flag assignment for one step.
fn coverage_flag_issue(step: &WorkflowStep<'_, '_>) -> Option<CoverageFlagIssue> {
    step.rustflags()
        .map_or(Some(CoverageFlagIssue::Missing), |flags| {
            flags
                .include_development_standard()
                .then(|| CoverageFlagIssue::DevelopmentStandard {
                    value: flags.value.to_owned(),
                })
        })
}

impl<'a> Workflow<'a> {
    /// Parses workflow lines while retaining the original name and source.
    fn from_input((name, source): WorkflowInput<'a>) -> Self {
        let lines = source
            .lines()
            .enumerate()
            .map(|(index, text)| WorkflowLine {
                text,
                number: index + 1,
            })
            .collect();
        Self {
            name,
            source,
            lines,
        }
    }

    /// Returns the step containing the line at `at`.
    fn step_at(&self, at: usize) -> WorkflowStep<'_, '_> {
        let here = self.lines.get(at).copied();
        let step_indent = match here {
            Some(line) if line.opens_step() => line.indent(),
            Some(line) => line.indent().saturating_sub(2),
            None => 0,
        };
        let start = (0..=at)
            .rev()
            .find(|&index| {
                self.lines
                    .get(index)
                    .is_some_and(|line| line.opens_step() && line.indent() == step_indent)
            })
            .unwrap_or(at);
        let end = (at + 1..self.lines.len())
            .find(|&index| {
                self.lines.get(index).is_some_and(|line| {
                    !line.is_blank()
                        && (line.indent() < step_indent
                            || (line.opens_step() && line.indent() <= step_indent))
                })
            })
            .unwrap_or(self.lines.len());
        WorkflowStep {
            lines: self.lines.get(start..end).unwrap_or_default(),
        }
    }

    /// Returns complaints for setup steps missing the `mold` installation input.
    fn linker_install_problems(&self) -> Problems {
        self.lines
            .iter()
            .enumerate()
            .filter(|(_, line)| line.is_setup_rust())
            .filter(|(at, _)| !self.step_at(*at).installs_linker())
            .map(|(_, line)| {
                format!(
                    "{}:{}: a setup-rust step does not pass `install-mold: 'true'`",
                    self.name, line.number
                )
            })
            .collect()
    }

    /// Returns complaints for coverage steps with missing or development flags.
    fn coverage_problems(&self) -> Problems {
        self.lines
            .iter()
            .enumerate()
            .filter(|(_, line)| line.is_coverage_action())
            .filter_map(|(at, line)| {
                coverage_flag_issue(&self.step_at(at)).map(|issue| issue.problem(self, line.number))
            })
            .collect()
    }

    /// Returns complaints for one listed workflow and rejects an empty listing.
    fn listed_problems(&self) -> Problems {
        let mut problems = self.linker_install_problems();
        problems.extend(self.coverage_problems());
        if !self.source.contains("setup-rust@") {
            problems.push(format!(
                "{}: the listed workflow has no setup-rust step, so the check proves nothing",
                self.name
            ));
        }
        problems
    }
}

/// Returns the complaint about each `setup-rust` step in one workflow that does
/// not pass `install-mold: 'true'`.
///
/// ```text
/// - uses: org/shared-actions/.github/actions/setup-rust@<sha>
///   with:
///     install-mold: 'true'      -> no complaint
/// ```
pub fn linker_install_problems(name: &str, workflow: &str) -> Problems {
    Workflow::from_input((name, workflow)).linker_install_problems()
}

/// Returns the complaint about each coverage step in one workflow that does not
/// assign `RUSTFLAGS` itself, or assigns a development backend, frontend, or
/// linker.
///
/// A coverage build is a measurement, so it takes none of the development
/// backend, frontend, or linker flags. The exception is explicit in the step,
/// not a side effect of whatever the setup action exports.
///
/// ```text
/// - uses: org/shared-actions/.github/actions/generate-coverage@<sha>
///   env:
///     RUSTFLAGS: -D warnings      -> no complaint
/// ```
pub fn coverage_problems(name: &str, workflow: &str) -> Problems {
    Workflow::from_input((name, workflow)).coverage_problems()
}

/// Returns every complaint about the listed workflows.
pub fn workflow_problems() -> Problems {
    WORKFLOWS
        .iter()
        .flat_map(|(name, text)| Workflow::from_input((*name, *text)).listed_problems())
        .collect()
}
