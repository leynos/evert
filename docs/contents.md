# Documentation contents

[Documentation contents](contents.md) is the index for Evert's documentation
set.

## Project guides

- [User guide](users-guide.md) explains Evert's current user-facing state and
  the public build and validation commands.
- [Developer guide](developers-guide.md) explains the local workflow and
  implementation tooling for contributors.
- [Repository layout](repository-layout.md) explains the repository's
  top-level files, directories, and ownership boundaries.
- [Documentation style guide](documentation-style-guide.md) defines the
  spelling, structure, Markdown, Architecture Decision Record (ADR), Request
  for Comments (RFC), and roadmap conventions used by this documentation set.

## Project definition

- [Evert context](context.md) defines the core language, compiler, and
  architecture terms used across the documentation set.
- [Terms of reference](terms-of-reference.md) records the problem space,
  stakeholders, scope, constraints, success criteria, and open questions before
  implementation work starts.
- [Evert design](evert-design.md) defines the initial language and compiler
  architecture for the Rust reference implementation.
- [Roadmap](roadmap.md) sequences design and implementation work into
  testable phases, steps, and tasks.

## Architecture decisions

- [ADR 001: Query-based compiler workspace](adr-001-query-based-compiler-workspace.md)
  selects a layered Rust workspace coordinated by a Salsa query database.
- [ADR 002: Interpreter-first backend boundary](adr-002-interpreter-first-backend-boundary.md)
  defers native code generation behind a backend port until the interpreter is
  a working semantic oracle.
- [ADR 003: Local-power language semantics](adr-003-local-power-language-semantics.md)
  records the initial semantic rule that power must be local, explicit, and
  non-contagious.

## Reference inputs

- [Inciting incident](references/inciting-incident.md) preserves the original
  product and language-design prompt that motivated Evert.
- [Evert plan](references/evert-plan.md) preserves the proposed planning-tool
  output used as non-binding design input.

## Rust reference material

- [Reliable testing in Rust via dependency injection](reliable-testing-in-rust-via-dependency-injection.md)
  explains how to keep tests deterministic by injecting environment, clock,
  filesystem, and other external dependencies.
- [Rust doctest Don't Repeat Yourself guide](rust-doctest-dry-guide.md)
  explains how to write maintainable, executable Rust documentation examples.
- [Rust testing with `rstest` fixtures](rust-testing-with-rstest-fixtures.md)
  explains fixture-based, parameterized, and asynchronous testing with `rstest`.

## Engineering practice

- [Complexity antipatterns and refactoring strategies](complexity-antipatterns-and-refactoring-strategies.md)
  explains cognitive complexity, the bumpy-road antipattern, and refactoring
  approaches for maintainable code.
- [Scripting standards](scripting-standards.md) explains the preferred Python
  scripting stack, command execution patterns, and test expectations for helper
  scripts.
