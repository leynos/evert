# Architectural decision record 003: Local-power language semantics

## Status

Accepted for the initial design.

## Date

2026-06-27.

## Context and problem statement

Evert's product thesis is that powerful abstractions should be available
without becoming ambient defaults. The source material requires strict
evaluation by default, explicit laziness, `pure fn` as an enforceable contract,
typed effects and handlers, monads as ordinary abstractions, and checked local
mutation.

## Decision drivers

- Programmers should be able to identify the local construct that introduces
  power.
- Pure functions must be enforceable by the compiler, not documented by
  convention.
- Effects should be visible in function types without requiring monads for
  ordinary direct-style code.
- Effects and handlers should be validated before broader systems features
  create harder interaction cases.
- Lazy values must not hide effect timing.
- Local mutation should preserve external referential transparency when cells
  cannot escape.

## Options considered

| Option                                         | Strengths                                         | Weaknesses                                                             |
| ---------------------------------------------- | ------------------------------------------------- | ---------------------------------------------------------------------- |
| Haskell-like global laziness and `IO` boundary | Mature model with strong prior art                | Makes laziness and effect discipline pervasive defaults                |
| Rust-like explicit ownership everywhere        | Strong systems safety                             | Exposes too much implementation machinery in ordinary application code |
| Evert local-power rule                         | Makes each powerful feature opt-in and reviewable | Requires several interacting static checks                             |

_Table 1: Language-semantics options._

## Decision outcome

Adopt the local-power rule as a semantic invariant:

- `pure fn` requires an empty inferred effect row.
- Function arrows carry effect rows.
- Effects are performed in direct style and interpreted by handlers.
- Effects and handlers are the first hard local-power semantic surface after
  pure code.
- Monads remain available through traits and `do M { ... }`, but monads do not
  replace effect rows.
- `lazy` creates a pure memoized thunk and rejects effectful expressions.
- `mutate` regions can appear inside pure code only when region-local mutable
  cells cannot escape, but executable mutation may be staged after the first
  effect and laziness interpreter slice.
- Advanced ownership, concurrency, capabilities, and unsafe code are specified
  early but staged behind simpler MVP semantics.

## Consequences

- The type checker must solve type and effect constraints together.
- Polymorphic effects may later need signature restriction or effect-interface
  sealing if open effect interfaces leak abstraction.
- The interpreter must distinguish value-level failures, `Throw<E>`, handler
  resumption, and runtime panics.
- The runtime must model thunk states and black-hole detection.
- Conformance tests need negative fixtures for effect leakage, effectful
  laziness, escaping mutable cells, incoherent instances, and non-exhaustive
  matches.
- Verification targets include row soundness, handler preservation, effect
  capability non-escape, and heap independence for region-local cells.

## References

- `docs/context.md`.
- `docs/terms-of-reference.md`.
- Daan Leijen, "Koka: Programming with Row Polymorphic Effect Types",
  <https://arxiv.org/abs/1406.2061>.
- Daniel Hillerstrom and Sam Lindley, "Liberating Effects with Rows and
  Handlers", <https://dl.acm.org/doi/10.1145/2976022.2976033>.
- Gordon D. Plotkin and Matija Pretnar, "Handling Algebraic Effects",
  <https://arxiv.org/abs/1312.1399>.
- Taro Sekiyama, Takeshi Tsukada, and Atsushi Igarashi, "Signature Restriction
  for Polymorphic Algebraic Effects", <https://arxiv.org/abs/2003.08138>.
- Dariusz Biernacki, Maciej Pirog, Piotr Polesiuk, and Filip Sieczkowski,
  "Abstracting Algebraic Effects", <https://dl.acm.org/doi/10.1145/3290319>.
- John Launchbury and Simon L. Peyton Jones, "Lazy Functional State Threads",
  <https://www.microsoft.com/en-us/research/wp-content/uploads/1994/06/lazy-functional-state-threads.pdf>.
- Amin Timany, Leo Stefanesco, Morten Krogh-Jespersen, and Lars Birkedal, "A
  Logical Relation for Monadic Encapsulation of State",
  <https://dl.acm.org/doi/10.1145/3158152>.
