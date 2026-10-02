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
- `make lint` runs rustdoc, Clippy, and Whitaker, then the Python linters, with
  warnings denied.
- `make lint-python` runs only the Python linters: Ruff, Pylint, the df12 house
  lints, `ambrleaks`, and Interrogate.
- `make test` runs `cargo nextest run` when cargo-nextest is installed and
  falls back to `cargo test` otherwise. All projects also run doctests.
- `make test-workflow-contracts` runs the shared CV-005 workflow checks and
  the repository's pytest workflow contracts. It needs `uv`.
- `make typecheck` checks the build tools, type-checks the Python sources with
  ty, then checks all Rust targets and features without building binaries.
- `make typecheck-python` and `make typecheck-rust` run only the Python or only
  the Rust half.
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
pinned Rust toolchain and linker tools for native Linux x86_64 and aarch64
development routes. On supported Linux hosts, the development build
(`make build`), tests (`make test`), lint, and typecheck use rustc's LLVM
backend, the nightly `-Zthreads=8` frontend, and the pinned `mold` linker.
Cranelift is not selected: its panic-unwind failures are tracked for review in
[issue #80](https://github.com/leynos/evert/issues/80) on 1 April 2027.

The Linux Cargo configuration requires the pinned `mold` binary and the
`evert-clang-mold` wrapper. Run `make install-build-tools` before the first
Linux development build; it installs the pinned linker and wrapper. CI
provisions the same prerequisite through `setup-rust` with
`install-mold: 'true'`. Bare Cargo commands on Linux need
`$BUILD_TOOLS_PREFIX/bin` on `PATH`; Make targets add it automatically. macOS
and Windows keep their platform linkers.

Coverage and release deliberately leave out the development flags while
preserving caller-supplied `RUSTFLAGS`. `make coverage` uses Clang with `lld`
for compatibility with coverage tooling. `make release` uses stable Rust and
the platform linker; the release workflow uses the stable Cross route for its
matrix targets. Install clang, python3, and cargo-audit before running the full
generated workflow locally on Linux; coverage also requires lld. The Python
linters, the Python type check, and workflow contract tests use `uv`, which
fetches CPython 3.14 on demand. The [developers' guide](developers-guide.md)
describes the backend and linker routing.
