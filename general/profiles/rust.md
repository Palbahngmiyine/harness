# Rust functional programming profile

Canonical English. [한국어](rust.ko.md). Apply with [common rules](../AGENTS.md) and [verification](../fp/verification.md). Evidence: [sources](../references/functional-programming.md).

## Values, effects, and composition

**RS-001** Use enums, immutable structs, private fields, and smart constructors for domain values; use `Option`/`Result` and exhaustive matches for absence and expected failure. Validate deserialization, FFI, migrations, and feature-specific constructors too. No panic, unchecked indexing, or `unwrap` for untrusted input or expected errors.

**RS-002** Ownership, borrowing, `&T`, `Send`, `Sync`, `Fn`, `const fn`, and `#![forbid(unsafe_code)]` are not effect or totality proofs. Keep explicit input/output contracts and a reviewed dependency boundary. Use `forbid(unsafe_code)` in the semantic crate where feasible, but do not claim it inspects dependencies or excludes safe I/O.

**RS-003** Exclude shared `Cell`, `RefCell`, atomics, locks, lazy mutable state, and other `UnsafeCell`-based capabilities from domain inputs/results and captures. `Arc<T>` only provides shared ownership; inspect `T` and all reachable state. Immutable sharing is valid when the entire reachable representation respects the contract.

**RS-004** `Fn` constrains how a callable is invoked, not what it can observe or change. Audit trait implementations, iterator callbacks, overloaded operators, `Deref`, `Clone`, formatting, and destructors for hidden effects. A closure using `Cell` can implement `Fn` and still change state. Generic bounds need an audited semantic contract, not a purity claim inferred from a trait name.

**RS-005** Compose named functions with iterators, `map`, `and_then`, `try_fold`, and pattern matching when they clarify the contract. `collect::<Result<_, _>>()` is fail-fast; accumulating independent validation errors needs an explicit design. Preserve iteration order when observable; choose deterministic ordering/encoding for results rather than assuming hash traversal is stable. Do not implement higher-kinded emulation or an effect runtime without a real need.

**RS-006** Model changes as consumed/borrowed immutable state to new state plus command data. Consuming a value avoids some alias problems but does not alone exclude effects. Keep concrete I/O handles, runtime access, and mutable service objects outside domain decisions. If a future/action is constructed, inspect when code actually runs; polling and dropping it can be effectful.

## Implementation and resources

**RS-007** Prefer immutable semantic implementations. Owned local mutation, builders, arenas, or in-place algorithms belong behind the FP-007 admission contract, not an automatic `mut` exception. Record non-escape, read/write footprint, no external observation, allocation/Drop behavior, termination, and reference equivalence. Aeneas-style functional translation is a verification option for supported code, not a claim that arbitrary safe Rust is already proved pure.

**RS-008** Specify checked, saturating, or wrapping arithmetic explicitly; do not depend on debug/release overflow differences. Bound recursion, iterator work, input sizes, and allocation demands. `Result` does not turn allocator abort, stack overflow, or panic-abort into a recoverable error. Use fallible allocation APIs where the recovery contract requires and supports them; record the remaining process-level assumptions.

**RS-009** Keep effectful `Drop` outside semantic values, including nested/generic values and values discarded on error. RAII aids cleanup but is not a guarantee against abort, leaks, forgotten values, or external process termination. Make fallible finalization an explicit operation; preserve both primary and cleanup failures. Do not rely on unwinding for guaranteed recovery.

**RS-010** Treat async work as an effect boundary with an owner, bounded concurrency, joining, and cancellation policy. Dropping a future is not evidence that a remote write was rolled back or never happened. Model unknown outcomes and operation IDs; verify cancellation at each suspension point relevant to owned resources. Avoid detached tasks and locks held across suspension unless explicitly justified and tested.

**RS-011** Keep FFI/unsafe in narrow adapters with documented safety preconditions and checked conversion to safe domain values. Apply both language profiles for C interop. Pin the ABI representation, null/length rules, ownership/deallocator pairing, lifetimes, thread/callback rules, and panic/unwind behavior. Do not expose a Rust enum, slice, reference, or allocator-owned buffer as an arbitrary C representation.

## Verification and assurance

**RS-012** Record edition, MSRV/toolchain, features, target, panic strategy, and dependency versions. Run formatter, compiler, project-specific Clippy rules, tests, and relevant feature/target combinations. Verify debug and release semantics; `debug_assert!` is not a required production invariant check. Do not add broad lint allowances or `unsafe` merely to obtain a green build.

**RS-013** Use property tests with domain generators/shrinkers, reference-model comparison, fault injection, and controlled-schedule tests where relevant. Miri and sanitizers provide dynamic evidence within supported executions; Clippy and an unsafe ban are not purity proofs. Document unavailable tools and unresolved obligations rather than reporting them as passed.

**RS-014** For formal verification, specify the supported subset, extraction/tool versions, backend model, dependency contracts, unproved obligations, and termination claim. Aeneas excludes important patterns in its stated approach, including unsafe/interior mutability; do not infer coverage of FFI or arbitrary async runtimes. Refinement to a pure model is scoped evidence, not a whole-system correctness certificate.
