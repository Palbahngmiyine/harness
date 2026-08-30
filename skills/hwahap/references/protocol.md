# Hwahap protocol

This is the execution contract behind the entrypoint. Sol supplies a read-only
planner and the sole orchestrator, Luna supplies the job executor and
independent reviewer, and Terra supplies the feature-scope reviewer. Only the
Sol orchestrator writes `.hwahap` state; no other role writes state, and
reviewers never edit source files.

All state commands below use the `<absolute-hwahap-skill-dir>/scripts/hwahap` launcher. Direct execution of
`hwahap_state.py` is outside the official security boundary; embedding callers
must supply an isolated, validated interpreter and clean module environment.

The launcher is used only through its absolute path from the loaded skill.
Copied, hard-linked, symlinked, or replaced entrypoints are outside the
security boundary. Its trust roots are `/bin/sh`, the launcher and adjacent
state script, kernel file-system semantics, and the selected absolute Python
interpreter and standard library. It does not pin state data; same-UID
concurrent replacement and a stronger native or signed bootstrap are out of
scope.

## Exact sequence

1. Select one authoritative input. An explicitly supplied approved PR/FAQ uses
   `status: prfaq` and `init --spec`. A current user instruction that clearly
   requests implementation uses an internal credential-free capsule with
   `status: request`, `confirmed_at`, and a concise title under
   `.hwahap/requests/`, then `init-request --request`. Ideas, grilling, and
   planning-only text are not direct-request authority. Return
   `HW_SPEC_UNCONFIRMED` or `HW_REQUEST_UNCONFIRMED` for invalid selected input.
2. Install the exact six project profiles. Spawn only the Sol orchestrator. It
   calls `get_goal`; if there is no active Goal, it calls `create_goal`
   automatically with the current implementation objective and then calls
   `get_goal` again. A conflicting active Goal returns
   `HW_USER_DECISION_REQUIRED`; unavailable or failed Goal creation returns
   `HW_GOAL_REQUIRED`. Then run the selected initializer once. A non-zero result
   is a stable failure:
   record its code and bounded evidence, then stop unless a defined recovery is
   safe and in scope.
3. Record the normalized bound Goal receipt with `goal-sync --mode bound`.
   Direct-request mode cannot lock before this succeeds. Spawn the read-only Sol
   planner, collect its six-list contract and atomic-unit proposal, and end the
   planner before any Luna writer starts. The Sol orchestrator fills every
   required list while it remains unlocked. Run
   `<absolute-hwahap-skill-dir>/scripts/hwahap lock`; the command records the canonical
   contract digest and first state transition. The locked contract is the sole
   authority for goals, non-goals, paths, forbidden changes, acceptance
   criteria, and test commands.
   Link objective, non-goals, proof, and checkpoint to this locked contract.
   Local state and Goal binding cannot expand scope or authority. Once history contains a
   `bound` receipt, `goal-sync` cannot append `no_active_goal` or
   `unavailable`; subsequent bound receipts and `goal-complete-sync` retain
   the original Goal `thread_id` and `objective_sha256`.
   A bound sync may include `--token-total <nonnegative-int>`; without it, and
   for unbound modes, token usage remains unavailable. The value is valid only
   when the matching Goal receipt records the same source and `token_total`.
4. After the lock, split the goal into atomic units. Create each with
   `<absolute-hwahap-skill-dir>/scripts/hwahap add-unit`, then use `<absolute-hwahap-skill-dir>/scripts/hwahap transition` for every
   state change. Give Luna only the current unit's contract. `add-unit` rejects
   unsafe IDs, paths, and commands containing sensitive data as `HW_STATE_INVALID`
   without writing. At most one unit may be unresolved at a time; unresolved
   means any status other than `planned` or `passed`, including
   `implementing`, `reviewing`, `recovery`, `replan_required`, and terminal
   failure states. Planned future units may coexist, but a different unit
   starts only when every other unit is `planned` or `passed`, so the next new
   unit starts only after the current unit passes; the same unit may resume from
   `recovery` or `replan_required`. A safe but non-member path or command
   records
   `contract_locked -> awaiting_user` with `HW_SCOPE_DRIFT`, asks the user for
   an approved new Goal/contract or corrected in-scope unit, and creates no
   unit. Out-of-contract commands are SHA-256 digests only; failed writes or
   validation restore both state files byte-for-byte.
5. Luna implements exactly one user-observable change and returns a compact
   preliminary envelope; this is not an official acceptance receipt. Locked
   acceptance commands are definitions, not execution permission. The
   compatibility `run-test` command always returns
   `HW_TEST_EXECUTION_DISABLED` before reading state, parsing the locked test
   command, or creating a process.
   Only the independent Luna verifier may run a normal Codex `exec_command`
   when it stays within locked paths and existing authority and needs no
   external write, network, or extra permission. If that is unclear, it
   returns `HW_USER_DECISION_REQUIRED`. Sol records the verifier result with
   `record-test-receipt` while the run and unit are `reviewing`. The receipt
   computes source `codex.exec_command`, role `verifier`, command digest,
   occurrence-based ID, and `pass|fail|timeout`, and stores execution receipt
   digest, verifier thread, full six-field `diff_snapshot`, output digest,
   times, and exit code. Raw command, stdout, stderr, and environment are
   never stored. A
   `record-test-receipt` call must include `--base-commit <40-hex-commit>` and
   `--target-commit <40-hex-commit>`; the command computes the full snapshot
   from those committed objects.
   passed unit requires the latest pass for every command and the matching
   latest passing unit-review Luna verifier thread/full snapshot; completed
   `test_runs` is derived from receipts.
6. Sol computes one full six-field `diff_snapshot` from the committed base and
   target and sets the unit to `reviewing`. No official test receipt exists yet.
   It contains `base_commit`, `target_commit`, `base_tree`, `target_tree`,
   `diff_digest`, and nonempty `changed_paths`. Commits are exact lowercase
   40-hex objects at the workspace's Git top-level; the canonical binary diff
   uses fixed `--full-index --binary --no-ext-diff --no-textconv --no-color
   --diff-algorithm=myers --no-indent-heuristic --unified=3 --src-prefix=a/
   --dst-prefix=b/ --no-renames` flags and isolated Git configuration. Dirty
   working-tree bytes are ignored.
   Non-Git workspaces, subdirectories, missing objects, or changed paths outside
   the unit fail closed as `HW_STATE_INVALID`. Before any final-review claim is
   accepted, every nonempty snapshot path must match locked `allowed_paths`, the
   union of passed-unit `allowed_paths`, and no `forbidden_changes` rule; the
   user must correct the scope or approve a new Goal/contract after a failure.
7. After the Luna job executor has ended, spawn the separate Luna reviewer
   (`gpt-5.6-luna`, `xhigh`) and Terra feature-scope reviewer
   (`gpt-5.6-terra`, `xhigh`) before waiting for either. Give both the
   same locked contract and the same full snapshot; run them in parallel.
   Installing six profiles does not authorize six live agents. With a four-slot
   limit including the invoking root, keep root and orchestrator, then use at
   most two child slots. Planner, job executor, and final reviewer run in
   separate phases; only Luna/Terra unit review is concurrent. Never spawn a
   replacement until the prior child is completed or explicitly interrupted.
8. Wait for both envelopes. Advance only when both are `pass`, their thread IDs
   are distinct, their actual model/effort values match the role contract, and
   their `sha256:` digests match. Record them in the unit's append-only
   `review_history` with changed paths and bounded evidence. Before the run can
   enter `final_review`, every unit must be `passed`; every acceptance command
   must have a latest `pass` receipt; and each latest receipt must match that
   unit's latest passing Luna verifier thread and full snapshot.
   Passed units are ordered by their `unit -> passed` events in `events.jsonl`,
   not by unit filenames. Their snapshots must form one adjacent Git chain:
   each next unit's base commit/tree must equal the previous unit's target
   commit/tree. Every final-review attempt snapshot must begin at the first
   unit's base and end at the last unit's target, including failed or
   unavailable probes; missing, duplicated, or
   mismatched pass-event mappings fail closed, even while the final-review
   attempt list is still empty or contains only an unavailable/unsupported
   model probe.
9. A review round fails if either reviewer fails; two failures in the same round
   still count as one failed round. After every failed round, Sol invokes
   `record-improvement` with a valid recorded failure signature, new strategy
   digest, verifiable hypothesis, bounded action, and evidence. The same
   signature may be used with a different strategy. The first record is
   `terra_recovery` from Terra's cause/recovery evidence; the second is
   `sol_replan`; the third and later records are `recursive_improvement`.
   The external Goal is the durable objective and verified stop condition. The
   loop has no fixed failure-count ceiling: after Terra recovery and Sol replan,
   continue only with new-evidence recursive improvements. A repeated blocker
   without a new hypothesis, or any scope/authority/cost change, goes to
   `awaiting_user` without completing the Goal.
10. The command atomically appends the improvement and transition event,
    validates the unit, and rolls back both unit and event files on failure.
    The first transition is `reviewing -> recovery`; subsequent transitions are
    `reviewing -> replan_required` and carry `HW_REPLAN_REQUIRED`, reason,
    evidence, and recovery action. Reusing a signature/strategy pair, having no
    new strategy, or expanding locked scope, authority, or cost moves the unit
    to `awaiting_user`. A terminal
    user gate may retain the last failed round without an improvement when its
    failure record is complete.
    For the F34/F35 correction rule, a verifiable new hypothesis permits Sol to
    continue correction on the same unit within locked scope; without one or
    when scope/authority must expand, use `awaiting_user`. This general rule
    does not define recursive final-review behavior.
    Run terminal states include `awaiting_user`. After any terminal run state,
    unit creation, unit mutation, test-receipt recording, and improvement
    recording are forbidden. The event validator also rejects every unit
    successor event after a terminal run.
11. Never implement scope drift. Set the run/unit to `awaiting_user` with
    `HW_SCOPE_DRIFT` or `HW_USER_DECISION_REQUIRED`, plain reason, evidence,
    and next action. A critical security fix may proceed only when it is
    goal-contained, has bounded allowed paths, and has tests. If it needs a new
    unit, path, or scope, record `security_deferred`, finish the original work
    only if safe, report it separately, and await the user's decision.
12. After the entry gate in step 8 is satisfied, set `final_review` and attempt
    one Sol final reviewer (`gpt-5.6-sol`, `ultra`). Every Sol attempt,
    including an `unavailable` or `unsupported` Ultra attempt, must contain the
    same valid full final `diff_snapshot`. If Ultra is unavailable or unsupported,
    keep `final_review` pending and use xhigh exactly once as fallback, recording
    the reason. Only an aggregate failure awaits the user: use
    `HW_FINAL_REVIEW_FAILED` when the final result fails, and
    `HW_MODEL_UNAVAILABLE` when the xhigh fallback is unavailable or unsupported.
    Do not retry after an aggregate failure. Record either one Ultra pass
    attempt, or one Ultra unavailable/unsupported attempt followed by one xhigh
    attempt.
13. When the final reviewer passes, Sol may return zero or more post-completion
    improvement candidates with the pass evidence. While the run is still in
    `final_review`, record each one with the exact
    `record-improvement-candidate` command in
    [state-contract.md](state-contract.md), including all six causal fields.
    The command stores `status: proposed` and is report-only. Do not run the
    proposed action, create a new Goal, or expand the locked scope; no candidate
    is also valid. A new-scope candidate stays report-only; after completion,
    ask the user to approve a new Goal/contract before any separate work. A
    candidate cannot be recorded before `final_review` or after the run is
    terminal.
14. After recording any candidates, invoke `<absolute-hwahap-skill-dir>/scripts/hwahap complete` with
    `--actor`, `--reason`, `--input-digest`, and one or more `--evidence-ref`
    values. `--input-digest` must exactly equal the verified digest in the sole
    passing final-review snapshot. It computes completed metrics, appends the final transition,
    generates and validates canonical `report-data.json` and fixed
    `report.html`, and records the official-guidance Material 3 receipt and separate file digests
    atomically. A generic transition to `completed` is forbidden. Run
    `validate` after completion, then and only then call external
    `update_goal(complete)` when a Goal is bound. A local Goal or report never
    expands scope or authority.

After local completion, record the external result with
`goal-complete-sync --sync-result completed|already_completed|failed`.
Successful results require `--token-total <nonnegative-int>` and bind the
final value to the `codex.update_goal` receipt. `failed` forbids that flag and
preserves the previous exact token receipt. The command regenerates the
allowlisted report, validates its source/file digests, changes no transition
event, and rolls back `run.json`, `report-data.json`, and `report.html`
byte-for-byte on failure. A bound recovery journal and run marker support
same-process or next-entry recovery; the journal alone never mutates state.

## Review and report continuation

Continue with [protocol-review.md](protocol-review.md) for atomic-unit envelopes, final reporting, and receipt rules.
