# Developer Guide

This guide explains the contributor workflow for the generated Evert project.

## Local Workflow

Use `make all` as the public entrypoint for formatting, linting, and tests.
`make lint` runs rustdoc, Clippy, and Whitaker. `make test` prefers
`cargo nextest run` and falls back to `cargo test` when cargo-nextest is not
available. `make audit` derives the Rust workspace root with `cargo metadata`,
logs workspace member manifests, and runs `cargo audit` once from the workspace
root. `make coverage` uses `cargo llvm-cov` with `lld`.

GitHub Actions Act validation lives in `.github/workflows/act-validation.yml`.
The main `.github/workflows/ci.yml` workflow deliberately does not run
`make test WITH_ACT=1`; the separate Act workflow runs those slower
container-backed checks in parallel.

## Lint baseline

`Cargo.toml`'s `[lints.clippy]`, `[lints.rust]`, and `[lints.rustdoc]`
tables hold this repository's lint baseline. `evert` is a single crate
with no `[workspace]` table, so the tables live directly on the crate
manifest rather than under `[workspace.lints]` with per-member
inheritance. `Cargo.toml` is authoritative for the exact entries; this
section summarizes intent rather than duplicating the list.

The baseline follows the estate's phase 2 Rust conventions: hygiene
and panic-prone operations are denied outright (`unwrap_used`,
`indexing_slicing`, `unreachable`, and similar), `pedantic` is enabled
as a warning tier, and `missing_docs` and `missing_crate_level_docs`
require real documentation rather than suppression.

Where a lint violation is a genuine, tracked deferral rather than a
bug, annotate the site with
`#[expect(clippy::<lint>, reason = "...")]`, never `allow`. An
`#[expect]` only suppresses the warning while the violation remains;
once the site is fixed, the unfulfilled expectation itself warns, so
the deferral surfaces for removal instead of rotting silently in the
codebase.

`clippy.toml` carries the numeric thresholds behind the baseline
(cognitive complexity, argument count, function length, nesting
depth) and the `disallowed-methods` list that blocks direct
`std::env::var`/`var_os`/`vars`/`vars_os`/`set_var`/`remove_var`
calls. Each disallowed method's `reason` tells the contributor what to
do instead: inject an environment reader in production code, or use a
stub environment in tests.

The pinned nightly toolchain in `rust-toolchain.toml` supplies the
`rustfmt`, `clippy`, and `rust-analyzer` components the baseline and
this workflow depend on.

## Spelling policy

`make all` and `make markdownlint` enforce en-GB-oxendict spelling with the
`TYPOS_VERSION` pin in the `Makefile`. The gate first tests the policy helper,
refreshes the shared base dictionary, generates `typos.toml`, and scans tracked
Markdown files.

The shared dictionary is maintained in `leynos/agent-helper-scripts`. Its
repository-local cache and freshness metadata are untracked. The helper
replaces the cache only when the authoritative copy is newer and can reuse a
valid cached copy while offline. A clean checkout with an unavailable network
retains the reviewed, tracked `typos.toml` policy.

Do not edit generated entries in `typos.toml`. Put only repository-specific
proper nouns, quoted upstream titles, fixtures, stems or exclusions in
`typos.local.toml`, then regenerate with:

```bash
uv run scripts/generate_typos_config.py
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

## Tooling

Development builds use the standard LLVM backend by default. On Linux
targets, `.cargo/config.toml` configures clang to link with `mold` so debug
builds link quickly. Coverage generation uses `lld` because LLVM coverage
tooling expects LLVM-compatible linker behaviour.

The pinned nightly toolchain retains the `llvm-tools-preview` and
`rustc-codegen-cranelift-preview` components, so the Cranelift backend and
LLVM coverage tooling are always installed; `tools/dev-fast/config.toml` is
what actually controls the repository-local opt-in activation. The opt-in
accelerated path, `make dev-build` and `make dev-test`, applies the
Cranelift codegen backend alongside `mold` via that fragment. It requires a
nightly toolchain and is never applied to release, coverage, or
verification builds; see [Fast development
builds](../AGENTS.md#fast-development-builds) in `AGENTS.md`.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
