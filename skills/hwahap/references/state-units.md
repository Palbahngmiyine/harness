# Hwahap unit and review state

## Units and review history

`add-unit` creates a `planned` unit with one observable change, writer
`hwahap-luna-implementer`, explicit paths, acceptance commands, empty
`review_history`, empty `improvement_history`, and `replan_count: 0`. Every unit
path and command must be an exact member of the locked contract. At most one
unit may be unresolved at a time. An unresolved unit has any status other than
`planned` or `passed`, including `implementing`, `reviewing`, `recovery`,
`replan_required`, and terminal failure states. Planned future units may coexist,
but a different unit starts only when every other unit is `planned` or `passed`,
so the next new unit starts only after the current unit passes; the same unit
may resume from `recovery` or `replan_required`.

For a safe but non-member path or acceptance command, `add-unit` records
`contract_locked -> awaiting_user` with `HW_SCOPE_DRIFT`, bounded evidence, and
a recovery asking the user to approve a new Goal/contract or corrected unit. It
creates no unit, uses actor `hwahap-sol-orchestrator`, and stores command
evidence only as SHA-256 digests. Unsafe IDs, paths, or commands containing sensitive data
commands remain `HW_STATE_INVALID`; recording or validation rolls back both
state files byte-for-byte, and terminal repeats are read-only.

`test_commands` and `acceptance_commands` define checks but do not grant
execution permission. `run-test` is retained for compatibility and always
returns `HW_TEST_EXECUTION_DISABLED` before reading state, parsing, or creating
a process. Only the independent Luna verifier may run a normal Codex
`exec_command` when it stays within locked paths and existing authority and
needs no external write, network, or extra permission; otherwise it returns
`HW_USER_DECISION_REQUIRED` and awaits the user. Sol records that result with
`record-test-receipt` only while the contract is locked, the run is reviewing,
and the unit is reviewing. The command computes source
`codex.exec_command`, observer role `verifier`, occurrence-based `test_id`,
locked command digest, and `pass` (exit 0), `fail` (nonzero), or `timeout`.
Each receipt also stores `execution_receipt_sha256`,
`observer_thread_id`, the full `diff_snapshot`, `started_at`, `ended_at`,
`output_sha256`, and exit code. It never stores raw command, stdout, stderr, or
environment. A passed unit requires the latest receipt for every command to be
pass and to match the latest passing unit-review Luna verifier thread and full
snapshot;
completion derives `metrics.test_runs` from validated receipt count.
Pass the committed `--base-commit` and `--target-commit`; the command resolves
their trees and canonical diff itself rather than trusting caller-provided
snapshot fields.

The state validator walks every nested JSON string in the contract, run, unit
files, and event history. Credential-bearing assignment/header/flag text, curl
user, proxy-user, or OAuth bearer options, credential URLs, and PEM headers are
rejected with secret-free
`HW_STATE_INVALID` output; the offending value is never echoed. Harmless prose
such as `secret handling` and `token usage unavailable` is allowed. Report
generation defensively redacts credentials and validates the rendered report
before recording its digests.

The command storage gate allows only named test/check/lint tools and safe
subcommands. It rejects arbitrary scripts; network, deploy, and VCS tools;
absolute or parent paths; URLs; credential patterns; every `KEY=VALUE` argv
token; `env` and shell launchers; shell expansion and controls; and malformed
shlex input. This is a storage boundary, not a process sandbox: repository test
code can still have side effects, so Luna retains read-only authority and must
return `HW_USER_DECISION_REQUIRED` for any extra permission.
Initialization scans the complete contract and run objects in memory before
creating their directory or files, and rejects sensitive title/source
inputs with generic `HW_STATE_INVALID` output.

One review-history round has this shape:

`diff_snapshot` is always the exact six-field object below; reviewers, receipts,
and Sol final attempts must share the whole object, not only its digest:

```json
{"base_commit":"<40 lowercase hex>","target_commit":"<40 lowercase hex>","base_tree":"<40 lowercase hex>","target_tree":"<40 lowercase hex>","diff_digest":"sha256:<64 lowercase hex>","changed_paths":["src/a"]}
```

```json
{
  "round": 1,
  "diff_snapshot": {"base_commit":"<40 lowercase hex>","target_commit":"<40 lowercase hex>","base_tree":"<40 lowercase hex>","target_tree":"<40 lowercase hex>","diff_digest":"sha256:<64 lowercase hex>","changed_paths":["src/a"]},
  "diff_digest": "sha256:<64 lowercase hex characters>",
  "changed_paths": ["src/a"],
  "outcome": "pass",
  "verifier": {
    "model": "gpt-5.6-luna",
    "effort": "xhigh",
    "status": "pass",
    "thread_id": "luna-thread",
    "diff_digest": "sha256:<same digest>",
    "evidence": ["bounded test result"]
  },
  "scope_reviewer": {
    "model": "gpt-5.6-terra",
    "effort": "xhigh",
    "status": "pass",
    "thread_id": "terra-thread",
    "diff_digest": "sha256:<same digest>",
    "evidence": ["bounded scope result"]
  }
}
```

The reviewer thread IDs must differ, both reviewers must use the recorded round
digest, and all `changed_paths` must be inside the unit. For every nonempty
final-review snapshot, each path must also match locked `allowed_paths`, match
the union of passed-unit `allowed_paths`, and overlap no `forbidden_changes`
rule. Otherwise validation fails with `HW_STATE_INVALID`; correct the scope or
approve a new Goal/contract. If either reviewer
fails, the round outcome is `fail`; two failures in one round still count as
one failed round. Each failed round normally has one corresponding
`improvement_history` record:

```json
{
  "after_round": 1,
  "kind": "terra_recovery",
  "failure_signature": "sha256:<64 lowercase hex characters>",
  "root_cause": "bounded cause",
  "hypothesis": "verifiable hypothesis",
  "action": "bounded action within the unit",
  "strategy_digest": "sha256:<64 lowercase hex characters>",
  "scope_status": "within_contract",
  "evidence": ["bounded evidence"]
}
```

The first failed round uses `terra_recovery`, the second `sol_replan`, and the
third and later rounds `recursive_improvement`. Each record has a valid
recorded `failure_signature` and a new `strategy_digest`; the same signature
may be used with a different strategy. The signature/strategy pair must not
recur, and each new strategy must remain inside locked scope, authority, and
cost. A missing new strategy or any expansion is `awaiting_user`. The
terminal `blocked`, `failed`, or `awaiting_user` state may omit only the last
failed round's record when its failure record is complete. There is no fixed
review-round ceiling.

Use `record-improvement` rather than hand-editing this history. `--actor` is
required; the command appends the record and its transition event atomically,
sets `reviewing -> recovery` for the first failure or
`reviewing -> replan_required` thereafter, fills `HW_REPLAN_REQUIRED` failure
evidence for replans, validates, and restores both files on failure.

Examples of valid histories for a passed unit include:

- `pass`
- `fail, pass` after one Luna recovery
- `fail, fail, pass` after one recovery and one Sol replan
- `fail, fail, fail, pass` after recursive improvements with new strategies
