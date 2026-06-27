# Repository layout

This document describes the Evert repository layout. It is the canonical
reference for where source code, tests, configuration, automation, and
long-lived documentation belong.

## Top-level tree

The tree below shows the current repository structure. It is intentionally
compact and omits build output such as `target/`.

```plaintext
.
├── .cargo/
│   └── config.toml
├── .github/
│   ├── dependabot.yml
│   └── workflows/
│       ├── act-validation.yml
│       ├── ci.yml
│       └── release.yml
├── docs/
│   ├── adr-001-query-based-compiler-workspace.md
│   ├── adr-002-interpreter-first-backend-boundary.md
│   ├── adr-003-local-power-language-semantics.md
│   ├── adr-004-effect-interface-sealing-gate.md
│   ├── adr-005-capability-authority-staging.md
│   ├── contents.md
│   ├── context.md
│   ├── developers-guide.md
│   ├── evert-design.md
│   ├── references/
│   ├── repository-layout.md
│   ├── roadmap.md
│   ├── terms-of-reference.md
│   ├── users-guide.md
│   └── ...
├── src/
│   ├── lib.rs
│   └── main.rs
├── tests/
│   └── stub.rs
├── AGENTS.md
├── Cargo.toml
├── LICENSE
├── Makefile
├── README.md
├── clippy.toml
├── codecov.yml
└── rust-toolchain.toml
```

## Path responsibilities

- `.cargo/config.toml`: Configures Cargo defaults for local development,
  including Linux linker and code-generation settings.
- `.github/dependabot.yml`: Configures automated dependency update checks.
- `.github/workflows/act-validation.yml`: Runs the generated workflow
  validation through `act` separately from main CI.
- `.github/workflows/ci.yml`: Runs the generated project's continuous
  integration checks.
- `.github/workflows/release.yml`: Builds and publishes binary release
  artefacts for the application flavour.
- `docs/`: Holds long-lived reference documentation, guides, style rules, and
  design material.
- `docs/adr-*.md`: Holds accepted architecture decisions that constrain the
  design and roadmap.
- `docs/contents.md`: Indexes the documentation set and should be updated when
  documentation files are added, renamed, or removed.
- `docs/context.md`: Defines shared Evert language, compiler, and architecture
  terms.
- `docs/developers-guide.md`: Explains the contributor workflow and local
  tooling used to work on Evert.
- `docs/evert-design.md`: Defines the initial Evert language and compiler
  architecture.
- `docs/references/`: Preserves source planning material that informed the
  design but is not itself normative.
- `docs/repository-layout.md`: Documents the repository tree and path
  responsibilities.
- `docs/roadmap.md`: Sequences design and implementation work into testable
  phases, steps, and tasks.
- `docs/terms-of-reference.md`: Records the problem space, scope, constraints,
  and success criteria.
- `docs/users-guide.md`: Explains Evert's current user-facing state and public
  build and validation commands.
- `src/lib.rs`: Contains library support for application logic and doctested
  examples.
- `src/main.rs`: Contains the application entrypoint and top-level executable
  wiring.
- `tests/`: Holds integration and behavioural tests that exercise public
  behaviour.
- `tests/stub.rs`: Keeps the generated test directory valid until real tests
  replace it.
- `AGENTS.md`: Provides repository-specific working instructions for agents and
  contributors.
- `Cargo.toml`: Defines package metadata, dependencies, lint policy, and Cargo
  configuration.
- `LICENSE`: Records the project licence text.
- `Makefile`: Provides the public build, lint, test, coverage, and
  documentation validation commands.
- `README.md`: Introduces Evert as a research project, links the design spine,
  and gives visitors the shortest useful orientation path.
- `clippy.toml`: Configures Clippy lint behaviour that is not expressed
  directly in `Cargo.toml`.
- `codecov.yml`: Configures coverage reporting behaviour.
- `rust-toolchain.toml`: Pins the Rust toolchain channel and required
  components.

## Ownership boundaries

- Keep generated source code under `src/`. Add modules below `src/` when a
  feature grows beyond a small entrypoint or crate root.
- Keep black-box integration tests and externally observable workflow tests
  under `tests/`.
- Keep reusable documentation under `docs/`. Update `docs/contents.md` whenever
  a documentation file is added, renamed, or removed.
- Keep build and validation entrypoints in `Makefile`; prefer adding or
  extending a Make target over documenting an ad hoc command.
- Keep continuous integration workflow changes under `.github/workflows/` and
  dependency-update policy under `.github/dependabot.yml`.
- Do not commit generated build output such as `target/`, coverage artefacts,
  or local editor state.

## Updating this document

Update this document when the repository gains a new top-level directory, a new
long-lived documentation category, a new workflow file, or a changed ownership
boundary that would otherwise make the tree misleading.
