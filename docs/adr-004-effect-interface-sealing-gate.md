# Architectural decision record 004: Effect-interface sealing gate

## Status

Accepted for the initial design.

## Date

2026-06-27.

## Context and problem statement

Evert's first semantic promise depends on row-polymorphic effect inference and
direct-style handlers. The literature supports this direction, but unrestricted
polymorphic effects are also where type safety and abstraction can leak. The
first implementation should not add a full sealing mechanism before it has real
row-polymorphic fixtures, but it must not treat sealing as late cleanup.

## Decision drivers

- `pure fn` and explicit effect rows must remain enforceable as the effect
  surface grows.
- Effect interfaces should not accidentally export authority or abstraction
  details through polymorphic operation signatures.
- The first effect implementation should stay narrow enough to validate
  inference and handlers before solving every advanced effect-interface problem.
- The roadmap needs a hard gate before Evert leaves the initial effect phase.

## Options considered

| Option                                               | Strengths                                                                    | Weaknesses                                               |
| ---------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------- |
| Implement signature restriction in the first checker | Addresses known polymorphic-effect risk early                                | Adds mechanism before Evert has its own failing fixtures |
| Defer sealing until after broad effect support       | Keeps the first checker simpler                                              | Lets abstraction leaks become baked into public examples |
| Add an early effect-interface sealing gate           | Keeps the first slice small while forcing the decision before effect breadth | Requires the roadmap to treat the gate as a blocker      |

_Table 1: Effect-interface sealing options._

## Decision outcome

Add an early effect-interface sealing gate:

- The first executable effect set is `Throw<E>` and `Console`.
- `Clock` is specified but staged until the capability/authority model is
  accepted.
- The first row-polymorphic checker may start without signature restriction.
- Before adding open polymorphic operation interfaces, capability-bearing
  effects, or broader handler libraries, Evert must either prove the current
  interface model safe through conformance fixtures or accept a follow-up ADR
  that introduces signature restriction or effect-interface sealing.
- Effect-interface metadata must be represented explicitly enough that sealing
  can be added without replacing the type/effect architecture.

## Consequences

- Roadmap tasks that broaden effects depend on the sealing gate.
- The type checker needs negative fixtures for effect-capability non-escape,
  not only happy-path row inference.
- `Clock` no longer belongs in the first executable effect slice.
- Diagnostics should name effect interfaces and operations so later sealing
  errors can be actionable.

## References

- `docs/evert-design.md`.
- `docs/roadmap.md`.
- Daniel Hillerstrom and Sam Lindley, "Liberating Effects with Rows and
  Handlers", <https://dl.acm.org/doi/abs/10.1145/2976022.2976033>.
- Daan Leijen, "Algebraic Effects for Functional Programming",
  <https://www.microsoft.com/en-us/research/wp-content/uploads/2016/08/algeff-tr-2016-v3.pdf>.
- Taro Sekiyama, Takeshi Tsukada, and Atsushi Igarashi, "Signature Restriction
  for Polymorphic Algebraic Effects", <https://arxiv.org/abs/2003.08138>.
- Dariusz Biernacki, Maciej Pirog, Piotr Polesiuk, and Filip Sieczkowski,
  "Abstracting Algebraic Effects", <https://dl.acm.org/doi/10.1145/3290319>.
