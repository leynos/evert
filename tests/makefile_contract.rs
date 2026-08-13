//! Contract test asserting the Makefile wires the dev-fast profile into
//! the standard development targets and keeps it out of coverage.
//!
//! Operation Parabellum's Wave 2+3 sponsor decision makes the dev-fast
//! profile (Cranelift plus mold, `tools/dev-fast/config.toml`) the
//! standard local development path: `make build`, `make test`,
//! `make lint`, and `make typecheck` must pass `--config` pointing at
//! that fragment to every cargo invocation they make, while
//! `make coverage` must keep the supported LLVM backend and platform
//! linker. This test reads the repository's own `Makefile` textually
//! and fails fast if a future edit drops the wiring, before the
//! estate-wide audit (concordat's forthcoming DF-004 rule) would ever
//! catch it. See AGENTS.md's "dev-fast is the standard development
//! path" section for the convention this test enforces.

use std::io;

use camino::Utf8Path;
use cap_std::{ambient_authority, fs_utf8::Dir};
use rstest::rstest;

/// Opens the crate manifest directory as a capability directory handle,
/// so file access below stays scoped to the checkout rather than
/// touching the ambient working directory via `std::fs`.
fn manifest_dir() -> io::Result<Dir> {
    Dir::open_ambient_dir(env!("CARGO_MANIFEST_DIR"), ambient_authority())
}

/// Reads the repository's `Makefile` as UTF-8 text.
fn read_makefile() -> io::Result<String> { manifest_dir()?.read_to_string("Makefile") }

/// Returns whether `relative` exists as a file beneath the crate
/// manifest directory.
fn manifest_has_file(relative: &Utf8Path) -> io::Result<bool> {
    Ok(manifest_dir()?.is_file(relative))
}

/// Returns the recipe lines following an unindented `<target>:` line, up
/// to (but excluding) the next unindented line. `None` means the target
/// itself was not found; `Some(String::new())` means the target exists
/// but has no recipe of its own (a dependency-only forwarding rule).
fn recipe_block(makefile: &str, target: &str) -> Option<String> {
    let header = format!("{target}:");
    let mut found_header = false;
    let mut block = Vec::new();
    for line in makefile.lines() {
        if found_header {
            if line.starts_with('\t') || line.starts_with(' ') {
                block.push(line);
            } else {
                break;
            }
        } else if line.starts_with(&header) {
            found_header = true;
        }
    }
    found_header.then(|| block.join("\n"))
}

/// Matches the estate's `(?i)dev[-_]fast` convention without pulling in
/// the `regex` crate for a single fixed pattern.
fn mentions_dev_fast(text: &str) -> bool {
    let lower = text.to_lowercase();
    lower.contains("dev-fast") || lower.contains("dev_fast")
}

/// Confirms each standard development target routes cargo through the
/// dev-fast fragment.
///
/// The `#[case]` pairs the target a developer invokes with the Makefile
/// rule whose recipe text should be checked. `build`'s own rule has no
/// recipe of its own: it depends on the `target/%/$(TARGET)` pattern
/// rule that actually invokes cargo (shared with `release`, which must
/// stay excluded), so that is the block resolved and checked here.
#[rstest]
#[case("build", "target/%/$(TARGET)")]
#[case("test", "test")]
#[case("lint", "lint")]
#[case("typecheck", "typecheck")]
fn standard_targets_use_dev_fast(#[case] invoked_target: &str, #[case] recipe_target: &str) {
    let makefile = read_makefile().expect("Makefile must be readable");
    let block = recipe_block(&makefile, recipe_target).unwrap_or_else(|| {
        panic!(
            "Makefile target `{recipe_target}` (backing `make {invoked_target}`) was not found; \
             the dev-fast standard-path convention requires it to exist and route cargo through \
             --config tools/dev-fast/config.toml, per AGENTS.md's \"dev-fast is the standard \
             development path\" section"
        )
    });
    assert!(
        block.contains("--config"),
        "Makefile target `{recipe_target}` (backing `make {invoked_target}`) must pass --config \
         to cargo so it uses the dev-fast profile, per AGENTS.md's \"dev-fast is the standard \
         development path\" section"
    );
    assert!(
        mentions_dev_fast(&block),
        "Makefile target `{recipe_target}` (backing `make {invoked_target}`) must reference the \
         dev-fast fragment (tools/dev-fast/config.toml) so --config actually points at it, per \
         AGENTS.md's \"dev-fast is the standard development path\" section"
    );
}

/// Confirms the coverage target keeps the supported LLVM backend and
/// platform linker rather than picking up the dev-fast fragment.
#[test]
fn coverage_target_excludes_dev_fast() {
    let makefile = read_makefile().expect("Makefile must be readable");
    let Some(block) = recipe_block(&makefile, "coverage") else {
        return; // No coverage target in this repository; nothing to guard.
    };
    assert!(
        !mentions_dev_fast(&block),
        "Makefile target `coverage` must not reference the dev-fast fragment: coverage builds \
         require the supported LLVM backend and platform linker, per AGENTS.md's \"dev-fast is \
         the standard development path\" section"
    );
}

/// Confirms the dev-fast fragment the Makefile wiring depends on exists.
#[test]
fn dev_fast_fragment_exists() {
    let relative = Utf8Path::new("tools/dev-fast/config.toml");
    let found = manifest_has_file(relative).expect("manifest directory must be readable");
    assert!(
        found,
        "{relative} must exist: the standard build/test/lint/typecheck targets pass --config \
         pointing at it"
    );
}
