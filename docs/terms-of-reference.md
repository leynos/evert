# Evert terms of reference

- **Status:** Draft v0.1 with acknowledged open questions.
- **Audience:** Product sponsors, language designers, compiler implementers,
  tool authors, and reviewers evaluating Evert's scope.
- **Companion documents:** `docs/context.md`, `docs/evert-design.md`,
  `docs/roadmap.md`, `docs/adr-001-query-based-compiler-workspace.md`,
  `docs/adr-002-interpreter-first-backend-boundary.md`, and
  `docs/adr-003-local-power-language-semantics.md`,
  `docs/adr-004-effect-interface-sealing-gate.md`, and
  `docs/adr-005-capability-authority-staging.md`.
- **Last substantive revision:** 2026-06-27.

## 1. Background and motivation

Evert exists because several powerful programming-language ideas work well in
isolation but become costly when a language makes one of them ambient. The
inciting incident asks for "inside-out Haskell": monads, lazy evaluation,
referential transparency, pure functions, and algebraic data types, but only
where the programmer asks for them. The governing rule is therefore:

> Power should be local, explicit, and non-contagious.

The problem is timely because typed effects, algebraic handlers,
row-polymorphic effect systems, structured concurrency, lossless syntax trees,
and incremental compiler query engines now have credible prior art. Koka shows
that row-polymorphic effect types and automatic inference can coexist in a real
language. Unison demonstrates a user-facing effect model based on abilities.
Swift and OpenJDK have both moved structured concurrency into mainstream
language or platform design. Rust-hosted compiler infrastructure such as Salsa,
rowan, Logos, Chumsky, Ariadne, and Inkwell makes a reference compiler
plausible without first building every compiler subsystem from scratch.

Evert should not begin as a production language. It should begin as a
specification-backed reference compiler that proves the language's most
important promise: direct code can remain readable while purity, laziness,
effects, local mutation, and structured concurrency stay explicit and local.

## 2. Domain

Evert belongs to programming-language and compiler design. Its source material
is the ECLP corpus in `docs/references/inciting-incident.md` and the planning
analysis in `docs/references/evert-plan.md`.

The domain has several established conventions that matter for Evert:

- Functional languages commonly separate pure values from effectful actions,
  but many expose that separation through pervasive abstractions.
- Modern IDE-grade compilers keep syntax lossless and semantic-free, then
  lower into semantic representations for analysis.
- Incremental compilers model derived facts as deterministic computations over
  source inputs.
- Safe local mutation is possible when the type system prevents mutable state
  from escaping its region.
- Structured concurrency treats related child tasks as one unit of work rather
  than as detached handles.

Terms in this document use the definitions in `docs/context.md`.

## 3. Market context

Evert does not enter an empty space. It coexists with several alternatives:

| Alternative     | What users get today                                                        | Gap Evert addresses                                                                                                                         |
| --------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Haskell and GHC | Mature laziness, purity, algebraic data types, and monadic abstractions     | Laziness and effect machinery are global defaults rather than local opt-ins.                                                                |
| Rust            | Strong safety, ownership, tooling, and systems performance                  | Ordinary code can expose lifetime and ownership machinery that Evert wants to keep semantic and mostly implicit.                            |
| Koka            | Effect types, handlers, row polymorphism, and research-grade implementation | Evert uses Koka as proof that effect rows are practical, but chooses a strict-by-default systems-language shape and a Rust-hosted compiler. |
| Unison          | Abilities as a user-facing algebraic effect model and advanced tooling      | Evert keeps the direct-style effect idea but is not content-addressed and does not adopt Unison's whole project model.                      |
| Swift and Java  | Increasingly mainstream structured concurrency                              | Evert bakes task scope, cancellation, and ownership into the language rather than exposing them only as library or platform APIs.           |
| Go              | Simple lightweight concurrency and channels                                 | Evert rejects unstructured detached tasks as the default concurrency model.                                                                 |

_Table 1: Prior-art position and Evert's intended gap._

The current default for a language implementer is to prototype a compiler,
write notes that drift from the implementation, and discover semantic
contradictions only after code generation starts. Evert's counter-position is
to keep the ECLP corpus, executable conformance tests, and Core interpreter in
lockstep before native backend work.

## 4. Users and stakeholders

| Type                                  | Context                                                                | Cares about                                                                                                | Will ignore or dislike                                               | Current alternative                                    |
| ------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | ------------------------------------------------------ |
| Primary user: compiler implementer    | Maintains the Rust reference compiler and ECLP corpus                  | Clear invariants, staged implementation, deterministic tests, and inspectable intermediate representations | Broad language claims without executable evidence                    | Ad hoc compiler prototypes and standalone design notes |
| Primary user: language designer       | Shapes ECLPs and reviews semantic trade-offs                           | Locality of power, consistency, and explicit non-goals                                                     | Accidental feature accumulation                                      | Haskell, Koka, Rust, Swift, Go, and research papers    |
| Secondary user: Evert programmer      | Eventually writes `.evt` programmes                                    | Direct code, clear diagnostics, local opt-in features, and predictable effects                             | Needing to understand compiler internals for normal application work | Haskell, Rust, Koka, Unison, Swift, Go                 |
| Secondary user: tooling author        | Builds formatters, editor features, and future language-server support | Lossless syntax, stable spans, query APIs, and machine-readable diagnostics                                | Syntax trees that discard trivia or diagnostics with unstable shape  | rust-analyzer-style infrastructure                     |
| Stakeholder: project maintainer       | Keeps the repository healthy                                           | Gated commits, current documentation, and reviewable roadmap slices                                        | Untested or undocumented broad rewrites                              | Generated Rust project scaffold                        |
| Non-user: production application team | Wants a stable, supported language today                               | Release maturity and ecosystem availability                                                                | Research-stage semantics and missing package registry                | Existing production languages                          |

_Table 2: Stakeholder mapping._

## 5. Job to be done

When a compiler implementer is turning a broad language concept into a working
reference compiler, they want a staged specification, architecture, and
roadmap, so they can build one falsifiable semantic slice at a time.

When a language designer evaluates a new feature, they want that feature tied
to Evert's local-power rule and to explicit non-goals, so they can reject
contagious abstractions before they reach implementation.

When an eventual Evert programmer writes ordinary code, they want functional
and systems features to appear only where requested, so they can use purity,
laziness, monads, effects, mutation, and concurrency without reorganizing the
whole programme around one abstraction.

## 6. Scope

### 6.1. Goals

- Produce a normative ECLP corpus and keep it linked to executable
  conformance tests.
- Build a Rust-hosted reference compiler with a lossless front end,
  query-based semantic analysis, typed Core IR, and interpreter-first execution.
- Enforce the first semantic invariants: empty effect rows for `pure fn`,
  pure-only laziness, row soundness for `Throw<E>` and `Console`, exhaustive
  closed-pattern matching, coherent trait instances, and non-escaping local
  mutation.
- Deliver human-first diagnostics as a language feature, not as an afterthought.
- Keep native code generation behind a narrow backend boundary until the
  interpreter has become the semantic oracle.
- Specify advanced concurrency, ownership, capabilities, unsafe code, editions,
  and metaprogramming before implementing their full runtime behaviour.

### 6.2. Non-goals

- Evert v1 is not a production application language.
- The MVP will not ship a native LLVM object backend as a required build path.
- The MVP will not include a package registry, hosted service, graphical user
  interface, or language-server binary.
- The MVP will not execute the full structured-concurrency, actor, protocol,
  capability-security, unsafe foreign-function interface, or metaprogramming
  surface.
- Evert will not add subtyping, type-level computation, or quantum-computing
  primitives in version one.
- Evert will not treat monads as the only effect mechanism or laziness as the
  default evaluation strategy.

## 7. Success criteria

User-facing success means a contributor can run one command that checks a
representative `.evt` programme, receives diagnostics that refer to source
constructs, and can trace the result through CST, HIR, Core, and interpreter
output without reading backend code.

Operational success means `make fmt`, `make nixie`, the Rust format and lint
gates, conformance tests, diagnostic snapshots, and interpreter golden tests
run deterministically on a checkout without LLVM installed.

Strategic success means the ECLP corpus and implementation reinforce one
another: every implemented language feature has an ECLP, every MVP ECLP has
conformance evidence, and every deferred feature is still represented by a
clear parser/specification boundary.

## 8. Constraints and assumptions

### 8.1. Hard constraints

- The implementation language is Rust.
- The compiler stack uses Logos, a layout pass, Chumsky, Salsa, typed Core IR,
  and an LLVM backend boundary.
- The interpreter precedes native backend execution.
- Durable query data must not borrow lexer input or hold LLVM objects.
- Documentation follows `docs/documentation-style-guide.md`.
- The repository's gates use Make targets and must leave `make fmt` and
  `make nixie` green for this design work.

### 8.2. Assumptions

- The primary near-term audience is the compiler implementer, not a production
  application developer. If that fails, the roadmap will over-prioritize
  conformance infrastructure and under-prioritize tutorials.
- The ECLP corpus in `docs/references/inciting-incident.md` is authoritative
  enough to split into individual proposal documents. If it is not, an ECLP
  ratification pass must precede implementation.
- One-shot effect handlers are sufficient for the interpreter MVP. If users
  need multi-shot handlers early, Core lowering and runtime frame ownership
  become more complex.
- The front end and interpreter can remain useful without LLVM. If not, LLVM
  installation becomes a day-one onboarding dependency and narrows adoption.
- The Rust ecosystem versions available during implementation remain
  compatible with the pinned toolchain. If not, the dependency decision needs a
  fresh ADR.

### 8.3. Dependencies

- Official crate APIs for Logos, Chumsky, Ariadne, Salsa, and Inkwell.
- LLVM tooling for deferred textual and embedded backend work.
- The ECLP source material in `docs/references/inciting-incident.md`.
- The repository's generated Rust workflow and Make targets.

## 9. Open questions

| Question                                                                       | Why it matters                                                                                                    | Resolution criteria                                                                                                               | Suggested path                                                                     |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Which ECLPs are accepted, draft, or deferred after the first split?            | The roadmap depends on the MVP specification boundary.                                                            | Each ECLP file has a status, dependencies, and a conformance expectation.                                                         | Split and review the corpus before implementing language features.                 |
| When does `Clock` enter the executable effect set?                             | Time introduces non-determinism and capability authority earlier than the first semantic proof needs it.          | ADR 005's authority model has fixtures for hidden authority, handler-provided authority, and deterministic test hosts.            | Keep the first executable effect set to `Throw<E>` and `Console`.                  |
| Do polymorphic effects need signature restriction or effect-interface sealing? | Open effect interfaces can make abstraction leaks hard to diagnose.                                               | Row soundness and capability non-escape tests either pass without a restriction or an ADR introduces one.                         | Use ADR 004 as the early gate before broadening effect polymorphism.               |
| Does executable local mutation belong in the first interpreter release?        | ST-style mutation is central but proof-heavy, and effects plus laziness already validate the first semantic loop. | The roadmap either accepts an executable `mutate` slice with heap-independence tests or defers it with static rejection fixtures. | Stage after handlers and pure laziness unless an ECLP example requires it earlier. |
| Which LLVM major version should the optional backend target?                   | Inkwell feature flags and CI images depend on one LLVM major.                                                     | One ADR pins the major and explains local installation expectations.                                                              | Defer until textual Core and interpreter tests are stable.                         |
| What package manifest shape does Evert use?                                    | CLI commands, editions, module resolution, and project tests depend on it.                                        | A minimal manifest schema is documented and covered by parser tests.                                                              | Design after module resolution but before `evert build`.                           |
| What memory-management model ships after the interpreter MVP?                  | Thunks, closures, resources, and backend interoperability depend on it.                                           | The runtime design chooses between reference counting, tracing, or a staged hybrid.                                               | Spike after lazy values and interpreter values exist.                              |
| How far should structured concurrency go before v1?                            | It is central to the language thesis but expensive to implement.                                                  | The parser/spec/runtime split for nurseries, channels, actors, and protocols is explicit.                                         | Keep parser and specification coverage early; defer full execution.                |

_Table 3: Open questions for the next design iteration._

## References

- `docs/references/inciting-incident.md`.
- `docs/references/evert-plan.md`.
- Salsa overview, <https://salsa-rs.github.io/salsa/overview.html>, accessed
  2026-06-27.
- rust-analyzer syntax guide,
  <https://github.com/rust-lang/rust-analyzer/blob/master/docs/book/src/contributing/syntax.md>,
  accessed 2026-06-27.
- Koka language site, <https://koka-lang.github.io/>, accessed 2026-06-27.
- Daan Leijen, "Koka: Programming with Row Polymorphic Effect Types",
  <https://arxiv.org/abs/1406.2061>, accessed 2026-06-27.
- Daan Leijen, "Algebraic Effects for Functional Programming",
  <https://www.microsoft.com/en-us/research/wp-content/uploads/2016/08/algeff-tr-2016-v3.pdf>,
  accessed 2026-06-27.
- Daniel Hillerstrom and Sam Lindley, "Liberating Effects with Rows and
  Handlers", <https://dl.acm.org/doi/10.1145/2976022.2976033>, accessed
  2026-06-27.
- Gordon D. Plotkin and Matija Pretnar, "Handling Algebraic Effects",
  <https://arxiv.org/abs/1312.1399>, accessed 2026-06-27.
- Taro Sekiyama, Takeshi Tsukada, and Atsushi Igarashi, "Signature Restriction
  for Polymorphic Algebraic Effects", <https://arxiv.org/abs/2003.08138>,
  accessed 2026-06-27.
- John Launchbury and Simon L. Peyton Jones, "Lazy Functional State Threads",
  <https://www.microsoft.com/en-us/research/wp-content/uploads/1994/06/lazy-functional-state-threads.pdf>,
  accessed 2026-06-27.
- Amin Timany, Leo Stefanesco, Morten Krogh-Jespersen, and Lars Birkedal, "A
  Logical Relation for Monadic Encapsulation of State",
  <https://dl.acm.org/doi/10.1145/3158152>, accessed 2026-06-27.
- Swift Evolution SE-0304 structured concurrency proposal,
  <https://github.com/swiftlang/swift-evolution/blob/main/proposals/0304-structured-concurrency.md>,
  accessed 2026-06-27.
- OpenJDK JEP 505, "Structured Concurrency (Fifth Preview)",
  <https://openjdk.org/jeps/505>, accessed 2026-06-27.
- Yi-An Chen and Yi-Ping You, "Structured Concurrency: A Review",
  <https://dl.acm.org/doi/10.1145/3547276.3548519>, accessed 2026-06-27.
- Gabriel Radanne, Hannes Saffrich, and Peter Thiemann, "Kindly Bent to Free
  Us", <https://arxiv.org/abs/1908.09681>, accessed 2026-06-27.
- A. Laura Voinea, Ornela Dardha, and Simon J. Gay, "Resource Sharing via
  Capability-Based Multiparty Session Types",
  <http://eprints.gla.ac.uk/202623/>, accessed 2026-06-27.
