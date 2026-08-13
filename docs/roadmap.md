# Evert roadmap

This roadmap translates `docs/terms-of-reference.md`, `docs/evert-design.md`,
and the accepted initial ADRs into an outcome-oriented delivery sequence. It
does not promise dates. Each phase carries one testable idea. Steps work toward
validating or falsifying that idea, and tasks are review-sized execution units
with design citations.

The roadmap assumes the GIST hierarchy: phases are ideas, steps are
workstreams, and tasks are concrete units of work. Unit and behavioural tests
belong inside implementation tasks; end-to-end, conformance, and combinatorial
suites are first-class tasks when they validate a product surface or feature
interaction.

## 1. Foundational contracts and build spine

Idea: if Evert settles the ECLP boundary, crate architecture, and first
conformance harness before feature work starts, later slices can validate
language semantics without repeatedly reworking contracts.

This phase turns the generated repository into a compiler project without yet
building a broad language surface. It validates the documentation and build
spine that all later slices depend on.

### 1.1. Ratify the initial language and architecture contracts

This step answers which documents are normative for the first implementation.
Its outcome informs crate creation, ECLP splitting, conformance fixtures, and
backend deferral. See `docs/evert-design.md` §§1-3 and
`docs/terms-of-reference.md` §§6-9.

- [ ] 1.1.1. Split the ECLP source material into `docs/eclp/` proposal files.
  - Preserve the source wording from `docs/references/inciting-incident.md`.
  - Add status, layer, dependencies, examples, and open questions to each
    proposal.
  - Success: every MVP feature in `docs/evert-design.md` has an ECLP file and
    every deferred ECLP is marked as deferred or staged.
- [ ] 1.1.2. Add ADRs for the MVP effect set and package manifest boundary.
  - Requires 1.1.1.
  - See `docs/evert-design.md` §§8 and 12,
    `docs/adr-004-effect-interface-sealing-gate.md`, and
    `docs/adr-005-capability-authority-staging.md`.
  - Success: the first semantic slice knows that `Throw<E>` and `Console` are
    executable, `Clock` is staged, and the manifest fields it must parse and
    check are documented.
- [ ] 1.1.3. Decide the first crate set and workspace metadata.
  - Requires 1.1.1 and `docs/adr-001-query-based-compiler-workspace.md`.
  - Create only crates needed by phases 2 and 3.
  - Success: workspace boundaries match implemented responsibilities, not empty
    architectural placeholders.

### 1.2. Establish conformance fixtures before compiler breadth

This step answers how Evert will know that an implemented feature satisfies the
ECLPs. It unlocks every later semantic task. See `docs/evert-design.md` §13.

- [ ] 1.2.1. Create the conformance fixture layout.
  - Requires 1.1.1.
  - Include accepted, rejected, diagnostic, and interpreter-output fixtures.
  - Success: a contributor can add one fixture and state the ECLP property it
    covers.
- [ ] 1.2.2. Add snapshot and semantic assertion helpers for diagnostics and
  Core text.
  - Requires 1.2.1.
  - Success: diagnostics snapshots cannot pass without matching source spans
    and diagnostic codes.
- [ ] 1.2.3. Add the first end-to-end generated-project gate for Evert
  examples.
  - Requires 1.2.1.
  - Success: the repository can run one command that exercises example files
    through the currently implemented stages.

## 2. Vertical slice 1: Lossless front end with useful diagnostics

Idea: if the first vertical slice can tokenize, layout-expand, parse, and
recover from real Evert examples while preserving source fidelity, Evert has a
credible foundation for diagnostics, formatting, and editor tooling before
semantic complexity lands.

This phase delivers source ingestion through CST and diagnostic rendering. It
does not type-check programmes yet.

### 2.1. Prove the token and layout contracts

This step answers whether Evert can preserve source text while normalizing
layout. It informs parser design and formatter feasibility. See
`docs/evert-design.md` §§6-7.

- [ ] 2.1.1. Implement `FileId`, `Span`, source maps, and interned `Symbol`
  values.
  - Requires 1.1.3.
  - See `docs/evert-design.md` §5.
  - Success: spans map from byte offsets to user-facing locations across
    multiline fixtures.
- [ ] 2.1.2. Implement the Logos token model for ECLP-0002.
  - Requires 2.1.1.
  - Include trivia retention and token errors.
  - Success: accepted lexical fixtures round-trip token text and rejected
    fixtures produce source-anchored diagnostics.
- [ ] 2.1.3. Implement layout expansion.
  - Requires 2.1.2.
  - Cover braces, layout blocks, mixed forms, empty blocks, and recovery after
    malformed indentation.
  - Success: layout-expanded token streams are deterministic and preserve
    enough trivia for formatting.
- [ ] 2.1.4. Add property-based lexer and layout round-trip coverage.
  - Requires 2.1.3.
  - Success: generated whitespace and comment variations do not change
    non-trivia token order or span mapping.

### 2.2. Deliver a recovering CST parser

This step answers whether Evert can parse incomplete programmes without losing
the user's source structure. It unlocks diagnostics, formatting, and semantic
lowering. See `docs/evert-design.md` §7.

- [ ] 2.2.1. Implement the Chumsky parser for modules, imports, data, records,
  functions, expressions, patterns, and effects.
  - Requires 2.1.3.
  - Success: the canonical examples from the inciting incident parse into a
    lossless CST.
- [ ] 2.2.2. Add parser recovery cuts for declaration, parameter, expression,
  and block errors.
  - Requires 2.2.1.
  - Success: malformed fixtures produce multiple diagnostics and a partial CST
    rather than aborting at the first error.
- [ ] 2.2.3. Add `evert dump tokens` and `evert dump cst`.
  - Requires 2.2.1.
  - See `docs/evert-design.md` §12.
  - Success: users can inspect token and CST output for one file through the
    command-line adapter.
- [ ] 2.2.4. Implement the first diagnostic renderer.
  - Requires 2.2.2.
  - See `docs/evert-design.md` §§7 and 11.
  - Success: diagnostics name source constructs and match snapshot fixtures.

## 3. Vertical slice 2: Names, types, effects, and pure code

Idea: if Evert can resolve names and enforce the first static invariants over
small programmes, the language thesis becomes testable before the interpreter
executes complex runtime behaviour.

This phase turns parsed source into HIR and typed bodies. It proves `pure fn`
as a compiler contract.

### 3.1. Establish HIR and stable identifiers

This step answers whether source modules can lower into a stable semantic
representation without carrying syntax-tree lifetimes into the query database.
See `docs/evert-design.md` §§5-6.

- [ ] 3.1.1. Implement item trees, module scopes, and stable `DefId`
  assignment.
  - Requires phase 2.
  - Success: reordering unrelated declarations preserves stable identifiers
    where names and ownership do not change.
- [ ] 3.1.2. Lower AST views into HIR for modules, data, records, functions,
  patterns, and effects.
  - Requires 3.1.1.
  - Success: HIR contains owned spans, identifiers, and symbols, but no borrowed
    source slices.
- [ ] 3.1.3. Add name-resolution diagnostics for missing, ambiguous, and
  private names.
  - Requires 3.1.2.
  - Success: diagnostics point to user names and suggest in-scope candidates
    where available.

### 3.2. Prove the first type and effect invariants

This step answers whether type inference, effect rows, and source-level purity
can coexist in the MVP. See `docs/evert-design.md` §8.

- [ ] 3.2.1. Implement kind and type inference for first-order functions,
  algebraic data types, records, and pattern matching.
  - Requires 3.1.2.
  - Success: accepted fixtures infer private signatures and require public
    signatures.
- [ ] 3.2.2. Implement effect-row inference for `Throw<E>` and `Console`.
  - Requires 3.2.1 and 1.1.2.
  - Success: inferred effect rows appear in diagnostics and dump output.
- [ ] 3.2.3. Enforce `pure fn` empty effect rows.
  - Requires 3.2.2.
  - Success: effectful calls inside `pure fn` are rejected with actionable
    diagnostics.
- [ ] 3.2.4. Add closed-pattern exhaustiveness checking.
  - Requires 3.2.1.
  - Success: non-exhaustive matches over closed ADTs fail with missing-shape
    diagnostics.
- [ ] 3.2.5. Add trait coherence checks for the first `Show`, `Eq`, `Functor`,
  and `Monad` traits.
  - Requires 3.2.1.
  - Success: orphan and overlapping instances fail before lowering.
- [ ] 3.2.6. Add a design checkpoint for effect-interface sealing.
  - Requires 3.2.2.
  - See `docs/evert-design.md` §8 and
    `docs/adr-004-effect-interface-sealing-gate.md`.
  - Success: row-polymorphic fixtures either demonstrate that the current
    effect-interface model is safe enough for the next slice or open a
    follow-up ADR for signature restriction.

## 4. Vertical slice 3: Core interpreter as semantic oracle

Idea: if typed programmes lower to deterministic Core and execute through an
interpreter, Evert can validate semantics independently of native backend work.

This phase delivers the first executable language subset: ADTs, pure functions,
`Option`, `Result`, `do`, basic handlers, pure laziness, and a decision gate
for executable local mutation.

### 4.1. Define and lower the typed Core

This step answers whether the semantic subset has one executable IR rather than
many feature-specific paths. See `docs/evert-design.md` §§9-10.

- [ ] 4.1.1. Implement Core forms for variables, lets, lambdas, applies,
  constructors, records, projection, update, and match.
  - Requires phase 3.
  - Success: Core pretty-printing is deterministic across representative
    fixtures.
- [ ] 4.1.2. Lower HIR typed bodies into Core.
  - Requires 4.1.1.
  - Success: accepted pure programmes lower without losing diagnostic source
    provenance.
- [ ] 4.1.3. Add `evert dump core`.
  - Requires 4.1.2.
  - Success: reviewers can inspect Core for every accepted MVP fixture.
- [ ] 4.1.4. Add the typed-Core size budget.
  - Requires 4.1.2.
  - See `docs/evert-design.md` §§9 and 13.
  - Success: representative fixtures report Core node counts and
    type-annotation growth, and unexpected growth fails review before backend
    work begins.

### 4.2. Execute pure and data-level programmes

This step answers whether the interpreter can act as the semantic oracle for
pure code before effects and mutation arrive. See `docs/evert-design.md` §10.

- [ ] 4.2.1. Implement runtime values and interpreter evaluation for pure Core.
  - Requires 4.1.2.
  - Success: examples covering ADTs, records, pattern matches, and pure
    functions produce golden outputs.
- [ ] 4.2.2. Add `Option`, `Result`, `Functor`, `Applicative`, `Monad`, and
  `do` lowering.
  - Requires 4.2.1 and 3.2.5.
  - Success: `do Option` and `do Result` examples execute through trait
    dictionaries, not through the effect system.
- [ ] 4.2.3. Add interpreter oracle fixtures for the ECLP examples.
  - Requires 4.2.2.
  - Success: every executable MVP example has an expected interpreter result.

### 4.3. Add local power features to the interpreter

This step answers whether Evert can implement local power without making it
ambient. See `docs/evert-design.md` §§8-10.

- [ ] 4.3.1. Implement basic `Throw<E>` and `Console` handlers.
  - Requires 4.2.1 and 3.2.2.
  - Success: direct-style effect examples execute through handlers and
    unhandled effects remain visible in the effect row.
- [ ] 4.3.2. Implement pure lazy thunks with memoization and black-hole
  detection.
  - Requires 4.2.1.
  - Success: pure lazy stream examples execute, effectful lazy expressions
    fail statically, and recursive forcing reports a black-hole diagnostic.
- [ ] 4.3.3. Decide the executable local-mutation gate.
  - Requires 4.3.1, 4.3.2, and the accepted ECLP split.
  - See `docs/evert-design.md` §8.4.
  - Success: the roadmap either accepts an executable `mutate` implementation
    task with heap-independence tests or defers execution while keeping
    parser, semantic rejection, and escaping-cell fixtures.
- [ ] 4.3.4. Add E2E CLI coverage for `evert check`, `evert run`, and
  `evert dump core`.
  - Requires 4.3.1-4.3.3.
  - Success: one command validates the complete parser-to-interpreter loop for
    representative examples.

## 5. Vertical slice 4: Tooling surface and package workflow

Idea: if the interpreter-backed compiler can operate on a small package rather
than one isolated file, Evert becomes a usable development loop without native
code generation.

This phase turns the semantic oracle into a day-one user workflow.

### 5.1. Deliver the minimal package and edition model

This step answers how source files become a coherent package. See
`docs/evert-design.md` §§12 and 16.

- [ ] 5.1.1. Implement the accepted package manifest schema.
  - Requires 1.1.2 and phase 4.
  - Success: the driver loads package name, edition, source roots, and entry
    point from a documented manifest.
- [ ] 5.1.2. Implement module resolution across a package.
  - Requires 5.1.1 and 3.1.1.
  - Success: multi-file examples resolve explicit imports without import-time
    execution.
- [ ] 5.1.3. Add edition parsing and compatibility diagnostics.
  - Requires 5.1.1.
  - Success: unsupported or missing editions produce stable diagnostics.

### 5.2. Make formatting and diagnostics useful on real files

This step answers whether the lossless CST pays off in day-to-day tooling. See
`docs/evert-design.md` §§7 and 12.

- [ ] 5.2.1. Implement `evert fmt` for the accepted syntax subset.
  - Requires phase 2.
  - Success: formatting preserves comments, source spans, and semantic token
    order across representative fixtures.
- [ ] 5.2.2. Add machine-readable diagnostic JSON.
  - Requires 2.2.4.
  - Success: JSON diagnostics include code, severity, message, file, byte span,
    and labels.
- [ ] 5.2.3. Add package-level E2E and combinatorial command coverage.
  - Requires 5.1.2, 5.2.1, and 5.2.2.
  - Cover `check`, `run`, `fmt`, and `dump` combinations over single-file and
    package inputs.
  - Success: command combinations do not silently change output format,
    diagnostics, or exit-code policy.

## 6. Deferred extensions after the core v1 promise

Idea: if the core interpreter-backed language is already trustworthy, Evert can
evaluate advanced systems features on their product value instead of letting
them destabilize the MVP.

This phase collects specified-but-staged work from the design. Items can move
earlier only through an ADR or RFC that explains the new dependency.

### 6.1. Native backend and runtime evolution

- [ ] 6.1.1. Pin the LLVM major version and Inkwell feature in an ADR.
  - Requires phase 4.
  - See `docs/adr-002-interpreter-first-backend-boundary.md`.
  - Success: local and CI installation expectations are explicit.
- [ ] 6.1.2. Implement textual LLVM IR golden generation.
  - Requires 6.1.1 and phase 4.
  - Success: textual IR fixtures correspond to interpreter-validated Core.
- [ ] 6.1.3. Implement differential interpreter/backend conformance tests.
  - Requires 6.1.2.
  - Success: native backend results match interpreter results for the supported
    subset.

### 6.2. Structured concurrency and ownership

- [ ] 6.2.1. Accept an RFC for nurseries, task cancellation, and `Task<T, E>`.
  - Requires phase 4.
  - See `docs/evert-design.md` §§8 and 16.
  - Success: the RFC states static capture rules, cancellation propagation, and
    interpreter/runtime staging.
- [ ] 6.2.2. Accept an RFC for channels, actors, protocols, and reentrancy.
  - Requires 6.2.1.
  - Success: actor state isolation and protocol sendability are defined before
    runtime work begins.
- [ ] 6.2.3. Add model-checking or state-machine verification for task-scope
  cancellation.
  - Requires 6.2.1.
  - Success: no child task can outlive its nursery in the model.

### 6.3. Local mutation, capabilities, unsafe code, and metaprogramming

- [ ] 6.3.1. Implement or formally defer executable local mutation.
  - Requires 4.3.3.
  - Success: `mutate` either executes with non-escape and heap-independence
    evidence, or the deferred ECLP states the remaining proof and runtime work.
- [ ] 6.3.2. Accept an RFC for capability values, `Clock`, and
  handler-provided authority.
  - Requires phase 4.
  - See `docs/adr-005-capability-authority-staging.md`.
  - Success: filesystem, network, clock, and unsafe authority cannot be
    performed by naming a type alone.
- [ ] 6.3.3. Accept an RFC for unsafe blocks and foreign-function interfaces.
  - Requires 6.3.2.
  - Success: unsafe contracts state aliasing, lifetime, layout, and threading
    obligations before safe wrappers are accepted.
- [ ] 6.3.4. Accept an RFC for typed metaprogramming.
  - Requires phase 5.
  - Success: macros operate on typed syntax with spans and hygiene rather than
    raw token strings.
