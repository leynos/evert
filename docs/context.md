# Evert context

This document defines the terms used across Evert's terms of reference, design,
roadmap, and future Evert Core Language Proposals (ECLPs). It is the ubiquitous
language for the project; when a design document gives a term a different
meaning, this document should be updated or the divergence should be made
explicit.

## Language and specification terms

| Term                   | Definition                                                                                                                                                                                      |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Evert                  | A strict-by-default functional systems language and its reference compiler.                                                                                                                     |
| ECLP                   | An Evert Core Language Proposal: a compact specification document for one language capability, invariant, or refusal.                                                                           |
| Power                  | Any capability that changes evaluation, effects, mutation, ownership, concurrency, unsafe code, or abstraction machinery. Evert's rule is that power stays local, explicit, and non-contagious. |
| Pure function          | A function whose inferred effect row is empty. `pure fn` asserts and locks this property.                                                                                                       |
| Effect row             | The structural set of effects attached to a function arrow or expression.                                                                                                                       |
| Handler                | A construct that interprets, eliminates, transforms, or re-emits operations from an effect row.                                                                                                 |
| Capability             | A value that grants authority to perform an operation, such as filesystem, network, clock, or unsafe system access.                                                                             |
| Monadicity             | Evert's support for `Functor`, `Applicative`, `Monad`, and `do M { ... }` as ordinary data-level abstractions rather than the only way to perform effects.                                      |
| Lazy value             | A pure suspended computation that is forced on demand and memoized after successful evaluation.                                                                                                 |
| Black hole             | The runtime state of a lazy value currently being forced; re-entering the same thunk reports recursive forcing instead of looping silently.                                                     |
| Mutate region          | A lexical region that permits local mutable cells while preventing those cells from escaping.                                                                                                   |
| Resource value         | A linear or affine value with deterministic finalization rules.                                                                                                                                 |
| Structured concurrency | A concurrency model where child tasks cannot outlive the lexical task scope that spawned them.                                                                                                  |
| Edition                | A declared language compatibility boundary that can change parsing defaults or reserve syntax without silently changing runtime meaning.                                                        |

## Compiler architecture terms

| Term            | Definition                                                                                                                                                  |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Source map      | The mapping from `FileId` and byte spans to user-facing file, line, and column locations.                                                                   |
| Trivia          | Whitespace and comments retained for diagnostics, formatting, and lossless syntax trees.                                                                    |
| CST             | Concrete syntax tree. Evert keeps it lossless so source can round-trip through formatting and editor features.                                              |
| AST             | Typed view over the CST that gives compiler passes structured access without making syntax semantic.                                                        |
| HIR             | High-level intermediate representation after name resolution, desugaring, module scoping, and stable definition identifier assignment.                      |
| Core IR         | A small, explicitly typed intermediate representation that defines Evert's executable semantics before backend lowering.                                    |
| LIR             | Lower-level monomorphic representation after closure, thunk, dictionary, and handler lowering.                                                              |
| Semantic oracle | The Core interpreter that defines expected runtime behaviour and checks backend conformance.                                                                |
| Query database  | The Salsa-backed database that stores source inputs, interned identities, tracked compiler outputs, and accumulated diagnostics.                            |
| Durable data    | Compiler data safe to keep in the query database across edits, such as byte spans, `FileId`, interned symbols, and stable identifiers.                      |
| Adapter         | Infrastructure-facing implementation of a compiler port, such as the CLI, filesystem source loader, diagnostic renderer, interpreter host, or LLVM backend. |
| Port            | A narrow interface owned by the compiler domain or application layer and implemented by an adapter.                                                         |

## Naming conventions

- Use `ECLP-NNNN` for proposal identifiers.
- Use `FileId`, `Span`, `Symbol`, `DefId`, `TypeId`, `RowId`, and
  `EffectId` for stable compiler identifiers.
- Use `evert_*` for workspace crates and keep crate names aligned with their
  domain responsibility.
- Use `.evt` for Evert source files until an ECLP changes the extension.
