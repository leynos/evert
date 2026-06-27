# Evert

*A research project for a strict-by-default functional systems language.*

Evert asks a narrow question with wide consequences: what would a functional
systems language look like if power stayed local, explicit, and non-contagious?

The repository is currently a design and compiler-foundation project. There is
no usable Evert compiler yet. The valuable artefacts are the terms of
reference, design, roadmap, and ADRs that define the language thesis and the
reference compiler plan.

______________________________________________________________________

## Why Evert?

Many programming-language ideas are excellent in isolation and expensive when
they become ambient defaults. Evert explores whether a language can make each
powerful mechanism opt-in without losing the ability to write direct, readable,
systems-capable code.

- **Strict by default:** laziness is explicit, pure-only, and memoized.
- **Effects are typed:** `pure fn` means an empty inferred effect row.
- **Handlers, not monads, carry effects:** monads remain ordinary data
  abstractions.
- **Compiler evidence first:** a typed Core interpreter becomes the semantic
  oracle before LLVM or native execution.
- **Systems power is staged:** mutation, structured concurrency, capabilities,
  ownership, and unsafe work have to earn their semantics before they execute.

______________________________________________________________________

## Quick start

There is nothing to install as a language user yet. From a checkout, validate
the current research documentation with:

```shell
make fmt
make nixie
```

Then start with the design spine:

- [Terms of reference](docs/terms-of-reference.md): the problem, scope,
  stakeholders, constraints, and open questions.
- [Evert design](docs/evert-design.md): the proposed language semantics and
  Rust reference compiler architecture.
- [Roadmap](docs/roadmap.md): the planned implementation order, from ECLP
  split to interpreter-backed compiler slices.
- [ADRs](docs/contents.md#architecture-decisions): accepted decisions that
  constrain the design and roadmap.

______________________________________________________________________

## Research focus

Evert is not trying to be a production language today. It is trying to make a
language design falsifiable before implementation momentum hides the hard
questions.

The current design concentrates on:

- a lossless CST and recovery-capable parser,
- row-polymorphic effects and direct-style handlers,
- explicit pure laziness with black-hole detection,
- a small typed Core IR,
- a tree-walking Core interpreter as semantic oracle,
- an early gate for effect-interface sealing,
- staged capability authority before host effects such as `Clock`,
- staged local mutation with non-escape and heap-independence obligations.

______________________________________________________________________

## Repository status

The Rust package is still starter scaffolding. The next research and
implementation work is to split the source ECLP material into proposal files,
ratify the first crate boundaries, and build conformance fixtures before
compiler breadth.

The repository currently treats documentation as the source of truth. If a
language decision changes, update the relevant design, roadmap, ADR, or guide
with the same care as code.

______________________________________________________________________

## Learn more

- [Documentation contents](docs/contents.md): complete documentation index.
- [Evert context](docs/context.md): shared terminology for language and
  compiler documents.
- [User guide](docs/users-guide.md): current public commands and project
  state.
- [Developer guide](docs/developers-guide.md): contributor workflow and
  normative references.
- [Repository layout](docs/repository-layout.md): ownership boundaries for
  source, tests, automation, and long-lived docs.

______________________________________________________________________

## Contributing

Contributions are welcome, especially design review, source research,
conformance fixtures, and small compiler-foundation slices that follow the
roadmap.

Please read [AGENTS.md](AGENTS.md) and the
[developer guide](docs/developers-guide.md) before changing the repository.

______________________________________________________________________

## Licence

ISC - see [LICENSE](LICENSE) for details.
