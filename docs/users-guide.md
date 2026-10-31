# User guide

Evert is currently in the design and compiler-foundation stage. The repository
does not yet provide a usable Evert compiler command. The current user-facing
surface is the project documentation and the validation commands that keep that
documentation and starter Rust package healthy.

## Where to start

- Read [terms of reference](terms-of-reference.md) for the problem Evert is
  intended to solve.
- Read [Evert context](context.md) for the language and compiler terminology.
- Read [Evert design](evert-design.md) for the proposed language semantics,
  compiler architecture, and implementation boundaries.
- Read [roadmap](roadmap.md) for the planned implementation order.

## Current tooling

The repository contains a starter Rust package named `evert` (version 0.1.0).
It is placeholder scaffolding until the compiler crates described in the design
land. The package has these characteristics:

- It uses Rust edition 2024 and has no runtime dependencies.
- `rust-toolchain.toml` pins the development nightly toolchain.
- `Cargo.toml` defines strict Clippy, rustc, and rustdoc lint tables.
- The library (`src/lib.rs`) is auto-detected and contains a doctested `greet`
  stub.
- The binary (`src/main.rs`) is auto-detected and is a stub entrypoint that
  prints a greeting.
- Development builds keep no incremental compilation state and no debug
  information: `[profile.dev]` sets `incremental = false` and `debug = 0`, and
  `.cargo/config.toml` sets the native `[unstable] embed-metadata = false` key.
  To debug, set `CARGO_PROFILE_DEV_DEBUG=true`; to rebuild incrementally, set
  `CARGO_INCREMENTAL=1`.
- `[package.metadata.binstall]` points cargo-binstall at GitHub release assets.
- `.github/workflows/release.yml` builds and publishes release binaries for
  Linux, Windows, macOS, and FreeBSD targets when a `v*.*.*` tag is pushed.

See the [developers' guide](developers-guide.md) for local build tooling,
including the default build configuration and platform linker details.

## Makefile targets

The repository `Makefile` exposes these public targets:

- `make all` runs formatting checks, linting, typechecking, tests, spelling,
  and workflow contracts.
- `make fmt` formats Rust and Markdown sources.
- `make check-fmt` verifies Rust and Markdown formatting.
- `make lint` checks Python docstring coverage with Interrogate, then runs
  rustdoc, Clippy, Whitaker, and the Python linters with warnings denied;
  `make lint-clippy` runs rustdoc and Clippy only.
- `make interrogate` checks every tracked Python source directory for complete
  docstring coverage and fails on any undocumented definition.
- `make lint-python` runs Ruff, Pylint, the df12 house lints, `ambrleaks`, and
  Interrogate.
- `make test` runs `cargo nextest run` when cargo-nextest is installed and
  falls back to `cargo test` otherwise, then runs doctests.
- `make test-workflow-contracts` runs the shared CV-005 workflow checks and
  the repository's pytest workflow contracts. It needs `uv`.
- `make typecheck` checks the build tools, type-checks the Python sources with
  ty, then checks all Rust targets and features without building binaries.
- `make typecheck-python` and `make typecheck-rust` run only the Python or only
  the Rust half.
- `make build` builds the debug binary.
- `make release` builds the release binary.
- `make install-build-tools` installs the pinned Rust toolchain and local
  linker tools needed by the standard development build.
- `make check-build-tools` checks that the pinned toolchain, linker, and Clang
  wrapper are installed and selected correctly; it does not install them.
- `make coverage` writes `lcov.info` using `cargo llvm-cov` and `lld`.
- `make audit` derives the Rust workspace root with `cargo metadata` and runs
  `cargo audit` once from that root.
- `make markdownlint` enforces repository spelling, then lints Markdown files.
- `make spelling` refreshes the generated spelling configuration and scans
  tracked files for en-GB-oxendict spelling.
- `make nixie` validates Mermaid diagrams.
- `make clean` removes build artefacts.
- `make help` lists available targets.

The former `make dev-build` and `make dev-test` targets are no longer
available. Use `make build` and `make test` for the standard development route.

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
local workflow on Linux; coverage also requires lld. The Python linters, the
Python type check, and workflow contract tests use `uv`, which fetches CPython
3.14 on demand. The [developers' guide](developers-guide.md) describes the
backend and linker routing. The gates also use Whitaker, `markdownlint-cli2`,
`mdtablefix`, and `nixie`, and coverage needs `cargo-llvm-cov`; cargo-nextest
is optional.
