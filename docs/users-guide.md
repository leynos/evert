# User Guide

This guide explains how to use the generated Evert project after rendering it
from the template.

## Generated Tooling

Generated projects use Rust 2024, a pinned nightly toolchain, strict lint
settings, and documented starter code. Library projects render `src/lib.rs`.
Application projects render `src/main.rs`, `src/lib.rs`, release automation, and
`[package.metadata.binstall]` metadata for binary installation.

See the [developers' guide](developers-guide.md) for local build tooling,
including the default build configuration and platform linker details.

## Makefile Targets

The generated `Makefile` exposes these public targets:

- `make all` runs formatting, linting, tests, spelling, and workflow contracts.
- `make check-fmt` verifies Rust and Markdown formatting.
- `make lint` runs rustdoc, Clippy, and Whitaker with warnings denied.
- `make test` runs `cargo nextest run` when cargo-nextest is installed and
  falls back to `cargo test` otherwise. All projects also run doctests.
- `make test-workflow-contracts` runs the shared CV-005 workflow checks and
  the repository's pytest workflow contracts. It needs `uv`.
- `make typecheck` checks all targets and features without building binaries.
- `make build` builds the debug target.
- `make install-build-tools` installs the pinned Rust toolchain and local
  linker tools needed by the standard development build.
- `make release` builds the release target.
- `make coverage` writes `lcov.info` using `cargo llvm-cov` and `lld`.
- `make audit` derives the Rust workspace root with `cargo metadata` and runs
  `cargo audit` once from that root.
- `make markdownlint` checks Markdown files.
- `make spelling` refreshes the generated spelling configuration and scans
  tracked files.
- `make nixie` validates Mermaid diagrams.

Before the first local build, run `make install-build-tools` to install the
pinned Rust toolchain and linker tools for the `x86_64-unknown-linux-gnu`
development route. Rustc uses its LLVM backend; the selected target also uses
the parallel frontend and pinned `mold` linker. Bare Cargo commands on that
target need `$BUILD_TOOLS_PREFIX/bin` on `PATH`; Make targets add it
automatically. Other Linux targets use their platform linker, while non-Linux
targets keep their platform linker. Install clang, python3, and cargo-audit
before running the full generated workflow locally on Linux; coverage also
requires lld. The [developers' guide](developers-guide.md) describes the
backend and linker routing.
