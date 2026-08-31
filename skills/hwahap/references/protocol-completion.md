# Hwahap protocol: completion

After step 11 in [protocol.md](protocol.md), follow this completion sequence.

1. After the entry gate in step 8 is satisfied, set `final_review` and attempt
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
2. When the final reviewer passes, Sol may return zero or more post-completion
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
3. After recording any candidates, invoke `<absolute-hwahap-skill-dir>/scripts/hwahap complete` with
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
