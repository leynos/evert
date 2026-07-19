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

Dependabot owns the upgrade of GitHub Actions and reusable workflows,
including calls into `leynos/shared-actions`. Contract tests that assert a
caller's exact commit SHA create a lockstep dependency: every time Dependabot
opens a bump PR, the test fails until a human edits the pinned constant to
match. That defeats the purpose of automated dependency updates and turns a
routine bump into a manual chore.

Contract tests may still verify the *shape* of a reusable-workflow caller.
They must not verify the specific SHA value.

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

## Mutation-testing workflow contract tests

This repository runs scheduled, informational mutation testing through a thin
caller workflow,
[`.github/workflows/mutation-testing.yml`](../.github/workflows/mutation-testing.yml),
which delegates to the shared reusable workflow
`leynos/shared-actions/.github/workflows/mutation-cargo.yml`. The heavy
lifting — running `cargo-mutants` and summarizing survivors — lives in
`shared-actions`; this repository carries only declarative configuration. The
run is **informational only**: it never gates a pull request. Survivors are
reported through the job summary and downloadable artefacts so they can be
triaged into tests, not enforced as a blocking check.

The workflow runs in two modes. A **daily schedule** fires a change-scoped run
that mutates only the source files touched within the detection window, so
quiet days are cheap no-ops. A **manual dispatch** (the Actions "Run workflow"
control) mutates the whole crate; select a branch in that control to exercise
a feature branch.

The caller overrides two of the shared workflow's inputs:

- `extra-args` — set to `--all-features`, mirroring the CI baseline so any
  feature-gated tests run against mutants.
- `setup-commands` — installs `clang`, `lld`, and `mold` before the run,
  matching the linker configuration `.cargo/config.toml` requires on
  `x86_64-unknown-linux-gnu`, the same step CI's `Install mold linker` step
  performs.

Change-detection paths and exclude globs are left at the shared workflow's
defaults; the caller does not override them.

The `uses:` reference pins the shared workflow to a full 40-character commit
SHA rather than a branch or tag, so a force-push upstream cannot silently
change what runs here. The contract test asserts only that the pin is a full
commit SHA, not a particular value, so Dependabot bumps it automatically
without any accompanying test edit.

Because the caller is configuration rather than code, a contract test in
`tests/workflow_contracts/mutation_testing_test.py` pins the shape it must
uphold, failing the pull request when the caller drifts — repointing the pin
at a branch, widening the token scope, or dropping a configuration input —
rather than letting the breakage surface only in a scheduled run. Run it
locally with `make test-workflow-contracts`. The test validates:

- the `uses:` reference targets `mutation-cargo.yml` pinned to a full commit
  SHA;
- the `with:` block carries exactly the expected `extra-args` and
  `setup-commands` configuration;
- job permissions are least-privilege (`contents: read`, `id-token: write`)
  and the workflow-level default token scope is empty;
- `concurrency` serializes runs per ref without cancelling one in progress;
  and
- the triggers keep the daily schedule and a plain `workflow_dispatch` with
  no legacy branch input.

## Tooling

Development builds use Cranelift for debug code generation. On Linux targets,
`.cargo/config.toml` configures clang to link with `mold` so debug builds link
quickly. Coverage generation uses `lld` because LLVM coverage tooling expects
LLVM-compatible linker behaviour.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
