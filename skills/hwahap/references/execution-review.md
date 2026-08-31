# Hwahap execution and review

## Roles and units

After installation, the normative activation list is exactly these six source
Hwahap role names, activated in this staged order:
1. `hwahap-sol-orchestrator`
2. `hwahap-sol-planner`
3. `hwahap-luna-implementer`
4. `hwahap-luna-verifier`
5. `hwahap-terra-scope-reviewer`
6. `hwahap-sol-final-reviewer`

- `hwahap-sol-orchestrator` (`gpt-5.6-sol`, `xhigh`) is the sole orchestrator
  and only `.hwahap` state writer; it delegates and never implements source.
- `hwahap-sol-planner` (`gpt-5.6-sol`, `xhigh`) is read-only and proposes the
  bounded six-list contract and atomic units; planner activation is mandatory and
  cannot be skipped, merged, or deferred past a Luna writer.
- `hwahap-luna-implementer` (`gpt-5.6-luna`, `high`) is the only implementation
  writer. Its test output is preliminary evidence, not an official acceptance
  receipt. Run no more than one writer at a time; it never edits `.hwahap`.
- `hwahap-luna-verifier` (`gpt-5.6-luna`, `xhigh`) is the independent role that
  may run a normal Codex `exec_command` check only when the command stays within
  locked paths and existing authority, and needs no external write, network, or
  additional permission. Otherwise it returns `HW_USER_DECISION_REQUIRED` and
  the unit awaits the user. `hwahap-terra-scope-reviewer`
  (`gpt-5.6-terra`, `xhigh`) and the Luna verifier are separate,
  read-only reviewers that return structured results.
- `hwahap-sol-final-reviewer` (`gpt-5.6-sol`) is read-only; omit its configured
  reasoning effort so the explicit final invocation can attempt `ultra` once.
  Alongside its pass evidence, it may return zero or more post-completion
  improvement candidates (`summary`, `expected_effect`, `next_action`,
  evidence, and the six-field causal `decision_context` defined in
  [state-run.md](state-run.md)). A candidate is only a proposal; it never changes the Goal or
  locked scope and the reviewer never executes it.
- The Sol profile requests Fast, but this platform exposes no verifiable Fast
  runtime receipt. Record local `fast_status: unknown`; never infer `enabled`
  or `disabled` from the profile. If a future platform receipt is exposed,
  document its evidence before changing this value. Record model or effort
  deviations as evidence.

The exact profile metadata and installation-preservation rules are defined in
[state-contract.md](state-contract.md); do not infer a
role from a similarly named user agent.

After Goal binding and initialization, wait for the planner proposal before any
Luna writer; this staged lifecycle cannot be skipped. Split the locked goal into
atomic units, each exactly one user-observable change with `allowed_paths` and
an acceptance command. Keep paths within the contract and exclude every
`forbidden_changes` rule; create units with `add-unit`, never by hand.
At most one unit may be unresolved (anything other than `planned` or `passed`,
including `implementing`, `reviewing`, `recovery`, `replan_required`, or failure).
Planned units may coexist, but the next unit starts only after the current one
passes; the same unit may resume from `recovery` or `replan_required`.
Unsafe IDs, paths, or sensitive commands remain `HW_STATE_INVALID` with no
write. A safe non-member records `HW_SCOPE_DRIFT`, moves to `awaiting_user`,
creates no unit, and stores only a command digest; failed writes restore state.

For each unit, Sol records `planned` then `implementing`, gives Luna only that
contract, and records a compact summary. After Luna finishes, compute one full
`diff_snapshot`; start the separate Luna and Terra reviewers with the same
contract/snapshot before waiting. They inspect without editing. Advance only
when both pass; record distinct thread IDs, status, evidence, snapshot, and
tests. `final_review` requires every unit passed, a latest pass receipt for each
command, and a matching latest Luna/Terra review pair.

### Review activation and fallback

Each unit review starts with concurrent-first activation: start a fresh Luna
reviewer and fresh Terra reviewer together on one identical six-field
`diff_snapshot`, then wait for both. Fresh means a new thread unused by any attempt.
Only the exact platform result `agent thread limit reached`
permits fallback. End both children and discard all partial parallel-attempt
envelopes, receipts, and review history. Then start a fresh Luna reviewer; after
Luna completes, start a fresh Terra reviewer sequentially on that identical snapshot;
both fresh envelopes are required. A missing reviewer, failure, timeout,
changed/reused snapshot or thread is a gate failure. Substrings, case variants, other
capacity errors, timeout, or reviewer failures never trigger fallback.
Record exactly one complete exact-v4 deviation for a fallback episode, with
nonempty `evidence_explanation` connecting the exact result, discarded evidence,
and sequential proof. The post-source installation synchronization is external-only:
record it only after every source unit/full source checks pass and before final Sol Ultra; it is never a source unit, allowed path, or `diff_snapshot` mutation.

Record each status change with the bundled `transition` command. Sol records
structured review history, failure evidence, metrics, and final-review
attempts in the state contract; where no dedicated record command exists, use
a bounded structured state update, never prose or raw logs. The transition
command appends the event, updates the state, validates it, and rolls both
files back if validation fails.

Run states `completed`, `blocked`, `failed`, `awaiting_user`, and `cancelled`
are terminal. After any such run state, no unit can be added, mutated,
reviewed, or receive a test/improvement record. The event validator also
rejects any later unit successor event after a terminal run, including an
`awaiting_user` gate.

### Acceptance evidence

`test_commands` and `acceptance_commands` are test definitions, not execution
permission. The compatibility command below always returns
`HW_TEST_EXECUTION_DISABLED` before reading state, parsing the locked test
command, or creating a process; it never runs a command:

`<absolute-hwahap-skill-dir>/scripts/hwahap run-test --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --command-index <n> --timeout-seconds <1..3600>`

Only the independent Luna verifier may execute a stored command. Storage is
limited to allowlisted test/check/lint tools and subcommands; network, deploy,
arbitrary script, VCS mutation, absolute-path, parent-path, and URL-shaped
commands are rejected. The verifier still requires locked scope/authority and
must not request external write, network, or extra permission. Sol records that
external result with:

`<absolute-hwahap-skill-dir>/scripts/hwahap record-test-receipt --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --command-index <n> --execution-receipt-sha256 <digest> --observer-thread-id <luna-thread> --base-commit <40-hex-commit> --target-commit <40-hex-commit> --diff-digest <digest> --started-at <time> --ended-at <time> --output-sha256 <digest> (--exit-code <n> | --timed-out)`

The record computes source `codex.exec_command`, observer role `verifier`,
command digest, occurrence-based test ID, and `pass|fail|timeout` status. It
stores no raw command, stdout, stderr, environment, or output. It computes and
stores the six-field `diff_snapshot` from the committed base/target; the
receipt digest, Luna verifier thread, snapshot digest, command/output digests,
timestamps, and outcome are bound together. A passed unit and completed run
require the latest pass for every acceptance command; the latest passing
unit-review Luna verifier thread/full snapshot must match those receipts.
`metrics.test_runs` counts validated receipts, not an independently proven
number of executions.
The snapshot fields are `base_commit`, `target_commit`, `base_tree`,
`target_tree`, `diff_digest`, and nonempty `changed_paths`; they must resolve
at the exact workspace Git top-level. Non-Git, subdirectory, missing-object,
or stale-snapshot inputs fail closed as `HW_STATE_INVALID`; dirty working-tree
changes are ignored.
Git evidence collection also fails closed after 30 seconds or when metadata,
path-list, or binary-diff output exceeds its fixed byte limit; oversized
evidence must be split into a smaller approved unit.
For every nonempty final-review snapshot, each changed path must match the
locked contract, the union of passed-unit paths, and no forbidden-change rule;
scope failure requires correcting the scope or approving a new Goal/contract.

Every nested JSON state string in the contract, run, units, and event history
is checked for sensitive assignment/header/flag text, curl user,
proxy-user, or OAuth bearer options, credential URLs, and PEM headers. The validator rejects
these with a secret-free
`HW_STATE_INVALID` message; it does not echo the offending value. Harmless
prose such as `secret handling` or `token usage unavailable` remains allowed.
The report builder defensively redacts credentials and validates the rendered
report before recording its source/file digests.

## Review failures and recursive improvement

One review round may contain both verifier and scope-review failures. After each
failed round, Sol records a `record-improvement` entry before continuing. The
first entry has kind `terra_recovery` and uses Terra's cause, evidence, and
bounded recovery. The second has kind `sol_replan`; the third and later entries
have kind `recursive_improvement`. Each entry requires a valid recorded
`failure_signature`, a new `strategy_digest`, a verifiable hypothesis, and
evidence within the locked scope and authority. The same signature may be
reused with a different strategy. Reusing the same signature and strategy,
lacking a new strategy, or expanding scope, authority, or cost moves the unit
to `awaiting_user`. The external Goal is the durable objective and verified
stop condition. Continue from Terra recovery to Sol replan and later
new-evidence recursive improvement without a fixed failure-count ceiling. A
repeated blocker without a new hypothesis, or any scope/authority/cost change,
waits at `awaiting_user` and does not complete the Goal. Post-completion
candidates are report-only and never execute automatically.

Use the bundled command with `--actor`, `--after-round`, `--kind`,
`--failure-signature`, `--root-cause`, `--hypothesis`, `--action`,
`--strategy-digest`, `--scope-status within_contract`, and one or more
`--evidence-ref` values. It atomically appends the improvement and event,
transitions the unit from `reviewing` to `recovery` on the first failure or
`replan_required` thereafter, records required failure evidence, validates,
and restores both files on failure.

Out-of-scope features never get implemented: use `HW_SCOPE_DRIFT` or
`HW_USER_DECISION_REQUIRED`, record evidence, and await the user. A critical
security fix may proceed only when it is goal-contained, has bounded allowed
paths, and has tests. If it needs a new unit, path, or scope, record
`security_deferred`, finish the original work only when safe, report it after
completion, and await the user's decision.

Use only the fixed states accepted by the bundled validator. Run states are
`initialized`, `contract_locked`, `implementing`, `reviewing`, `recovering`,
`replanning`, `final_review`, `completed`, `blocked`, `failed`,
`awaiting_user`, and `cancelled`. Unit states are `planned`, `implementing`,
`reviewing`, `recovery`, `replan_required`, `passed`, `blocked`, `failed`, and
`awaiting_user`.

State commands validate after every transition and contract lock; also run
explicit validation before spawning the next writer or returning to the user:
`<absolute-hwahap-skill-dir>/scripts/hwahap validate --workspace <workspace> --run-id <goal-id>`

Validate again before the final response. A `blocked`, `failed`, or
`awaiting_user` outcome must include stable failure code, plain reason,
evidence, and recovery/next action. Use validator codes including
`HW_AGENT_CONFIG_INVALID`, `HW_IMPLEMENTATION_BLOCKED`, `HW_IMPLEMENTATION_FAILED`,
`HW_VERIFICATION_FAILED`, `HW_REPLAN_REQUIRED`, `HW_FINAL_REVIEW_FAILED`,
`HW_MODEL_UNAVAILABLE`, `HW_STATE_INVALID`, and the scope/spec codes above.
Never continue a failed review without a validated improvement record or an
explicit `awaiting_user` failure record. For the F34/F35 correction rule, a
verifiable new hypothesis permits Sol to continue correction on the same unit
within the locked scope; without one, or when scope or authority must expand,
use `awaiting_user`; this is a general rule, not new final-review recursion policy. A user gate remains authoritative.
