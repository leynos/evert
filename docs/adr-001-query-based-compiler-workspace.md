# Architectural decision record 001: Query-based compiler workspace

## Status

Accepted for the initial design.

## Date

2026-06-27.

## Context and problem statement

Evert needs a compiler architecture that keeps the language semantics testable
while leaving room for formatting, editor tooling, native code generation, and
future language-server work. The source material requires a lossless front end,
stable identifiers, an interpreter before LLVM, and a rule that durable
compiler data must not borrow lexer input or store LLVM objects.

## Decision drivers

- The ECLP corpus needs executable conformance evidence.
- The front end must preserve trivia for diagnostics and formatting.
- The semantic pipeline must support incremental recomputation and future IDE
  responsiveness.
- Rust crates should reflect real boundaries rather than one monolithic binary.
- Tests should exercise the same boundaries that the architecture claims.

## Options considered

| Option                                         | Strengths                                                                                                       | Weaknesses                                                                                                     |
| ---------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Single crate compiler                          | Fast to start and easy to navigate initially                                                                    | Blurs syntax, semantic analysis, runtime, and backend ownership; makes future LSP and backend isolation harder |
| Layered workspace with explicit query database | Aligns crates to compiler responsibilities; isolates backend and driver adapters; supports incremental analysis | Requires early boundary discipline and more manifest work                                                      |
| Copy rustc's shape closely                     | Proven for a production compiler                                                                                | Too large for a new language and risks importing Rust-specific constraints into Evert semantics                |

_Table 1: Compiler workspace options._

## Decision outcome

Use a layered Cargo workspace coordinated by a Salsa query database. Keep
source identity, syntax, HIR, type/effect checking, Core IR, lowering,
interpreter, runtime, backend API, LLVM backend, and CLI driver in separate
`evert_*` crates when those boundaries become concrete.

The initial crate map is:

- `evert_span`
- `evert_syntax`
- `evert_db`
- `evert_hir`
- `evert_types`
- `evert_core`
- `evert_lower`
- `evert_interpreter`
- `evert_runtime`
- `evert_codegen_api`
- `evert_codegen_llvm`
- `evert_driver`

## Consequences

- The domain crates own compiler concepts and expose narrow Rust APIs.
- Driving adapters such as `evert_driver` depend inward on the compiler
  application layer.
- Driven adapters such as `evert_codegen_llvm` implement backend ports without
  leaking LLVM objects into the query database.
- The workspace is heavier than a single crate, so early tasks must create only
  crates whose boundary is already justified by the design.
- Future refactors should remove nominal crates that do not earn their
  boundary.

## References

- `docs/terms-of-reference.md`.
- `docs/evert-design.md`.
- Salsa overview, <https://salsa-rs.github.io/salsa/overview.html>.
- rust-analyzer syntax guide,
  <https://github.com/rust-lang/rust-analyzer/blob/master/docs/book/src/contributing/syntax.md>.
