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
//!
//! Assertions check each cargo-invoking recipe *line* individually
//! rather than the recipe block as a whole: a target with several
//! cargo lines (nextest plus doc-tests, `cargo doc` plus `cargo
//! clippy`) would otherwise pass a whole-block substring match even
//! when only one of those lines carries `--config`.

use std::{io, process::Command};

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

/// Returns the lines within `block` that actually invoke cargo via the
/// Makefile's `$(CARGO)` macro, as distinct from unrelated recipe lines
/// such as the Whitaker Dylint invocation, which is not cargo and is
/// not expected to carry `--config`.
fn cargo_invocation_lines(block: &str) -> Vec<&str> {
    block
        .lines()
        .filter(|line| line.contains("$(CARGO)"))
        .collect()
}

/// Confirms every cargo invocation in a standard development target's
/// recipe routes through the dev-fast fragment.
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
    let cargo_lines = cargo_invocation_lines(&block);
    assert!(
        !cargo_lines.is_empty(),
        "Makefile target `{recipe_target}` (backing `make {invoked_target}`) has no $(CARGO) \
         invocation to check; the dev-fast standard-path convention expects at least one, per \
         AGENTS.md's \"dev-fast is the standard development path\" section"
    );
    for line in cargo_lines {
        assert!(
            line.contains("--config"),
            "Makefile target `{recipe_target}` (backing `make {invoked_target}`) has a cargo \
             invocation that does not pass --config: `{line}`; every cargo line must use the \
             dev-fast profile, per AGENTS.md's \"dev-fast is the standard development path\" \
             section"
        );
        assert!(
            mentions_dev_fast(line),
            "Makefile target `{recipe_target}` (backing `make {invoked_target}`) has a cargo \
             invocation whose --config does not reference the dev-fast fragment: `{line}`, per \
             AGENTS.md's \"dev-fast is the standard development path\" section"
        );
    }
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

/// Runs `make --dry-run <target> CARGO=<cargo_override>` in the crate
/// root and returns its captured stdout. `--dry-run` prints the recipe
/// Make would run without executing it, so this needs neither a
/// nightly toolchain nor `mold` installed.
fn make_dry_run(target: &str, cargo_override: &str) -> io::Result<String> {
    let output = Command::new("make")
        .arg("--dry-run")
        .arg(target)
        .arg(format!("CARGO={cargo_override}"))
        .current_dir(env!("CARGO_MANIFEST_DIR"))
        .output()?;
    String::from_utf8(output.stdout)
        .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))
}

/// Confirms the opt-in `dev-build`/`dev-test` targets honour a CARGO
/// override, proving they invoke `$(CARGO)` rather than a hard-coded
/// `cargo`. Overriding CARGO on the command line must show up ahead of
/// `--config`, which must in turn come before the dev-fast fragment
/// reference, in the emitted recipe.
#[rstest]
#[case("dev-build")]
#[case("dev-test")]
fn dev_fast_targets_honour_cargo_override(#[case] target: &str) {
    let output = make_dry_run(target, "probe-cargo").expect("make --dry-run must run and succeed");
    let cargo_pos = output.find("probe-cargo").unwrap_or_else(|| {
        panic!(
            "`make --dry-run {target} CARGO=probe-cargo` did not emit \"probe-cargo\"; the recipe \
             must invoke $(CARGO) rather than a hard-coded cargo, per AGENTS.md's \"dev-fast is \
             the standard development path\" section. Output: {output:?}"
        )
    });
    let config_pos = output.find("--config").unwrap_or_else(|| {
        panic!(
            "`make --dry-run {target} CARGO=probe-cargo` did not emit \"--config\". Output: \
             {output:?}"
        )
    });
    assert!(
        cargo_pos < config_pos,
        "`make --dry-run {target} CARGO=probe-cargo` must emit the substituted cargo binary \
         before --config; got: {output:?}"
    );
    let lower = output.to_lowercase();
    let dev_fast_pos = ["dev-fast", "dev_fast"]
        .into_iter()
        .filter_map(|needle| lower.find(needle))
        .min()
        .unwrap_or_else(|| {
            panic!(
                "`make --dry-run {target} CARGO=probe-cargo` did not reference the dev-fast \
                 fragment. Output: {output:?}"
            )
        });
    assert!(
        config_pos < dev_fast_pos,
        "`make --dry-run {target} CARGO=probe-cargo` must emit --config before the dev-fast \
         fragment reference; got: {output:?}"
    );
}
