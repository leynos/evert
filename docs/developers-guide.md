# Developer guide

This guide explains the contributor workflow for Evert.

## Normative design sources

Use these documents before adding or changing compiler behaviour:

- [Terms of reference](terms-of-reference.md) defines the problem space, scope,
  constraints, and success criteria.
- [Evert context](context.md) defines the terms used by the language and
  compiler documentation.
- [Evert design](evert-design.md) defines the compiler architecture and initial
  semantic contracts.
- [Roadmap](roadmap.md) sequences work into testable phases, steps, and tasks.
- [Repository layout](repository-layout.md) explains ownership boundaries for
  source, tests, documentation, and automation.
- The accepted ADRs in `docs/adr-*.md` record decisions that constrain
  implementation work.

The top-level [README](../README.md) is the visitor-facing research-project
pitch. Keep it concise and link-oriented. Do not move normative semantics,
roadmap detail, or ADR rationale into the README; promote those decisions to
the documents above and point readers there.

When a change alters language semantics, compiler architecture, public command
behaviour, or internal ownership boundaries, update the corresponding design,
roadmap, ADR, guide, or layout document in the same change.

## Local workflow

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

Development builds use Cranelift for debug code generation. On Linux targets,
`.cargo/config.toml` configures clang to link with `mold` so debug builds link
quickly. Coverage generation uses `lld` because LLVM coverage tooling expects
LLVM-compatible linker behaviour.

Install `clang`, `lld`, `mold`, `python3`, and `cargo-audit` before running the
full generated workflow locally on Linux.

## Design workflow

Treat `docs/references/` as historical input rather than normative
specification. Promote decisions from those references into the terms of
reference, design, roadmap, ECLP files, or ADRs before implementing them.

Create implementation tasks from the roadmap. A task is ready when it names its
design source, dependency, success condition, and relevant validation target.
If implementation reveals a design mismatch, update the design before expanding
the code to work around the mismatch.

### Security audit ignores

Security audit jobs may set `CARGO_AUDIT_IGNORES` for narrowly scoped RustSec
advisories that affect unused or tooling-only dependency paths. Keep each
ignore tied to a documented runtime impact analysis, and remove it when the
affected dependency leaves the graph or the project starts using the advised
runtime path.
