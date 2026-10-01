# Debugging Plan: Cranelift Unwind Test Abort

**Generated**: 2026-09-29 **Issue ID**: PR #64, build-standard batch
**Severity**: Blocking for the requested Cranelift development default
**Falsification sub-agent**: `alchemist` **Planning agent boundary**: The first
candidate was prepared by the supervisory agent. The revised candidate was
supplied by the measurement agent. Falsification was executed by the named
`alchemist` sub-agent.

## Problem Statement

On the integrated Evert branch at base commit
`49ca82df6d534f8117d6b9d510f4c623762f4214`, focused panic tests fail with the
auto-discovered x86_64 GNU/Linux Cranelift defaults under the pinned
`nightly-2026-05-28` compiler. `catch_unwind` returns a failed test and a
panicking spawned thread aborts with `failed to initiate panic, error 5`;
`#[should_panic]` succeeds. All three cases passed when the same compiler used
the explicit LLVM/default linker route. The requested development default
therefore lacks required panic-unwind evidence.

## Context Summary

| Aspect              | Details                                                   |
| ------------------- | --------------------------------------------------------- |
| First observed      | Focused run at `49ca82df6d534f8117d6b9d510f4c623762f4214` |
| Reproduction rate   | Reproduced once per failing case on x86_64 GNU/Linux      |
| Affected components | Rust test binary, Cranelift backend, panic runtime        |
| Recent changes      | Cranelift is selected for Linux x86_64 development        |

### Error Artefacts

```text
thread 'catch_unwind_observes_an_intentional_panic' panicked at
tests/build_backend_contract.rs:383:47: intentional unwind probe
test result: FAILED

thread '<unnamed>' panicked at
tests/build_backend_contract.rs:390:41: intentional thread panic probe
fatal runtime error: failed to initiate panic, error 5, aborting
process didn't exit successfully (signal: 6, SIGABRT)
```

The source logs are under `/tmp/evert-pr64-build-batch/panic-probe-49ca-run1/`:
`bare-catch.out`, `bare-join.out`, `bare-should-panic.out`, and corresponding
`.exit` files. LLVM control logs use the `llvm-` prefix in the same directory.
Their exit codes were 101, 101, and 0 for the Cranelift cases, and 0 for all
three LLVM cases.

### Information Gaps

- The differential probe covers the pinned compiler on x86_64 GNU/Linux only.
- The upstream README currently says panic unwinding is not supported and
  mentions `-Cpanic=abort` as the default. It does not prove the behaviour of
  Evert's exact May-pinned component.
- Cross-platform panic behaviour remains unmeasured. The two directly affected
  cases fail on Evert's selected host route; a full Cranelift suite is not a
  valid passing route while those cases remain in the workspace.

### Primary-Source Context

The official
[Cranelift backend README](https://github.com/rust-lang/rustc_codegen_cranelift)
read on 2026-09-29 lists panic unwinding as unsupported. The
[issue](https://github.com/rust-lang/rustc_codegen_cranelift/issues/1567) was
open and marked blocked when read; its status update says Rust tests with
`panic=unwind` remain work in progress. The README's latest listed commit was
`c6cc12438e36971a6abd17738d1dbb686a201b60` from 2026-09-28. These upstream
facts motivated testing an explicit panic strategy; the pinned target failed
that probe, as recorded below.

______________________________________________________________________

## Hypotheses

### H1: Forced Unwind Tables Restore Cranelift Test Unwinding

**Claim**: On `nightly-2026-05-28` for x86_64 GNU/Linux, the two failures occur
because the current Cranelift test binaries lack unwind tables unless rustc is
explicitly asked to emit them. Adding `-Cforce-unwind-tables=yes` while
retaining every current development flag makes both `catch_unwind` and
panicking-thread join pass.

**Plausibility**: Medium — the failures reproduce only under the Cranelift
route, while the same two tests pass under the LLVM control. This candidate
option must still be measured on the exact toolchain.

**Prediction**: If H1 holds, both failing tests exit 0 with the candidate flag,
and the four current Cranelift/frontend/linker flags remain present in the
compiler invocation.

#### H1 Falsification Plan

Run from the integration worktree at the recorded base, after the shared Cargo
gate slot is clear. Do not edit source or Cargo configuration. Preserve all
four defaults explicitly because setting `RUSTFLAGS` replaces Cargo's
auto-discovered `rustflags`; clear `CARGO_ENCODED_RUSTFLAGS` so it cannot take
precedence. Use the normal shared Cargo cache and the worktree's default target
directory. Run only the two failing cases:

```bash
DEV_FLAGS=(
  -Zcodegen-backend=cranelift
  -Zthreads=8
  -Clinker=evert-clang-mold
  -Clink-arg=-fuse-ld=mold
  -Cforce-unwind-tables=yes
)

env -u CARGO_ENCODED_RUSTFLAGS PATH="$HOME/.local/bin:$PATH" \
  RUSTFLAGS="${DEV_FLAGS[*]}" \
  cargo +nightly-2026-05-28 -vv test --test build_backend_contract \
  catch_unwind_observes_an_intentional_panic -- --exact --nocapture

env -u CARGO_ENCODED_RUSTFLAGS PATH="$HOME/.local/bin:$PATH" \
  RUSTFLAGS="${DEV_FLAGS[*]}" \
  cargo +nightly-2026-05-28 -vv test --test build_backend_contract \
  joining_a_panicking_thread_reports_its_panic -- --exact --nocapture
```

The executor must confirm the effective rustc invocation includes the four
existing flags plus `-Cforce-unwind-tables=yes`. Capture each command's full
output and exit status in a unique task-scoped directory under `/tmp`.

| Step | Action                                               | Expected Negative Result                                 |
| ---- | ---------------------------------------------------- | -------------------------------------------------------- |
| 1    | Run both cases with all defaults plus the candidate. | Any behavioural failure or rejected option falsifies H1. |
| 2    | A setup failure prevents either test from executing. | Inconclusive; report the exact error.                    |

**Tooling**: `rustup`'s pinned nightly Cargo/rustc, the existing integration
test target, and shell logging with preserved command exit statuses.

**Confidence on falsification**: High for these two panic paths on this exact
compiler and target. A successful result would leave H1 not falsified; it would
not establish correctness for the full suite or any other platform.

**Verdict**: Falsified on 2026-09-29 by the alchemist experiment. The verbose
invocation contained all four default flags plus `-Cforce-unwind-tables=yes`,
but catch_unwind still failed and thread join still aborted. Logs are under
`/tmp/evert-rust-baseline/pr64-unwind-alchemist-h1-20260929/`.

______________________________________________________________________

### H2: Explicit Unwind Strategy Enables the Pinned Cranelift Route

**Claim**: The pinned Cranelift component selects abort semantics when the
panic strategy is implicit. Explicitly adding `-Cpanic=unwind` to Evert's test
compilation, while retaining the four configured development flags, makes both
failing panic paths pass.

**Plausibility**: Medium — the official backend README identifies abort as the
default and unwinding as unsupported, while the current Evert rustc invocation
contains no explicit panic-strategy flag. The result must be measured because
the installed component predates the current README.

**Prediction**: If H2 holds, both failing tests exit 0 and the effective rustc
invocation contains all four existing defaults plus `-Cpanic=unwind`.

#### H2 Falsification Plan

Run only after the shared Cargo gate slot is clear. Do not edit source or
configuration. Clear `CARGO_ENCODED_RUSTFLAGS` because it takes precedence, and
explicitly retain all four defaults because `RUSTFLAGS` replaces Cargo's
auto-discovered flags. Use the normal shared Cargo cache and the worktree's
default target directory:

```bash
DEV_FLAGS=(
  -Zcodegen-backend=cranelift
  -Zthreads=8
  -Clinker=evert-clang-mold
  -Clink-arg=-fuse-ld=mold
  -Cpanic=unwind
)

env -u CARGO_ENCODED_RUSTFLAGS PATH="$HOME/.local/bin:$PATH" \
  RUSTFLAGS="${DEV_FLAGS[*]}" \
  cargo +nightly-2026-05-28 -vv test --test build_backend_contract \
  catch_unwind_observes_an_intentional_panic -- --exact --nocapture

env -u CARGO_ENCODED_RUSTFLAGS PATH="$HOME/.local/bin:$PATH" \
  RUSTFLAGS="${DEV_FLAGS[*]}" \
  cargo +nightly-2026-05-28 -vv test --test build_backend_contract \
  joining_a_panicking_thread_reports_its_panic -- --exact --nocapture
```

Capture each command's full output and exit status in a unique task-scoped
directory under `/tmp`, and verify the effective rustc invocation contains all
five flags.

| Step | Action                                                  | Expected Negative Result                                                        |
| ---- | ------------------------------------------------------- | ------------------------------------------------------------------------------- |
| 1    | Run both cases with all defaults plus `-Cpanic=unwind`. | Either case still fails/aborts, or rustc rejects the option; this falsifies H2. |
| 2    | A setup failure prevents a named case from executing.   | Inconclusive; report the exact error.                                           |

**Tooling**: Pinned nightly Cargo/rustc, the existing integration test target,
and shell logging with preserved exit statuses.

**Confidence on falsification**: High for these two cases on the pinned
compiler and target. A pass still requires a full suite and independent
`#[should_panic]` verification under the intended route.

**First dispatch**: Inconclusive without execution. The shared Cargo slot was
occupied by another repository's Podbot test; preflight exited 75 and neither
Evert case ran. Evidence is in
`/tmp/evert-rust-baseline/pr64-unwind-alchemist-h2-20260929/preflight-processes.out`.

**Verdict**: Falsified on 2026-09-29 by the second alchemist dispatch. The
verbose compiler invocation contained all four development defaults plus
`-Cpanic=unwind`. `catch_unwind` still failed (exit 101), and a spawned-thread
panic still aborted with `failed to initiate panic, error 5` (exit 101,
SIGABRT). Logs are in
`/tmp/evert-rust-baseline/pr64-unwind-alchemist-h2-20260929-run2/`.

______________________________________________________________________

## Findings and Next Decision

Both tested candidates are falsified on the pinned toolchain and target. The
current official backend README also says unwinding is unsupported, and the
upstream issue 1567 remains blocked. These results do not establish behaviour
on other targets; they do establish that the two included tests fail under the
requested host default. Do not run the full suite and present it as a passing
Cranelift route. The next action is a recorded baseline decision from the
authorized maintainer or upstream backend support; no exception is approved by
this investigation.

## Termination Criteria

The investigation is complete. The Cranelift development-default requirement
remains blocked for x86_64 GNU/Linux until the backend supports unwinding on
the selected pinned toolchain or an authorized, precisely scoped baseline
resolution is recorded. Do not weaken the panic probes, route only those tests
through LLVM, or claim the full Cranelift suite passes.

## Notes for Executing Agent

The integration owner is working in
`/home/leynos/.lody/repos/github---leynos---evert/worktrees/pr64-integration` on
`chore/rust-build-standard`. The tracked source base is
`49ca82df6d534f8117d6b9d510f4c623762f4214`, with task changes in the worktree.
The probes are complete. Preserve the recorded shared-cache rule: do not alter
the tests or use another Cargo cache to make a candidate appear to pass.

## Decision update (2026-10-01)

The authorized maintainer resolved the default-backend decision: exclude
Cranelift from Evert's development flags and pinned toolchain components. Keep
both panic probes unchanged and use LLVM for the supported development route.
The [follow-up issue #80](https://github.com/leynos/evert/issues/80) schedules
a support review for 1 April 2027. This decision supersedes the earlier
statement that no baseline resolution had been approved.
