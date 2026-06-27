# Developer guide

This guide explains the contributor workflow for Evert.

## Normative design sources

Use these documents before adding or changing compiler behaviour:

- [Terms of reference](terms-of-reference.md) defines the problem space, scope,
  constraints, and success criteria.
- [Evert context](context.md) defines the terms used by the language and
  compiler documentation.
- [Evert design](evert-design.md) defines the compiler architecture and initial
  semantic contracts.
- [Roadmap](roadmap.md) sequences work into testable phases, steps, and tasks.
- [Repository layout](repository-layout.md) explains ownership boundaries for
  source, tests, documentation, and automation.
- The accepted ADRs in `docs/adr-*.md` record decisions that constrain
  implementation work.

When a change alters language semantics, compiler architecture, public command
behaviour, or internal ownership boundaries, update the corresponding design,
roadmap, ADR, guide, or layout document in the same change.

## Local workflow

Use `make all` as the public entrypoint for formatting, linting, and tests.
`make lint` runs rustdoc, Clippy, and Whitaker. `make test` prefers
`cargo nextest run` and falls back to `cargo test` when cargo-nextest is not
available. `make audit` derives the Rust workspace root with `cargo metadata`,
logs workspace member manifests, and runs `cargo audit` once from the workspace
root. `make coverage` uses `cargo llvm-cov` with `lld`.

GitHub Actions Act validation lives in `.github/workflows/act-validation.yml`.
The main `.github/workflows/ci.yml` workflow deliberately does not run
`make test WITH_ACT=1`; the separate Act workflow runs those slower
container-backed checks in parallel.

## Tooling

Development builds use Cranelift for debug code generation. On Linux targets,
`.cargo/config.toml` configures clang to link with `mold` so debug builds link
quickly. Coverage generation uses `lld` because LLVM coverage tooling expects
LLVM-compatible linker behaviour.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

## Design workflow

Treat `docs/references/` as historical input rather than normative
specification. Promote decisions from those references into the terms of
reference, design, roadmap, ECLP files, or ADRs before implementing them.

Create implementation tasks from the roadmap. A task is ready when it names its
design source, dependency, success condition, and relevant validation target.
If implementation reveals a design mismatch, update the design before expanding
the code to work around the mismatch.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
