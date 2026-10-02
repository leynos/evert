//! `Evert` application entry point.

// TODO: Remove when replacing app scaffolding
// (docs/execplans/rust-project-enhancements.md).
/// Application entry point.
fn main() -> std::io::Result<()> {
    use std::io::Write;

    writeln!(std::io::stdout().lock(), "Hello from Evert!")
}
