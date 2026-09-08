# Go functional programming profile

Canonical English. [한국어](go.ko.md). Apply with [common rules](../AGENTS.md) and [verification](../fp/verification.md). Evidence: [Go sources](../references/functional-programming.md#go-semantics-and-verification).

Scope: implementation and executable-verification obligations apply to actual Go software changes. Profile maintenance uses CHK-014 document review. This package contains no Go module, executable examples, or runner.

## Values, effects, and composition

**GO-001** Model domain values with small structs, explicit variants, and validated construction. Go does not enforce exhaustive switches over enum-like constants; reject unsupported tags and invalid tag/payload combinations explicitly. Unexported fields do not prevent zero-value construction. Make zero values valid by design or reject them at every ingress, including decoding and migration.

**GO-002** Passing a struct by value does not make reachable storage immutable: slices, maps, pointers, and interface payloads may share mutable data. Establish race-free, coherent snapshots at ingress and prevent mutable aliases from escaping through constructors or accessors. Shallow copies do not isolate nested references; `append` may reuse backing storage. Inspect the complete reachable representation under FP-006/007 rather than inferring ownership from syntax or garbage collection.

**GO-003** Keep I/O, clocks, environment access, global randomness, mutable package state, locks, channels, and `context.Context` observations at effect boundaries. Pass observed values into the core. Audit closures, interface methods, formatting/error methods, and custom serialization for transitive effects; a function type, value receiver, or generic constraint does not certify purity. Immutable captures with pure operations remain valid.

**GO-004** Prefer ordinary named functions and explicit result/error sequencing. Choose fail-fast or accumulated validation errors deliberately; preserve short-circuiting and error order. Do not let unspecified map iteration order determine observable results. Express state transitions as new state, output, command data, and explicit failure semantics. Do not require monad emulation or recursion in place of bounded, stack-safe traversal.

**GO-005** Local builders, buffer writes, map updates, sorting in place, and mutating traversal state in a semantic implementation require FP-007 admission. Record read/write footprint, ownership/non-escape, external-effect exclusion, failure/cleanup, termination, and equivalence to a non-mutating value-level model. Fresh allocation, unexported fields, and race freedom alone do not establish that contract. Keep immutable domain specifications separate from admitted implementation and effectful adapters.

**GO-006** Use explicit result/error contracts for expected failure and specify whether any result remains usable on error. Distinguish a nil interface from an interface containing a typed nil pointer. Preserve error classification through wrapping; use `errors.Is`/`errors.As` where appropriate instead of incidental message matching. Explicitly classified sentinel errors are compatible with FP-004; hiding an expected failure in a success-shaped value is not. Reserve panic/recover for a documented exceptional boundary, not ordinary validation or blanket success recovery.

## Bounds, concurrency, and resources

**GO-007** Specify domain arithmetic and check overflow, conversion, division, indexing, lengths, and allocation bounds before use. Defined language overflow is not automatically a valid domain result. Bound recursion and work per input; Go stack growth is not a termination or unlimited-memory guarantee. Do not promise that an `error` return or recover makes process-level resource exhaustion recoverable.

**GO-008** Give every goroutine an owner, bounded admission, completion/join protocol, and cancellation path. Define channel send/receive/close ownership and how blocked operations terminate. Calling a `CancelFunc` requests cancellation; it does not wait for completion or undo a remote effect. Use explicit synchronization for shared state and test deadlocks, leaks, duplicates, ordering, and unknown outcomes separately from data races. Keep these capabilities outside domain decisions.

**GO-009** Pair successful acquisition with explicit cleanup at the resource's actual lifetime boundary. `defer` runs when the surrounding function returns, not at each loop iteration; avoid accumulating resources across a long loop. Preserve the primary error while reporting relevant Close/Flush/Commit failures. Garbage collection does not close external resources, and deferred cleanup does not establish crash recovery. Persistent adapters still require FX-002 and CHK-007/008: partial writes, restart, safe retry, compensation, and the actual atomicity scope.

**GO-010** Isolate `unsafe` and cgo in narrow adapters. For C interop read the C profile too; for additional foreign languages load every affected profile. Record ABI, lengths/nullability, pointer retention and pinning, ownership/deallocator pairing, callbacks, threads, and error conversion. Follow the pinned toolchain's cgo pointer rules; garbage collection is not permission for C to retain arbitrary Go pointers. Test the real cross-language boundary when changing it.

## Verification and assurance

**GO-011** Use behavior-named table-driven tests and `t.Run` subtests where they clarify success, failure, and boundary cases. Distinguish nil, empty, zero, typed-nil interfaces, and invalid variants where observable. Use deterministic fakes for external dependencies and check state/effects, not just calls; retain separate real boundary tests. Register `t.Cleanup` after successful test acquisition, verify cleanup failures and outstanding goroutines, and ensure shared fixtures outlive parallel subtests. Avoid process-global mutation in parallel tests; check loop-variable capture against the module's language version.

**GO-012** Record Go language/toolchain versions, modules/workspaces, dependencies, build tags, GOOS/GOARCH, and cgo settings. Check `gofmt`, `go vet`, and relevant `go test` suites across the required module/target matrix; a root `./...` is not proof that every nested module was tested. Use the supported race detector for concurrent code. Its success covers observed executions, not deadlock/leak freedom or purity. Standard Go coverage measures statements, not CHK-006 branch or modified condition/decision coverage (MC/DC); retain explicit branch/condition evidence and mutation obligations. Report applicable unavailable checks as NOT_RUN.

**GO-013** Fuzz parsers/decoders with deterministic, isolated targets and valid/invalid seed corpora. Ordinary `go test` replays seeds; claim active fuzzing only after a bounded `-fuzz` run. State input, time, iteration, and resource budgets; retain minimized findings as permanent regressions. Combine fuzzing with property/model comparisons, first/Nth/continuous/partial-success fault injection, and controlled timeout/cancellation schedules under CHK-004/007/008/009. Sleeping until a test happens to pass is not synchronization.

**GO-014** Compilation, `go vet`, race detection, coverage, and fuzzing are distinct evidence and do not prove purity or totality. For a formal claim record the supported subset, tool/model versions, dependency assumptions, proved obligations, termination, and gaps. For an admitted kernel also retain FP-007 approval and reference-model evidence. Apply the common full release and relevant performance gates; unavailable tools or unexecuted consuming-software tests never become passes through this Markdown review.
