# Evidence-gated recursive improvement

Canonical English. [한국어](evolution.ko.md). Apply with [common rules](../AGENTS.md) and [verification](verification.md). Public seed cases: [evaluation corpus](../evals/cases.json).

**EVO-001** Recursive improvement means repeating a bounded propose/test/review cycle on code, contracts, or instructions. It is not permission for autonomous self-modification, deployment, merging, or changing the user's goal. A proposal is immutable review data until authorized and accepted. Function recursion, fixed-point semantics, and this engineering process are different concepts; Haskell papers do not prove this process converges or improves agents.

**EVO-002** Freeze the parent commit, accepted requirements, rule IDs, oracle/acceptance criteria, input corpus, language/toolchain, and authorized scope before each candidate. State one falsifiable hypothesis and choose a bounded budget (by default three substantive repair rounds per task). Record the baseline result and uncertainties before judging the candidate.

**EVO-003** Express module changes against small stable contracts and a pure reference relation. Change one cause at a time; compare public values, error/state/effect traces, and resource obligations. Compatible implementations may evolve recursively behind the contract. A contract change is a versioned migration with its own approval and downstream compatibility review, not a hidden refactor.

**EVO-004** Separate attacker and defender passes. The attacker supplies rule IDs, counterexamples, severity, evidence, and reproduction steps; the defender must reproduce or refute with evidence, not agreement. Recheck the changed surface and adjacent invariants after each repair. Record whether passes were one model's sequential self-review, separate sessions, separate agents, or human review; do not fabricate independence.

**EVO-005** Keep the incumbent evaluator/oracle fixed while evaluating a candidate. Do not remove regressions, lower thresholds, change exclusions, edit held-out tasks, or relabel unsupported checks to get a pass. If the evaluator is itself wrong, first record the defect and separately approve/version the evaluator correction; rerun baseline and candidate under that same revision. A weaker contract requires explicit user approval, not recursive optimization.

**EVO-006** For instruction changes use public development regressions plus independently supplied held-out tasks. Keep model snapshot, reasoning settings, tools, repository state, and budgets matched; repeat runs and report variance. Measure task correctness, purity violations, authority violations, truthful evidence reporting, code/abstraction growth, and cost. Compare cost only among candidates that meet the unchanged mandatory quality gates. Corpus presence and checker tests are not executed LLM evaluations.

**EVO-007** Accept only authorized candidates with no unresolved findings in the stated scope and no known required-contract regressions. Preserve counterexamples, commands, outcomes, source links, and the exact commit. Stop after a clean full scoped recheck; do not keep changing a passing candidate merely to perform more rounds. Repeated candidates, no progress, or budget exhaustion with unresolved findings require a blocker report rather than silent relaxation or an infinite loop.

**EVO-008** Retain the accepted parent, a rollback plan, and a ledger of hypothesis, evidence, decision, and remaining limitations. When new evidence appears, add a reproducer and start a new bounded cycle; re-evaluate affected callers, translations, docs, and checkers. Synchronize bilingual rule IDs and meaning; IDs support traceability, not equivalence proof.

**EVO-009** Before approving a kernel or profile change, test at least: hidden C aliases, writes through an output buffer, hidden Rust interior mutability, effectful callbacks/destructors, eager action construction, overflow, nontermination, unknown external outcomes, evaluator gaming, and improper document loading. Also test valid immutable closures/value functions so over-restrictive rules cannot silently win.

**EVO-010** The maintenance ledger must distinguish facts from proposals: what ran, what was only inspected, what is out of scope, and what remains unverified. A clean scoped review is not a guarantee of all future code, a formal proof, or demonstrated coding-agent improvement. Do not publish benchmark wins without matched executions and preserved results.
