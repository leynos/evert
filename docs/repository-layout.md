# Repository layout

This document describes the generated Evert repository layout. It is the
canonical reference for where source code, tests, configuration, automation,
and long-lived documentation belong.

## Top-level tree

The tree below shows the generated repository structure. It is intentionally
compact and omits build output such as `target/`.

```plaintext
.
├── .cargo/
│   └── config.toml
├── .github/
│   ├── cv005.toml
│   ├── dependabot.yml
│   └── workflows/
│       ├── act-validation.yml
│       ├── audit.yml
│       ├── ci.yml
│       ├── coverage-main.yml
│       ├── dependabot-automerge.yml
│       ├── mutation-testing.yml
│       └── release.yml
├── docs/
│   ├── contents.md
│   ├── debugging/
│   │   └── debugging-plan-2026-09-29-cranelift-unwind-test-abort.md
│   ├── developers-guide.md
│   ├── repository-layout.md
│   ├── users-guide.md
│   └── ...
├── scripts/
│   ├── build-tools-common.sh
│   ├── check-build-tools.sh
│   ├── clang-linker.sh
│   └── install-build-tools.sh
├── src/
│   ├── lib.rs
│   └── main.rs
├── tests/
│   ├── build_backend_contract.rs
│   ├── build_backend_contract_support/
│   │   ├── quoted_hash.rs
│   │   └── toml.rs
│   ├── build_standard_contract.rs
│   ├── build_standard_support/
│   │   ├── ci_steps.rs
│   │   ├── config.rs
│   │   ├── coverage_contract.rs
│   │   └── make.rs
│   ├── makefile_contract.rs
│   ├── makefile_contract_support/
│   │   ├── clippy_target_route.rs
│   │   ├── cross_caller_flags.rs
│   │   └── whitaker_binding.rs
│   ├── stable_cargo_config.rs
│   └── workflow_contracts/
│       ├── build_tools_cache_test.py
│       ├── build_tools_coverage_test.py
│       ├── build_tools_rules.py
│       ├── build_tools_runner.py
│       ├── build_tools_runner_test.py
│       ├── build_tools_test.py
│       ├── cargo_selection_test.py
│       ├── command_runner.py
│       ├── command_runner_test.py
│       ├── coverage_build_tools_test.py
│       ├── coverage_flags_test.py
│       ├── coverage_toolchain_rules.py
│       ├── coverage_toolchain_test.py
│       ├── markdown_formatting_test.py
│       ├── mutation_testing_test.py
│       ├── python_lint_gateway_test.py
│       ├── supported_route_inventory_test.py
│       ├── supported_route_rules.py
│       ├── whitaker_provisioning_rules.py
│       ├── whitaker_provisioning_test.py
│       └── workflow_contract_support.py
├── tools/
│   └── mold/
│       ├── SHA256SUMS
│       └── VERSION
├── AGENTS.md
├── Cargo.toml
├── LICENSE
├── Makefile
├── README.md
├── clippy.toml
├── codecov.yml
├── pyproject.toml
└── rust-toolchain.toml
```

## Path responsibilities

- `.cargo/config.toml`: Configures Cargo's discovered development defaults for
  `x86_64-unknown-linux-gnu`: the parallel `rustc` frontend and pinned `mold`
  linker. Rustc uses its LLVM backend on all targets.
- `.github/dependabot.yml`: Configures automated dependency update checks.
- `.github/cv005.toml`: Supplies repository-specific parameters to the shared
  CV-005 workflow contracts.
- `.github/workflows/act-validation.yml`: Runs the generated workflow
  validation through `act` separately from main CI.
- `.github/workflows/audit.yml`: Runs the scheduled Rust dependency audit.
- `.github/workflows/ci.yml`: Runs the generated project's continuous
  integration checks.
- `.github/workflows/coverage-main.yml`: Measures coverage on each push to
  `main`, writes the coverage ratchet baseline, and is the only workflow that
  uploads coverage to CodeScene.
- `.github/workflows/dependabot-automerge.yml`: Handles Dependabot pull
  request auto-merge through the shared workflow.
- `.github/workflows/mutation-testing.yml`: Runs scheduled and manually
  dispatched mutation tests through the shared workflow.
- `.github/workflows/release.yml`: Builds and publishes binary release
  artefacts for the application flavour.

- `docs/`: Holds long-lived reference documentation, guides, style rules, and
  design material.
- `docs/debugging/`: Holds investigation plans and their supporting evidence.
- `docs/contents.md`: Indexes the documentation set and should be updated when
  documentation files are added, renamed, or removed.
- `docs/users-guide.md`: Explains how to use the generated project and its
  public build and test commands.
- `docs/developers-guide.md`: Explains the contributor workflow and local
  tooling used to work on the generated project.
- `docs/repository-layout.md`: Documents the repository tree and path
  responsibilities.

- `src/lib.rs`: Contains library support for application logic and doctested
  examples.
- `src/main.rs`: Contains the application entrypoint and top-level executable
  wiring.

- `tests/`: Holds integration and behavioural tests that exercise public
  behaviour.
- `tests/build_backend_contract.rs`: Checks the development backend contract.
- `tests/build_standard_contract.rs`: Checks target-specific development
  defaults, Make routing, and build-tool prerequisites.
- `tests/build_backend_contract_support/`: Holds TOML readers and quoted-hash
  cases used by the development-backend contract.
- `tests/build_standard_support/`: Holds helpers shared by build-standard
  contract tests.
- `tests/makefile_contract.rs`: Checks the Makefile's public target behaviour.
- `tests/makefile_contract_support/`: Holds helpers for Clippy target routing,
  caller-supplied flags, and binding Whitaker gate contracts.
- `tests/stable_cargo_config.rs`: Checks that stable Cargo handles the
  configured release route.
- `tests/workflow_contracts/`: Holds pytest contracts for build-tool
  provisioning, Cargo selection, CodeScene build and coverage routes, toolchain
  routing, Markdown formatting, mutation testing, supported-route inventory,
  and Whitaker provisioning. `python_lint_gateway_test.py` guards the Python
  lint gateway wiring in the `Makefile` and `pyproject.toml`, and
  `command_runner.py` is the one place these tests start a process.
  `make test-workflow-contracts` also runs the shared CV-005 contracts with
  `.github/cv005.toml`.
- `scripts/`: Installs and checks the pinned development compiler and linker
  prerequisites used by the Makefile.
- `scripts/build-tools-common.sh`: Shares build-tool paths and checks between
  the installer and preflight scripts.
- `scripts/check-build-tools.sh`: Checks the pinned nightly and `mold`
  prerequisites before standard development Make targets compile.
- `scripts/clang-linker.sh`: Source for the installed `evert-clang-mold` linker
  wrapper. The installer places it in `$BUILD_TOOLS_PREFIX/bin` as
  `evert-clang-mold`; it verifies the pinned `mold` binary and passes its
  directory to Clang. Bare Cargo commands on the selected target require that
  install directory on `PATH`.
- `scripts/install-build-tools.sh`: Installs the pinned nightly and the
  checksum-verified `mold` binary for local development.
- `tools/mold/VERSION`: Records the `mold` release used by local build-tool
  provisioning.
- `tools/mold/SHA256SUMS`: Records the checksums for the supported `mold`
  archives used by local build-tool provisioning.
- `AGENTS.md`: Provides repository-specific working instructions for agents and
  contributors.
- `Cargo.toml`: Defines package metadata, dependencies, lint policy, and Cargo
  configuration.
- `LICENSE`: Records the project licence text.
- `Makefile`: Provides the public build, lint, test, coverage, and
  documentation validation commands.
- `README.md`: Introduces the project and gives the shortest useful
  getting-started path.
- `clippy.toml`: Configures Clippy lint behaviour that is not expressed
  directly in `Cargo.toml`.
- `codecov.yml`: Configures coverage reporting behaviour.
- `pyproject.toml`: Configures Ruff and Pylint for the Python lint gateway. It
  defines no Python project.
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
