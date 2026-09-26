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

`Cargo.toml`'s `[lints.clippy]`, `[lints.rust]`, and `[lints.rustdoc]` tables
hold this repository's lint baseline. `evert` is a single crate with no
`[workspace]` table, so the tables live directly on the crate manifest rather
than under `[workspace.lints]` with per-member inheritance. `Cargo.toml` is
authoritative for the exact entries; this section summarizes intent rather than
duplicating the list.

The baseline follows the estate's phase 2 Rust conventions: hygiene and
panic-prone operations are denied outright (`unwrap_used`, `indexing_slicing`,
`unreachable`, and similar), `pedantic` is enabled as a warning tier, and
`missing_docs` and `missing_crate_level_docs` require real documentation rather
than suppression.

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
entry is gone, never saved or since evicted, the re-run saves the older
commit's baseline again, the shared action restores the newest entry under the
key prefix, and later ratchets read the older baseline until the next push
saves a newer one. That stale-order risk is accepted.

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

`make test-workflow-contracts` holds this shape. The contract tests are
`codescene_pull_request_test.py`, `codescene_publisher_test.py` and
`codescene_token_test.py` under `tests/workflow_contracts/`, with the rules in
the `codescene_*_rules.py` modules beside them, the strict workflow reader in
`codescene_workflow_reader.py`, and the scalar flattening the marker rules
share in `codescene_workflow_text.py`. The rules read every workflow a pull
request can start, from its own events, reviews and comments, a merge queue, or
a push not confined to `main` or tags, following local reusable-workflow calls
and `workflow_run` chains, and refuse any mention of the CodeScene host,
uploader, client, or token there, and any local action or action named as this
repository at a ref, whose `action.yml` they do not read. They also refuse
`continue-on-error` wherever it would turn a failed ratchet or upload green,
and any `if:` on the job holding the pull-request coverage step, whose own
guard already selects pull requests. The upload guard is compared as an exact
set of conjuncts, so an `||` hidden inside an extra conjunct fails the
comparison without a separate scan. Each clause has a test that mutates the
workflows and expects the clause to refuse the result.

The publisher job declares `environment: codescene`. That environment admits
deployments from `main` alone and is where the CodeScene token lives, so only
the trunk publisher can read it.
`tests/workflow_contracts/codescene_environment_rules.py` holds the placement:
every uploading job declares the environment, as a string or as
`{name: codescene}`; no other job declares it; and no workflow a pull request
can start declares it in any job.
`tests/workflow_contracts/codescene_environment_test.py` proves each clause by
mutation.

## Tooling

Development builds use the standard LLVM backend by default. On Linux targets,
`.cargo/config.toml` configures clang to link with `mold` so debug builds link
quickly. Coverage generation uses `lld` because LLVM coverage tooling expects
LLVM-compatible linker behaviour.

The pinned nightly toolchain retains the `llvm-tools-preview` and
`rustc-codegen-cranelift-preview` components, so the Cranelift backend and LLVM
coverage tooling are always installed; `tools/dev-fast/config.toml` is what
actually controls the repository-local opt-in activation. The opt-in
accelerated path, `make dev-build` and `make dev-test`, applies the Cranelift
codegen backend alongside `mold` via that fragment. It requires a nightly
toolchain and is never applied to release, coverage, or verification builds; see
[Fast development builds](../AGENTS.md#fast-development-builds) in `AGENTS.md`.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
