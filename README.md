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

## Credit where due

Evert is not pretending these ideas arrived out of a clear blue sky. We promise
we are not shooting for Pseuds Corner in *Private Eye*: the design is
explicitly indebted to a long line of programming-languages work, and the full
bibliography lives in
[the design references](docs/evert-design.md#17-references).

The up-front credits we would be very cheeky not to name are:

- Gordon Plotkin and Matija Pretnar,
  [Handlers of Algebraic Effects](https://arxiv.org/abs/1312.1399), for the
  semantic foundation of algebraic handlers.
- Daan Leijen,
  [Koka: Programming with Row Polymorphic Effect Types](https://arxiv.org/abs/1406.2061)
  and
  [Algebraic Effects for Functional Programming](https://www.microsoft.com/en-us/research/wp-content/uploads/2016/08/algeff-tr-2016-v3.pdf),
  for row-typed effects and practical compilation evidence.
- Daniel Hillerstrom and Sam Lindley,
  [Liberating Effects with Rows and Handlers](https://dl.acm.org/doi/10.1145/2976022.2976033),
  for the rows-and-handlers direction.
- Taro Sekiyama, Takeshi Tsukada, and Atsushi Igarashi,
  [Signature Restriction for Polymorphic Algebraic Effects](https://arxiv.org/abs/2003.08138),
  and Dariusz Biernacki, Maciej Pirog, Piotr Polesiuk, and Filip Sieczkowski,
  [Abstracting Algebraic Effects](https://dl.acm.org/doi/10.1145/3290319), for
  the warning that effect abstraction needs a hard boundary.
- John Launchbury and Simon Peyton Jones,
  [Lazy Functional State Threads](https://www.microsoft.com/en-us/research/wp-content/uploads/1994/06/lazy-functional-state-threads.pdf),
  for the local-state encapsulation idea.
- Jill Seaman and S. Purushothaman Iyer,
  [An Operational Semantics of Sharing in Lazy Evaluation](https://dl.acm.org/doi/10.1016/0167-6423(96)00012-3),
  and Keiko Nakata,
  [Denotational Semantics for Lazy Initialization of Letrec](https://cs.ioc.ee/~keiko/papers/fics10.pdf),
  for the sharing and black-hole semantics behind explicit laziness.
- Simon Peyton Jones,
  [Type-Directed Compilation in the Wild: Haskell and Core](https://link.springer.com/chapter/10.1007/978-3-642-38946-7_1),
  and Zhong Shao, Christopher League, and Stefan Monnier,
  [Implementing Typed Intermediate Languages](https://dl.acm.org/doi/10.1145/289423.289460),
  for the typed-Core and typed-IR lessons.

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
