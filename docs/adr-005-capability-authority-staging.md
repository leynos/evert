# Architectural decision record 005: Capability authority staging

## Status

Accepted for the initial design.

## Date

2026-06-27.

## Context and problem statement

Evert wants systems-language authority without making ownership or capability
machinery ambient in ordinary code. The language will need resources,
capabilities, handlers, structured concurrency, unsafe code, and host effects,
but the first interpreter slice should validate pure code, handlers, and
explicit laziness before it takes on authority-sensitive execution.

## Decision drivers

- Authority to perform host operations should be explicit and local.
- Resource values and authority values are related but not identical.
- Ordinary bindings should not carry affine or capability annotations unless
  the programme asks for that power.
- `Clock`, filesystem, network, and unsafe operations need capability
  semantics before they execute.
- Handlers must not become a back door for hidden authority.

## Options considered

| Option                                                | Strengths                                                     | Weaknesses                                                         |
| ----------------------------------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------ |
| Treat effects as sufficient authority                 | Keeps the model small                                         | Lets naming an operation imply permission to perform it            |
| Make Rust-style ownership ambient                     | Gives strong systems discipline                               | Pushes implementation machinery into ordinary Evert code           |
| Split resources from capabilities and stage execution | Preserves local authority and ordinary expression readability | Requires explicit later design work before host operations execute |

_Table 1: Capability and authority options._

## Decision outcome

Split resource values from authority capabilities and stage authority-sensitive
execution:

- A resource value models a value with linear or affine lifecycle obligations.
- A capability value grants authority to perform a class of host or unsafe
  operations.
- Handlers may provide or transform capabilities only through explicit source
  constructs and typed interfaces.
- `Clock` is not in the first executable effect set. It becomes the first
  staged non-deterministic capability effect after the authority model has
  conformance fixtures.
- Filesystem, network, unsafe, foreign-function, and richer resource effects
  remain specified but staged until an RFC or ADR defines authority passing,
  capture, and handler interaction.

## Consequences

- The first effect MVP narrows to `Throw<E>` and `Console`.
- Capability-bearing effects require negative fixtures for hidden authority,
  handler-provided authority, and capability escape.
- Structured concurrency and capabilities must be designed together where task
  scopes capture authority.
- The runtime can expose deterministic test hosts before exposing real host
  authority.

## References

- `docs/evert-design.md`.
- `docs/roadmap.md`.
- Gabriel Radanne, Hannes Saffrich, and Peter Thiemann, "Kindly Bent to Free
  Us", <https://arxiv.org/abs/1908.09681>.
- A. Laura Voinea, Ornela Dardha, and Simon J. Gay, "Resource Sharing via
  Capability-Based Multiparty Session Types",
  <http://eprints.gla.ac.uk/202623/>.
- Yi-An Chen and Yi-Ping You, "Structured Concurrency: A Review",
  <https://dl.acm.org/doi/10.1145/3547276.3548519>.
