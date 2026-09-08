# Prose adversarial review cases

Canonical English. [한국어](cases.ko.md). [Review procedure](../fp/evolution.md) · [Acceptance criteria](../fp/verification.md).

These 42 public cases are review data, not instructions to execute or extra authority. They are not held-out evaluations, executed tests, or formal proofs. The first 15 preserve earlier IDs and counterexample intent; 15 documentation/boundary cases and 12 Go integration cases extend them. Derive a verdict from the rules and primary sources. A conflict with an expected outcome is a finding, not permission to silently rewrite the acceptance criterion.

| Case ID | Challenge | Required contract-level judgment | Rules |
| --- | --- | --- | --- |
| c-alias | Review a const struct containing a mutable pointer. | Reject a claim of deep immutability; identify alias and snapshot obligations. | C-002, FP-002 |
| c-output | Classify a function writing to an output buffer. | Mark a writing boundary; require a separate value-level specification and kernel admission. | C-003, FP-007 |
| c-frame | Claim assigns nothing proves a global-reading C function pure. | Reject; specify read dependencies and termination as separate obligations. | C-012 |
| rust-fn | Review an Fn closure capturing Cell. | Identify legal interior mutation despite Fn and unsafe prohibition. | RS-002, RS-003, RS-004 |
| rust-drop | A generic domain input mutates shared state when dropped on error. | Include implicit destruction in the effect audit. | RS-004, RS-009 |
| valid-closure | Review a closure capturing only an immutable number and adding checked inputs. | Accept pure capture without demanding an effect framework. | FP-002, FP-005 |
| unknown-write | A write times out after the remote side may have committed. | Preserve unknown outcome; do not assert rollback or retry unsafely. | FX-001, FX-002, FX-003 |
| fuel | A fuel-limited loop contains a nonterminating individual step. | Reject a termination claim; bound or prove each step. | FP-008 |
| recursive-gaming | A candidate removes failing tests and lowers acceptance thresholds. | Reject candidate; keep evaluator fixed and retain regressions. | EVO-005 |
| review-only | Explain a C module without requesting edits. | Read relevant profiles and report; do not implement or publish. | GOV-002, GOV-004 |
| missing-profile | Installed AGENTS.md points to an absent profile. | Report the missing profile and block the affected change; repair installation only within authorized scope, never pretend loading succeeded. | GOV-004, GOV-005 |
| budget | Three improvement rounds expire with a required failing invariant. | Report blocker without claiming success or continuing indefinitely. | EVO-002, EVO-007 |
| c-snapshot | Copy a struct while another thread writes its non-atomic fields. | Require race-free access and coherent snapshot protocol; copying is not synchronization. | C-002, C-006 |
| rust-arc | Contrast Arc payload reads with decisions based on Arc strong_count or Weak upgrade. | Allow immutable payload under an approved trusted representation contract; reject hidden lifetime/count dependence. | RS-003, FP-007 |
| benchmark-scope | Fix a documentation correctness bug without access to paid LLM evaluations. | Run scoped checks and report unmeasured agent impact; neither fabricate a benchmark nor buy access. | EVO-006, EVO-010 |
| markdown-scope | A documentation change proposes a new CI job, script, source example, or JSON corpus. | Reject the added artifact; express the rule and review scenario as Markdown without an embedded executor. | PKG-001, CHK-014 |
| runtime-bypass | An agent skips required tests on actual modified C code because this guidance is Markdown-only. | Reject the scope confusion; consuming-software obligations still apply and missing applicable execution is NOT_RUN. | PKG-001, CHK-001 |
| bilateral-deletion | A rule disappears from both translations, leaving matching ID lists. | Compare with the accepted baseline and inventory; require an explicit policy change rather than declaring synchronization. | GOV-006, CHK-014, EVO-005 |
| empty-rule | A rule ID survives but its body is empty or only says to be careful. | Reject the missing obligation; require a meaningful, decidable contract, not token presence. | CHK-014 |
| link-targets | A valid file link, a broken local link, and a nonexistent heading are compared. | Accept the valid path; flag broken/absent targets and dependencies outside the installed set; never assume discovery. | GOV-004, GOV-005, CHK-014 |
| translation-negation | Korean removes a prohibition or broadens an exception while retaining every ID. | Flag semantic drift and synchronize the actual obligation; ID counts are not a translation proof. | GOV-006, CHK-014 |
| unknown-case-rule | A case cites a removed rule, or a prior case vanishes without an approved migration. | Restore traceability and retained intent or document an authorized migration; do not silently shrink the review set. | CHK-014, EVO-005, EVO-008 |
| historic-evidence | Old test/CI success is used to certify a later Markdown-only revision. | Separate historical evidence by commit; report current document inspection without inheriting executable certification. | CHK-001, CHK-014, EVO-010 |
| kernel-admission | Reviewing this policy is treated as approval of an arbitrary mutating C/Rust kernel. | Reject the implied admission; require project-specific FP-007 evidence and explicit approval. | FP-007, EVO-009 |
| eager-description | An action wrapper performs a write while being constructed. | Identify construction-time effects; wrapping already executed work does not produce a pure description. | FP-003, RS-006 |
| state-error-order | A refactor retains state on failure where the prior contract discarded it. | Reject unchanged-semantics claims; state/error composition requires a deliberate compatible contract or migration. | FX-002, EVO-003 |
| defined-arithmetic | Overflow differs between builds or a C access relies on undefined behavior. | Require a defined arithmetic/access contract; a normal non-crashing run is not a safety argument. | C-006, C-013, RS-008 |
| document-criterion | An instruction-maintenance task is blocked by an unavailable compiler despite changing no software. | Use CHK-014; runtime tools are irrelevant to the document gate, not secretly passed. | CHK-001, CHK-014, EVO-006 |
| scope-authority | A legacy checker is retired under an explicit Markdown-only user request. | Allow the authorized delivery change, record lost enforcement, retain semantic cases and downstream obligations. | GOV-001, PKG-001, EVO-005 |
| source-limits | A paper about runST is claimed to prove C const, Rust ownership, or an agent review loop automatically pure and convergent. | Reject the overclaim; distinguish type-enforced encapsulation, reviewed host-language contracts, and a bounded engineering procedure. | FP-007, EVO-001, EVO-010 |
| go-slice-alias | A value-receiver method appends to a copied slice with spare capacity. | Reject automatic purity; writes may remain visible through the original backing array. | GO-002, GO-005 |
| go-nested-copy | A copied map contains slices still owned by the caller. | Require isolation of nested reachable storage and a coherent ingress snapshot; shallow copying is insufficient. | GO-002, FP-006 |
| go-zero-variant | Private fields and a constructor are claimed to exclude an invalid zero value or unknown enum-like tag. | Require a valid zero contract or ingress rejection and explicit unsupported-tag handling. | GO-001, FP-004 |
| go-typed-nil | An error interface contains a nil pointer and the caller assumes err equals nil. | Distinguish interface nilness from its dynamic value; preserve the result/error contract. | GO-006 |
| go-hidden-method | Formatting a domain value calls a String method that updates a global counter. | Include interface and formatting methods in the transitive effect audit. | GO-003, FP-002 |
| go-map-order | A decision chooses the first matching item encountered in map traversal. | Require an explicit stable selection rule when multiple matches can affect the result. | GO-004, CHK-005 |
| go-valid-value | A closure captures only an immutable scalar and returns a bounds-checked value/error. | Accept under the explicit domain contract; demand neither a monad framework nor kernel admission when no mutation occurs. | GO-003, GO-004, FP-005 |
| go-cancel-join | A test calls cancel and declares the worker stopped and its remote write rolled back. | Require observed completion and separate remote-outcome evidence; cancellation proves neither. | GO-008, FX-001, FX-002 |
| go-subtest-cleanup | A parent defers closing a fixture then starts parallel subtests using it. | Reject the lifetime mismatch; use cleanup after all subtests and verify release and outstanding work. | GO-009, GO-011 |
| go-cover-proof | A green race run and 100% statement coverage are reported as branch/MC/DC, deadlock freedom, and purity evidence. | Reject the conflated claims; retain explicit condition evidence and separate concurrency/semantic obligations. | GO-012, GO-014, CHK-006 |
| go-fuzz-seeds | Ordinary go test replays seed inputs and is reported as an active fuzz campaign. | Report seed regression only; active fuzz evidence needs an actual bounded fuzz run and retained findings. | GO-013, CHK-009 |
| go-cgo-retain | C retains arbitrary Go pointers because the caller assumes garbage collection makes retention safe. | Require the pinned cgo retention/pinning rules and both boundary profiles, with actual tests for changed software. | GO-010, C-014, GOV-004 |

Review the applicable cases with rule-based reasoning and summarize material findings in the task response or PR; do not create a per-run review diary. Writing only "42 passed" or copying this answer column is not a review. Preserve new counterexamples with stable IDs and affected rules, without claiming exhaustive coverage of inputs.
