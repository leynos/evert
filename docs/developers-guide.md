# Developer Guide

This guide explains the contributor workflow for the generated Evert project.

## Local Workflow

Use `make all` as the public entrypoint for formatting, linting, and tests.
`make lint` runs rustdoc, Clippy, and Whitaker, then the
[Python lint gateway](#python-lint-gateway). `make test` prefers
`cargo nextest run` and falls back to `cargo test` when cargo-nextest is not
available. `make audit` derives the Rust workspace root with `cargo metadata`,
logs workspace member manifests, and runs `cargo audit` once from the workspace
root. `make coverage` uses `cargo llvm-cov` with `lld`.

GitHub Actions Act validation lives in `.github/workflows/act-validation.yml`.
The main `.github/workflows/ci.yml` workflow deliberately does not run
`make test WITH_ACT=1`; the separate Act workflow runs those slower
container-backed checks in parallel.

## Lint baseline

`Cargo.toml`'s `[lints.clippy]`, `[lints.rust]`, and `[lints.rustdoc]` tables
hold this repository's lint baseline. `evert` is a single crate with no
`[workspace]` table, so the tables live directly on the crate manifest rather
than under `[workspace.lints]` with per-member inheritance. `Cargo.toml` is
authoritative for the exact entries; this section summarizes intent rather than
duplicating the list.

The baseline follows the estate's phase 2 Rust conventions: hygiene and
panic-prone operations are denied outright (`unwrap_used`, `indexing_slicing`,
`unreachable`, and similar), `pedantic` is enabled as a warning tier, and
`missing_docs_in_private_items`, `missing_docs`, and `missing_crate_level_docs`
require real documentation rather than suppression.

Where a lint violation is a genuine, tracked deferral rather than a bug,
annotate the site with `#[expect(clippy::<lint>, reason = "...")]`, never
`allow`. An `#[expect]` only suppresses the warning while the violation
remains; once the site is fixed, the unfulfilled expectation itself warns, so
the deferral surfaces for removal instead of rotting silently in the codebase.

`clippy.toml` carries the numeric thresholds behind the baseline (cognitive
complexity, argument count, function length, nesting depth) and the
`disallowed-methods` list that blocks direct `std::env::var`/`var_os`/`vars`/
`vars_os`/`set_var`/`remove_var` calls. Each disallowed method's `reason` tells
the contributor what to do instead: inject an environment reader in production
code, or use a stub environment in tests.

The pinned nightly toolchain in `rust-toolchain.toml` supplies the `rustfmt`,
`clippy`, and `rust-analyzer` components the baseline and this workflow depend
on.

## Python lint gateway

`make lint` runs the Rust gates first and the Python gates after them, with
warnings denied. `make lint-python` runs the Python gates on their own. In
order, it runs:

- Ruff (`ruff check`), pinned by `RUFF_VERSION` (0.16.4).
- Pylint, pinned by `PYLINT_VERSION` (4.0.9), with the selected message set
  enabled in `pyproject.toml`.
- The df12 house lints, a Pylint plugin from `leynos/df12-python-lints`, pinned
  by `DF12_PYTHON_LINTS_REF` (tag `v0.3.0`). `DF12_PYLINT_MESSAGES` lists the
  R9101-R9112 and C9102-C9112 messages the target enables.
- `ambrleaks`, from the same df12 package and ref.
- Interrogate, pinned by `INTERROGATE_VERSION` (1.7.0), with `--fail-under 100`.
  Every module, class, function, nested function, and test needs a docstring.

Rule sets differ between releases, so each tool is pinned exactly. To bump one,
change its Makefile variable and fix the new findings in the same commit.

`pyproject.toml` only configures these linters. It has no `[project]` or
`[build-system]` table, so nothing can be built or published from it and `uv`
never treats the repository as a Python project. It mirrors the Ruff and Pylint
configuration of `leynos/netsuke`, which itself mirrors `leynos/episodic`; only
path-shaped settings are local.

All tools run on CPython 3.14 through `uv tool run`. `uv` fetches a managed
3.14 interpreter, so contributors need `uv` but not a system Python 3.14.
`make test-workflow-contracts` runs pytest on the same baseline. The baseline
is set in three places, which must agree: `PYTHON_BASELINE` in the `Makefile`
(3.14), `target-version` (`py314`) and `py-version` in `pyproject.toml`.

`PYTHON_SOURCE_ROOTS` in the `Makefile` lists the source roots:
`.github/scripts`, `.github/actions`, `scripts`, `tests`, `benches`, and
`benchmarks`. Only roots that contain Python are linted, so a new script,
benchmark, or workflow-run module is covered as soon as it exists. Today only
`tests/workflow_contracts/` holds Python.

Do not silence a Python lint: no `# noqa`, `# pylint: disable`, or
`# type: ignore`. Fix the code. Two exemptions are configured, both scoped by
file in `pyproject.toml`:

- Ruff's `assert` rule (`S101`) for files under `tests/`, because pytest relies
  on plain `assert` statements and rewrites them to report the compared values.
- Ruff's subprocess import and call rules (`S404` and `S603`) for
  `tests/workflow_contracts/command_runner.py` alone. No code change satisfies
  those two rules, and some contracts can only be proved by running the real
  tools, so all process spawning goes through that one helper. It uses no
  shell, takes a fixed argument list, and resolves the executable itself;
  `command_runner_test.py` holds those properties. Every other module that
  imports `subprocess` fails the gate.

Docstrings follow the numpy convention (Ruff's `D` and `DOC` rules). The line
length is 88, and a module may have at most 400 lines, matching the
repository's file-size ceiling.

`tests/workflow_contracts/python_lint_gateway_test.py` guards the wiring. It
fails if a Python file sits outside the source roots, if the three baseline
settings disagree, if `lint` stops depending on `lint-python`, if a tool is
missing from the recipe, or if a tool version or the df12 ref is not an exact
pin.

## Spelling policy

`make all` and `make markdownlint` enforce en-GB-oxendict spelling by running
`make spelling`, which invokes the `typos-config-builder` gate pinned by
`TYPOS_CONFIG_BUILDER_VERSION` in the `Makefile`. The gate regenerates
`typos.toml` from the live shared dictionary and this repository's overlay on
every run, then scans tracked Markdown files.

The shared dictionary is maintained in `leynos/agent-helper-scripts` and is
fetched by the gate; `typos.toml` is a generated artefact, so CI never
drift-checks it against the checked-in copy.

Do not edit `typos.toml` by hand. Put only repository-specific proper nouns,
quoted upstream titles, fixtures, stems or exclusions in `typos.local.toml`,
then rerun:

```bash
make spelling
```

Keep upstream API spellings in inline or fenced code where practical. The
spelling gate deliberately ignores code spans and fenced code blocks.

## Workflow pins and Dependabot

Dependabot owns the upgrade of GitHub Actions and reusable workflows, including
calls into `leynos/shared-actions`. Contract tests that assert a caller's exact
commit SHA create a lockstep dependency: every time Dependabot opens a bump PR,
the test fails until a human edits the pinned constant to match. That defeats
the purpose of automated dependency updates and turns a routine bump into a
manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller. They
must not verify the specific SHA value.

- Do assert the workflow references the correct reusable workflow path.
- Do assert the ref is pinned to a full 40-character commit SHA, not a
  mutable branch such as `main` or `rolling`.
- Do assert the expected `on:` triggers, least-privilege `permissions:`, and
  the inputs the caller relies on.
- Do not hard-code the current SHA value as an expected string. Match it with
  a pattern instead.
- Do not fail a test purely because Dependabot bumped the pinned SHA.

```python
import re

SHA_RE = re.compile(r"^[0-9a-f]{40}$")

def test_uses_pinned_full_sha(caller_step):
    ref = caller_step["uses"].split("@")[-1]
    assert SHA_RE.match(ref), f"expected a 40-hex commit SHA, got {ref!r}"
```

If a workflow's behaviour genuinely depends on a feature only present from a
particular commit onwards, express that as a comment or a changelog note, not
as a test assertion on the SHA string.

## Coverage publication

Pull-request continuous integration (CI) generates LCOV coverage and ratchets
it against the baseline written by `coverage-main.yml`. The pull-request lane
publishes no coverage artefact, never contacts CodeScene, and never receives
`CS_ACCESS_TOKEN`, so a change in CodeScene's application programming interface
(API) cannot hold a pull request.

`coverage-main.yml` is the only publisher. On each push to `main` it refreshes
the ratchet baseline and uploads the report to CodeScene. It also runs on
demand through `workflow_dispatch`, for merges that fire no push event: a
dispatch on `main` uploads a fresh report, but the shared action advances the
baseline only on a push, so the ratchet catches up at the next push to `main`.
No `env` binds `CS_ACCESS_TOKEN`: a check step writes whether the secret is
set, from an expression evaluated before its shell runs, and the upload step
receives the token only as its `access-token` input, because the uploader is a
composite action that would pass its step's `env` to its nested steps. The
upload runs only when the token is present and the ref is `refs/heads/main`, so
a dispatch from a branch cannot publish that branch's coverage as the trunk's.

The publisher's concurrency group is keyed on the ref alone and never cancels a
run in progress, so runs on `main` never overlap, and a newer trigger replaces
an older pending run rather than queueing behind it. GitHub does not promise to
start runs in trigger order, so this does not guarantee commit order: an older
run that starts late can publish its commit's coverage after a newer one, and
the next push supersedes it. A manual re-run of an older run keeps its SHA and
its run id: it republishes that commit's coverage to CodeScene, but replaces no
ratchet baseline while the original run's cache entry survives, because the
shared action saves each baseline under a key that includes the run id. If that
entry is gone, never saved or since evicted, a re-run of a push saves the older
commit's baseline again, the shared action restores the newest entry under the
key prefix, and later ratchets read the older baseline until the next push
saves a newer one. That stale-order risk is accepted. A re-run of a dispatch
saves no baseline, since the shared action saves one only on a push.

Two gaps are known and accepted, and both are tracked in
[shared-actions issue 518](https://github.com/leynos/shared-actions/issues/518):

- Merges made by the Dependabot automerge workflow use `GITHUB_TOKEN` and fire
  no push event, so they are measured only at the next push to `main` or a
  manual dispatch.
- A dispatch that replaces a pending push writes no baseline, since the shared
  action saves one only on a push, so the ratchet baseline stays behind until
  the next push. A dispatch made before a push can also reach the concurrency
  group after it, replace it and upload the older commit; that is part of the
  stale-order risk accepted above.

No other workflow a push starts, directly or through a local call, may generate
coverage outside the pull-request guard, and none, the publisher included, may
run a local action, whose `action.yml` the contract does not read, so the
publisher is the only baseline writer. Both coverage steps select the same
inputs at the same `shared-actions` pin because the pull-request ratchet is
only meaningful against a baseline measured the same way.

The repository-specific build-standard tests use
`tests/workflow_contracts/workflow_contract_support.py` only for strict YAML
reading and workflow-shape access. Keep build, coverage, and route assertions
in their corresponding `*_rules.py` modules; do not extend the helper with
another copy of shared CV-005 policy.

`make test-workflow-contracts` holds this shape by running
`cv005-contracts check`, the shared contract library in `leynos/shared-actions`
(`packages/cv005-contracts`), from a full commit named by `CV005_CONTRACTS_REF`
in the Makefile, and CI runs it as its own step. A fix to the rules is
therefore a pin bump. The target needs `uv`, which fetches the Python 3.13 the
library runs under. The repository's parameters are in `.github/cv005.toml`: its
`repository` name and the `[selection]` inputs the baseline measures, which
the publisher's generator must carry and every pull-request lane must match.
The library's own suite proves each rule refuses the shape it exists to refuse,
so this repository keeps no copy of the readers or the refusal cases. Its rules
read every workflow a pull request can start, from its own events, reviews and
comments, a merge queue, or a push not confined to `main` or tags, following
local reusable-workflow calls, `workflow_run` chains and local composite
actions, and refuse any mention of the CodeScene host, uploader, client, or
token there. They also refuse `continue-on-error` wherever it would turn a
failed ratchet or upload green, and they read workflows strictly, so a
duplicate key is refused rather than silently resolved.

The publisher job declares `environment: codescene`. That environment admits
deployments from `main` alone and is where the CodeScene token lives, so only
the trunk publisher can read it. The shared library holds the placement: every
uploading job declares the environment, as a string or as `{name: codescene}`;
no other job declares it; and no workflow a pull request can start declares it
in any job.

## The build standard

Development, test, lint, and typecheck builds use the parallel `rustc` frontend
(`-Zthreads=8`) and, on Linux, the `mold` linker (`-Clink-arg=-fuse-ld=mold`).
These are defaults in `.cargo/config.toml`, which Cargo discovers on its own,
so a bare `cargo build` gets them. `mold` ships for Linux only, so the linker
flag lives in a Linux-only table and macOS and Windows keep their platform
linker. Cargo selects one `rustflags` source rather than merging them, so every
source repeats the same flags apart from the linker.

An assigned `RUSTFLAGS` replaces the configuration's flags, so the Makefile
recipes that set it compose the standard's flags onto any inherited value (CI's
`setup-rust` exports one). Two builds are deliberately excluded: coverage
assigns `RUSTFLAGS` without the fast flags, because a measurement should not
depend on them, and the release recipe and workflow keep the platform linker,
because they assign `RUSTFLAGS` (even an empty value displaces the
configuration). Cargo has no per-profile `rustflags`, so a direct
`cargo build --release` takes the configuration's flags unless `RUSTFLAGS` is
assigned too.

On Linux, install `mold` before building: the configuration names it, so a
build without it fails at link time. CI installs it through `setup-rust`'s
`install-mold` input. `tests/build_standard_contract.rs` holds the standard. It
reads the configuration sources, the commands `make -n` prints for each
development target on a Linux host and a macOS host (each keeping the caller's
own `RUSTFLAGS`) and for each coverage and release target on a Linux host, and
the `setup-rust` steps of the CI workflows (each must pass `install-mold`), so
a flag lost through a recipe or workflow edit fails there.

### Backend support

Cranelift is excluded from the development defaults and pinned toolchain
components. With Cranelift selected on the pinned `nightly-2026-05-28` Linux
toolchain, the `catch_unwind` contract fails and a panicking joined thread
aborts with `failed to initiate panic, error 5`. Both probes pass on LLVM, so
the standard retains LLVM until Cranelift supports these panic paths. The
[follow-up issue #80](https://github.com/leynos/evert/issues/80) schedules a
review for 1 April 2027; the tests must remain intact when support is
reassessed.

## Tooling

The LLVM and pinned `mold` development route applies to
`x86_64-unknown-linux-gnu`; other targets use LLVM and their platform linker.
Run `make install-build-tools` to provision the pinned nightly and local build
tools, including `mold` 2.41.0 and the `evert-clang-mold` wrapper. Standard
Make targets add the install directory to `PATH` and check prerequisites before
compiling. Bare Cargo commands on the selected target need the same directory on
`PATH`. The wrapper source is `scripts/clang-linker.sh`; it checks the pinned
linker and passes its directory to Clang so the system linker cannot take
precedence. Coverage uses LLVM and `lld` for compatibility with coverage
tooling. The pinned nightly includes the `llvm-tools-preview` component.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

On `x86_64-unknown-linux-gnu`, development, test, lint, and typecheck use this
LLVM and pinned-linker route. Cargo's target table also applies to a direct
cross build *to* `x86_64-unknown-linux-gnu` from another host. That cross-host
development route is unsupported: the linker wrapper and pinned `mold`
installation target the Linux build host. Use the Linux host for development
builds; the stable Cross release workflow handles explicit release targets.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
