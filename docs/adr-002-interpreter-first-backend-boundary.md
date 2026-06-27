# Architectural decision record 002: Interpreter-first backend boundary

## Status

Accepted for the initial design.

## Date

2026-06-27.

## Context and problem statement

The source material explicitly requires an interpreter before LLVM. Evert's
semantics include effect rows, local mutation, pure lazy thunks, monads,
handlers, and later structured concurrency. If native code generation starts
before the semantics are executable in a simpler oracle, backend defects can be
mistaken for language defects.

## Decision drivers

- The Core interpreter must define expected runtime behaviour for conformance
  tests.
- LLVM should not be a build prerequisite for front-end and interpreter work.
- Backend objects are mutable and target-specific, so they must not enter the
  Salsa database.
- Textual intermediate representations make reviews and golden tests easier.

## Options considered

| Option                 | Strengths                                          | Weaknesses                                                                         |
| ---------------------- | -------------------------------------------------- | ---------------------------------------------------------------------------------- |
| LLVM first             | Proves native execution early                      | Couples semantics to backend bugs and forces LLVM installation on all contributors |
| Bytecode VM first      | Could become a long-term portable execution engine | Adds a second runtime target before the Core semantics are settled                 |
| Core interpreter first | Gives a semantic oracle and fast conformance loop  | Delays native performance work                                                     |

_Table 1: Execution strategy options._

## Decision outcome

Build a tree-walking Core interpreter before native code generation. Define a
narrow `Backend` trait in `evert_codegen_api`; keep textual LLVM IR and the
Inkwell-backed LLVM implementation behind an optional `evert_codegen_llvm`
adapter.

## Consequences

- MVP contributors can build and test the language without LLVM installed.
- Diagnostics, Core pretty-printing, and interpreter output become the first
  golden-test surfaces.
- The LLVM backend must prove conformance by comparing against interpreter
  results for the same Core programmes.
- Runtime object models for closures, thunks, handlers, and capabilities must
  be specified before the embedded backend becomes a release blocker.

## References

- `docs/terms-of-reference.md`.
- `docs/evert-design.md`.
- Inkwell repository, <https://github.com/TheDan64/inkwell>.
- Rust compiler development guide,
  <https://rustc-dev-guide.rust-lang.org/overview.html>.
