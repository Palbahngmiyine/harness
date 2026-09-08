# Verification contracts

Canonical English. [한국어](verification.ko.md). Apply with [common rules](../AGENTS.md); policy changes also require [evolution](evolution.md).

**CHK-001** Before implementing, record the affected rule IDs, input domain, observable outputs/errors/state/effects, required checks, tool versions, and completion criterion. Use states `PASS`, `FAIL`, `NOT_APPLICABLE(reason)`, `NOT_RUN(reason)`, or `APPROVED_EXCEPTION(reference)`. An exception is not a pass; unresolved mandatory obligations block the affected completion/release claim.

**CHK-002** Map semantic, memory, termination, resource, and concurrency claims separately to evidence. Keep a trusted-boundary record: component/version, accepted contract, assumptions, verifier and proved obligations, dynamic tests, gaps, and approver. A proof establishes its stated property under its model; annotations, lint success, or tests are not interchangeable evidence tiers.

**CHK-003** Test changed behavior with success, failure, empty/absent/zero/min/max/out-of-range inputs and every reachable branch. Every bug fix needs a reproducer that fails on the baseline and passes after the fix. Validate invariants and actual state/effects, not merely an error code or mock call. Keep unrelated concerns in separate tests.

**CHK-004** Test the core without real I/O. Use independent example tests, property/model tests, and a simple pure reference for optimized/admitted kernels. Generators must represent valid/invalid domains and transition histories; enforce input-class coverage and bound discards. Shrinkers preserve the property's relevant precondition/failure category, not necessarily validity for invalid-input tests. Reject vacuous properties and expected values derived from the implementation itself.

**CHK-005** Specify the applicable laws and their preconditions before testing custom abstractions or algebraic refactors. Verify identity, composition, associativity, round trips, and idempotence where meaningful; do not impose false laws on floating point, partiality, or effect ordering. Test canonicalization and deterministic serialization independently of allocation addresses or incidental traversal order.

**CHK-006** Target 100% branch coverage on the core; enumerate uncovered and genuinely unreachable cases with evidence. Apply MC/DC to compound Boolean decisions. Use mutation testing to exercise branch, boundary, and state-update faults; classify surviving mutants including equivalent mutants. Never delete defense code, relax assertions, or exclude a path just to improve a metric. Unsupported tools are `NOT_RUN`, not automatically irrelevant.

**CHK-007** Inject first-call, Nth-call, continuous, and partial-success failures in dependencies that exist. Include timeout, cancellation, allocation/storage exhaustion, partial acquisition, and cleanup failure. Check state consistency, ownership, actual effects, and outstanding work. Test duplicate/stale acknowledgements and unknown remote outcomes; local rollback is not a remote rollback test.

**CHK-008** For concurrent systems test controlled schedules plus stress, races, deadlocks, task leaks, duplicate effects, and ordering. For persistent systems test partial writes, forced exit, restart, atomicity scope, safe retry, compensation, and recovery. For parsers/decoders fuzz for panic/crash/nontermination/resource exhaustion. Preserve minimized findings as permanent regressions with inputs, seeds, and execution order.

**CHK-009** Control clocks, random seeds, and scheduling instead of sleep-based assertions. Set input, iteration, memory, and time budgets for fuzz/mutation/stress work. A finite successful run does not prove the absence of other executions. A budget exhausted before a required obligation is met must be reported, not recast as success.

**CHK-010** Use available type/effect/dependency checks and analyzers for the language profile. Add accepted examples and intentional violations to test the checker itself; a negative test must fail for the expected reason, not an unrelated compile error. Include indirect calls, nested mutable values, and missing required documents. Regex/symbol scans can be useful tripwires but must not be called a sound purity checker.

**CHK-011** Separate fast change/pre-commit and full pre-release suites. Full verification runs applicable supported address, memory, undefined-behavior, race, and leak analyzers in compatible builds. Maintain supported OS/architecture/endianness/compiler/feature matrices; compare unoptimized, optimized, and production results. Required invariants remain active in production. Document unsupported target/tool combinations and their effect on the gate.

**CHK-012** Benchmark representative runtime, allocation, peak live memory, stack depth, and throughput where applicable. Use matched inputs/toolchains; preserve required short-circuiting, stream productivity, error order, and cleanup behavior. Approval of a faster kernel requires the unchanged semantic oracle plus the FP-007 evidence/approval, not just a speed number.

**CHK-013** For every release candidate rerun the full required regressions and create a concrete human checklist: changed user-visible workflows, actual security implications, measured performance, compatibility, and rollback/recovery steps, each with method/evidence/verdict. Review is not complete merely because a checklist is mentioned. Do not manufacture unrelated risks or approval work.

**CHK-014** This package's checker validates required paths, Markdown links, stable IDs and bilingual ID parity, text hygiene, and source-file length. Its native probes demonstrate selected contracts and legal impurity counterexamples. These checks do not establish translation equivalence, whole-program purity, memory safety of clients, termination proofs, or agent performance. Report each of those as a separate review or unperformed activity.
