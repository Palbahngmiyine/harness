# Hwahap execution and review

## Roles and units

After installation, spawn roles by these exact custom-agent names:
`hwahap-sol-orchestrator`, `hwahap-luna-implementer`,
`hwahap-luna-verifier`, `hwahap-terra-scope-reviewer`, and
`hwahap-sol-final-reviewer`.

- `hwahap-sol-orchestrator` (`gpt-5.6-sol`, `xhigh`) is the sole orchestrator
  and only `.hwahap` state writer; it delegates and never implements source.
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
  improvement candidates (`summary`, `expected_effect`, `next_action`, and
  evidence). A candidate is only a proposal; it never changes the Goal or
  locked scope and the reviewer never executes it.
- The Sol profile requests Fast, but this platform exposes no verifiable Fast
  runtime receipt. Record local `fast_status: unknown`; never infer `enabled`
  or `disabled` from the profile. If a future platform receipt is exposed,
  document its evidence before changing this value. Record model or effort
  deviations as evidence.

The exact profile metadata and installation-preservation rules are defined in
[state-contract.md](state-contract.md); do not infer a
role from a similarly named user agent.

Split the locked goal into atomic units. Each unit must describe exactly one
user-observable change, its explicit `allowed_paths`, and at least one
mechanical acceptance command. Keep the unit's paths within the contract and
exclude every `forbidden_changes` path or behavior. Create it with the bundled
`add-unit` command; do not hand-author the initial unit state.
At most one unit may be unresolved at a time. An unresolved unit has any status
other than `planned` or `passed`, including `implementing`, `reviewing`,
`recovery`, `replan_required`, and terminal failure states. Planned future units
may coexist; a different unit can enter `implementing` only when every other
unit is `planned` or `passed`, so the next new unit starts only after the
current unit has passed. The same unit may resume from `recovery` or
`replan_required`.
Unsafe IDs, paths, and commands containing sensitive data remain `HW_STATE_INVALID`
with no write. A safe but non-member path or command records `HW_SCOPE_DRIFT`,
moves the run to `awaiting_user`, creates no unit, and stores command evidence
as a SHA-256 digest only. It asks the user to approve a new Goal/contract or
corrected in-scope inputs; failed writes or validation restore both state files.

For each unit, Sol records `planned` and then `implementing`, gives Luna only
that unit's contract, and records a compact summary. After Luna finishes,
compute one full `diff_snapshot` and spawn both the separate Luna xhigh
verifier and Terra xhigh scope reviewer before waiting. Give both the same
snapshot and contract. They inspect without editing. Advance only when both
report pass; record their distinct thread IDs, statuses, full snapshot,
evidence, and mechanical test results. A run may enter `final_review` only
after every unit is `passed`, each latest receipt is `pass`, and each latest
passing Luna/Terra review pair shares one full snapshot that receipts and the
Luna verifier thread match.

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

The state commands validate after every transition and contract lock. Also run
an explicit validation before spawning the next writer or returning to the
user:

`<absolute-hwahap-skill-dir>/scripts/hwahap validate --workspace <workspace> --run-id <goal-id>`

Validate again before the final response. A `blocked`, `failed`, or
`awaiting_user` outcome must include a stable failure code, plain reason,
evidence, and recovery/next action. Use the validator's codes, including
`HW_AGENT_CONFIG_INVALID`, `HW_IMPLEMENTATION_BLOCKED`,
`HW_IMPLEMENTATION_FAILED`,
`HW_VERIFICATION_FAILED`, `HW_REPLAN_REQUIRED`, `HW_FINAL_REVIEW_FAILED`,
`HW_MODEL_UNAVAILABLE`, `HW_STATE_INVALID`, and the scope/spec codes above.
Never continue a failed review without a validated improvement record or an
explicit `awaiting_user` failure record. For the F34/F35 correction rule, a
verifiable new hypothesis permits Sol to continue correction on the same unit
within the locked scope; without one, or when scope or authority must expand,
use `awaiting_user`. This is a general rule, not a new final-review recursion
policy. A user gate remains authoritative.
