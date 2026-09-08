# Sources and policy rationale

Checked 2026-09-08. This file is explanatory evidence, not another instruction authority.
The English rules are normative; Korean files mirror their rule IDs. Links below identify primary sources.
The policy is an engineering synthesis: no cited paper mandates a 100-line file limit, proves C/Rust pure by default, or proves recursive agent improvement converges.

## Functional foundations

- **S1 — John Hughes, Why Functional Programming Matters (1989).** [Author's university-hosted reprint](https://www.cs.kent.ac.uk/people/staff/dat/miranda/whyfp90.pdf), introduction and higher-order-function sections. Modular decomposition and composition motivate FP-005/006; a ban on assignment alone is not its central benefit.
- **S2 — Haskell 2010 Report.** [Chapter 7, I/O](https://www.haskell.org/onlinereport/haskell2010/haskellch7.html), [chapter 3, expressions/errors](https://www.haskell.org/onlinereport/haskell2010/haskellch3.html), [chapter 5, abstract datatypes](https://www.haskell.org/onlinereport/haskell2010/haskellch5.html). Action descriptions versus execution, abstraction boundaries, and partiality motivate FP-001/003/004/008. Haskell admits nontermination; a type named IO in another language is not the same guarantee.
- **S3 — Launchbury and Peyton Jones, Lazy Functional State Threads (PLDI 1994).** [Publication](https://www.microsoft.com/en-us/research/publication/lazy-functional-state-threads/), [paper, section 2.4](https://www.microsoft.com/en-us/research/wp-content/uploads/1994/06/lazy-functional-state-threads.pdf), [modern ST interface](https://hackage.haskell.org/package/base/docs/Control-Monad-ST.html). Parametric state encapsulation motivates FP-007. Our C/Rust audited-kernel admission is explicitly weaker than type-enforced runST unless a separate proof closes that gap.
- **S4 — McBride and Paterson, Applicative Programming with Effects (2008).** [Author-hosted manuscript, sections 3 and 5](https://www.staff.city.ac.uk/~ross/papers/Applicative.pdf). Independent structure versus result-dependent sequencing motivates FP-005 and RS-005. Applicative alone implies neither parallelism nor error accumulation; effect ordering remains meaningful.
- **S5 — David Turner, Total Functional Programming (2004).** [J.UCS paper](https://www.jucs.org/jucs_10_7/total_functional_programming/jucs_10_07_0751_0768_turner.pdf). Finite-data termination and codata productivity motivate FP-008. Bounded fuel is a project adaptation and only works with terminating individual steps.
- **S6 — QuickCheck official API.** [Test.QuickCheck](https://hackage.haskell.org/package/QuickCheck/docs/Test-QuickCheck.html), generator/shrinker, cover/checkCoverage sections. Distribution enforcement and useful shrinking motivate CHK-004/009. Random tests and mere labels are not universal proofs.

## C semantics and verification

- **S7 — WG14 N1570, C11 committee draft (2011), not the final latest ISO edition.** [Official draft](https://www.open-std.org/jtc1/sc22/wg14/www/docs/n1570.pdf), sections 5.1.2.4, 6.2.6.1, 6.5, 6.7.3, 6.7.3.1, 7.2. Object representations, defined accesses, qualifiers/restrict, and NDEBUG underpin C-002/006/007/008/009. Each consuming project must pin its actual language version and target; this document does not prescribe C11 forever.
- **S8 — GCC function attributes.** [Official reference](https://gcc.gnu.org/onlinedocs/gcc/Common-Function-Attributes.html), pure/const. Optimizer assumptions are not an effect verifier (C-005).
- **S9 — Frama-C.** [ACSL overview](https://www.frama-c.com/html/acsl.html), [WP plugin](https://www.frama-c.com/fc-plugins/wp.html). Contracts, frame conditions, invariants, variants, and proof obligations motivate C-012. A write frame alone does not constrain all reads or establish termination; axioms and callee models belong to the trusted base. No Frama-C proof is claimed by this package.

## Rust semantics and verification

- **S10 — Rust Reference and standard library.** [Interior mutability](https://doc.rust-lang.org/reference/interior-mutability.html), [UnsafeCell](https://doc.rust-lang.org/std/cell/struct.UnsafeCell.html), [Fn](https://doc.rust-lang.org/std/ops/trait.Fn.html), [Arc](https://doc.rust-lang.org/std/sync/struct.Arc.html), [undefined behavior](https://doc.rust-lang.org/reference/behavior-considered-undefined.html). These distinguish access/alias safety from effect freedom (RS-002/003/004).
- **S11 — Rust resource and ABI contracts.** [Destructors](https://doc.rust-lang.org/reference/destructors.html), [Future](https://doc.rust-lang.org/std/future/trait.Future.html), [Rustonomicon FFI](https://doc.rust-lang.org/nomicon/ffi.html). Implicit destruction, deferred computation, and foreign ownership/unwinding motivate RS-006/009/010/011. Dropping work is not proof of external rollback.
- **S12 — Ho and Protzenko, Aeneas: Rust Verification by Functional Translation (2022).** [Research paper](https://arxiv.org/abs/2206.07185). Functional translation of supported Rust provides a route to proving functional properties; the stated approach excludes unsafe and interior mutability. This motivates RS-007/014 without asserting that the tool verifies arbitrary Rust or is installed here.
- **S13 — Rust dynamic/static tools.** [Miri authors' documentation](https://github.com/rust-lang/miri/blob/master/README.md), [Cargo Clippy documentation](https://doc.rust-lang.org/cargo/commands/cargo-clippy.html). Miri explores particular supported executions and cannot establish soundness universally; Clippy catches classes of mistakes. Neither proves purity (RS-012/013).

## Agent instructions and iterative evaluation

- **S14 — OpenAI model guidance.** [Latest-model guide](https://developers.openai.com/api/docs/guides/latest-model), lean prompts and autonomy/approval boundaries. State rules once, route relevant details, distinguish review from implementation, and compare changes on representative tasks (GOV-002/004, EVO-002/006). Runtime model/reasoning configuration is not changed by prose in AGENTS.md.
- **S15 — OpenAI AGENTS.md discovery.** [Official guide](https://developers.openai.com/codex/guides/agents-md), instruction hierarchy, fallback names, and combined byte budget. Links are not automatic loading; install the linked package and verify the client actually reads it (GOV-005).
- **S16 — OpenAI evaluation guidance.** [Evaluation best practices](https://developers.openai.com/api/docs/guides/evaluation-best-practices). Task-specific representative evaluation and retained regressions motivate EVO-005/006/010. Public seed cases are development data, not independently held-out evaluation, and no agent benchmark has been run here.

## Deliberate policy choices

- The previous type-only internal-mutation rule is refined into a recorded admission/assurance contract. Strict immutable domain specifications remain the default; audited C/Rust kernels are never described as compiler-proven runST equivalents.
- The instruction-document line cap is removed, while the source/test/script 100-line policy is retained. The package is Markdown-only; direct review cannot automatically enforce that policy in downstream code.
- Branch coverage, MC/DC, failure injection, analyzer matrices, and release gates preserve the prior testing requirements with explicit applicability and unrun states.
- C snapshot creation needs race-free access and a coherent multi-field protocol; copying alone does not provide either. Rust Arc reference counting can be trusted representation bookkeeping, but reference counts and Weak liveness cannot become hidden inputs to domain results.
- Sequential attacker/defender review is permitted but must be labelled honestly. A clean scoped recheck is a stopping condition, not proof that no future issue can exist.

## Markdown-only maintenance scope

The user explicitly replaced the previous executable package with Markdown-only guidance. The prose [review cases](../evals/cases.md) and CHK-014 checklist preserve counterexample intent, not the removed checker's enforcement strength. Downstream software still needs its applicable tests and proofs; a document-only change needs a document-only verdict. Historical executions belong to their original commits, not the current artifact. This scope change is authorized, not a claim that deleting tests improves correctness.
