# Verification contracts

Canonical English. [한국어](verification.ko.md). Apply with [common rules](../AGENTS.md); policy changes also require [evolution](evolution.md).

## Select the review scope

For instruction maintenance, inspect Markdown contracts, examples expressed in prose, links, translations, and sources. Apply CHK-001, CHK-014, and evolution; assess the correctness of the other rules as text. No C/Rust build, proof tool, installed checker, or LLM benchmark is needed to complete this document review.

For actual consuming-software changes, apply CHK-001 through CHK-013 and the relevant language profiles. The Markdown-only restriction on this package is not permission to skip that software's mandatory tests. A package review establishes only what was inspected, never execution results for an unmodified downstream project.

**CHK-001** Record scope, baseline revision, affected rule IDs, inputs/observations, acceptance criteria, and the evidence actually available. Software changes additionally record language/tool versions and mandatory execution gates. Use `PASS(scope, evidence)`, `FAIL(reason)`, `NOT_APPLICABLE(reason)`, `NOT_RUN(reason)`, or `APPROVED_EXCEPTION(reference)`. PASS for a document means the specified text checks passed, not that a program was tested. An exception is not a pass; unresolved mandatory obligations block only the affected claim. Do not confuse a tool absent for applicable work with a tool irrelevant to documentation-only work.

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

**CHK-014** Maintain the package by direct Markdown review. Follow the inventory and checklist below, compare with the accepted baseline, and record findings against exact paths and rule IDs. A prose scenario is a reasoned contract check, not an executed regression test. There is no bundled checker, native probe, or dedicated CI gate. Structural agreement alone establishes neither semantic equivalence nor automatic enforcement.

## Markdown review inventory

| Canonical document | Required rule IDs | Count |
| --- | --- | ---: |
| [Common contract](../AGENTS.md) | GOV-001–006; FP-001–008; FX-001–004; VER-001–003; PKG-001 | 22 |
| [C profile](../profiles/c.md) | C-001–014 | 14 |
| [Rust profile](../profiles/rust.md) | RS-001–014 | 14 |
| [Verification](verification.md) | CHK-001–014 | 14 |
| [Evolution](evolution.md) | EVO-001–010 | 10 |

The inventory contains 74 canonical rules. Each has one nonempty definition and an equivalent definition with the same ID in its Korean counterpart. Merely deleting the same rule in both languages is not synchronization. Changes to this inventory need the same rationale and authorization as the corresponding policy change; the count is traceability metadata, not a quality score.

## Direct review checklist

| Check | Required observation |
| --- | --- |
| Artifact scope | Compare final changed paths with the accepted base: only Markdown guidance artifacts; no runner or workflow introduced. Check embedded instructions do not regenerate removed code. |
| Loading and links | Follow each local link and any heading target within the installed document set; confirm required profiles exist, no stale execution dependency remains, and conditional loading reaches needed rules. Do not assert actual client loading without observing it. |
| Rules | Check every inventory ID, substantive body, applicability, exception, and cross-reference against the baseline. Duplicate/missing IDs and empty or weakened obligations require a finding. Check UTF-8 text, line endings, final newline, trailing whitespace, and conflict markers without confusing formatting with semantics. |
| Translation | Compare each rule/case meaning, especially MUST, negation, exceptions, approval, evidence, and termination. Matching IDs or line counts is insufficient. |
| Semantics | Challenge hidden effects, aliases, constructors, state/failure ordering, totality, cleanup, and lawful composition using the relevant primary sources. Keep normative changes separate from explanatory notes. |
| Cases | Review the prose [cases](../evals/cases.md), preserve earlier case IDs and intent, and add newly found counterexamples. Derive the decision from rules and sources, not merely by copying the expected answer. |
| Evidence | Separate textual review, actual execution, assumptions, and unavailable evidence. Old CI or test results do not certify a later Markdown-only revision. |
| Closure | Recheck the whole affected scope and both translations after repairs; record finding dispositions and limits. A clean recheck ends this cycle, not all future investigation. |

## Review record fields

Record the baseline and candidate identity, scope, reviewer arrangement, fixed acceptance criteria, inspected files/sources, case IDs and reasoned outcomes, findings with exact wording, repairs, recheck results, unresolved items, and scope limitations. Identify the exact submitted commit in the PR after it exists rather than inserting a self-referential commit hash into its own file. Use PASS only with its stated evidence scope. Record a missing/blocked item explicitly; do not fill in successful results in advance.
