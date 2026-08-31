# Hwahap state contract

`.hwahap` is compact execution state for handoff and audit. It is not
tamper-proof, and it cannot prove who performed an action or whether two agents
actually ran at the same time. Store summaries, SHA-256 digests, bounded test
results, and evidence references only. Never store secrets, credentials, or raw
logs. Sol is the sole state writer; every other role returns an envelope to Sol.

The official state entrypoint is `<absolute-hwahap-skill-dir>/scripts/hwahap`, which starts the
state program with an isolated trusted interpreter. Direct `hwahap_state.py`
execution is not this security boundary. Embedding callers must ensure an
isolated, validated interpreter and clean module environment.

Use only the absolute launcher path resolved from the loaded skill. A copied,
hard-linked, symlinked, or replaced entrypoint is outside the boundary. The
launcher, adjacent state script, `/bin/sh`, kernel file-system semantics, and
the selected absolute Python interpreter and standard library are trust roots;
the launcher does not pin state data. Same-UID concurrent races and stronger
native or signed bootstraps are not covered.

## Generated tree and commands

```text
<workspace>/.codex/agents/hwahap-*.toml
<workspace>/.hwahap/runs/<goal-id>/
├── contract.json
├── run.json
├── events.jsonl
├── report-data.json (every terminal outcome)
├── report.html (every terminal outcome)
├── .report-recovery.json (transient during report transactions)
└── units/<unit-id>.json
```

In a Git workspace, `.hwahap/` must be ignored before initialization. Hwahap
creates state directories as `0700` and files as `0600`; wrong ownership,
group/world access, symlinks, or hard links fail validation.

Resolve `<skill-dir>` from the loaded Hwahap `SKILL.md`. Select exactly one
input branch: approved-spec mode uses an approved PR/FAQ and
`init --spec`; direct-request mode first writes a credential-free request
capsule, then uses `init-request --request`. Neither branch is interchangeable.

The exact pre-lock Goal sequence for either branch is `get_goal` -> conditional
`create_goal` (only when no active Goal exists) -> `get_goal` -> `goal-sync`
(`--mode bound`) -> `lock`. A compatible Goal is reused; a conflict or failed
Goal tool stops the run. The selected initializer remains the branch-specific
`init --spec` or `init-request --request` described above and must complete
before lock.

```text
<absolute-skill-dir>/scripts/install-project-agents --workspace <workspace>
<absolute-hwahap-skill-dir>/scripts/hwahap init --workspace <workspace> --goal-id <goal-id> --spec <approved-prfaq>
# Sol fills the six contract lists while locked is false.
<absolute-hwahap-skill-dir>/scripts/hwahap lock --workspace <workspace> --run-id <goal-id> --actor <sol-thread> --reason <reason> --evidence-ref <reference>
<absolute-hwahap-skill-dir>/scripts/hwahap add-unit --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --title <title> --allowed-path <path> --acceptance-command <command>
<absolute-hwahap-skill-dir>/scripts/hwahap run-test --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --command-index <1-based> --timeout-seconds <1..3600> # compatibility; always disabled
<absolute-hwahap-skill-dir>/scripts/hwahap record-test-receipt --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --command-index <1-based> --execution-receipt-sha256 <digest> --observer-thread-id <luna-thread> --base-commit <40-hex-commit> --target-commit <40-hex-commit> --diff-digest <digest> --started-at <time> --ended-at <time> --output-sha256 <digest> (--exit-code <n> | --timed-out)
<absolute-hwahap-skill-dir>/scripts/hwahap transition --workspace <workspace> --run-id <goal-id> --entity <run-or-unit-id> --to <state> --actor <thread-id> --role <role> --reason <reason> --input-digest <digest> --evidence-ref <reference>
<absolute-hwahap-skill-dir>/scripts/hwahap record-improvement --workspace <workspace> --run-id <goal-id> --unit-id <unit-id> --actor <sol-thread> --after-round <n> --kind <kind> --failure-signature <sha256:...> --root-cause <reason> --hypothesis <testable-hypothesis> --action <bounded-action> --strategy-digest <sha256:...> --scope-status within_contract --evidence-ref <reference>
<absolute-hwahap-skill-dir>/scripts/hwahap record-improvement-candidate --workspace <workspace> --run-id <goal-id> --summary <summary> --expected-effect <effect> --next-action <action> --evidence-ref <final-review-evidence> --scenario <concrete-condition> --affected-scope <affected-boundary> --impact <consequence> --decision-reason <why-user-decides> --evidence-relation <what-evidence-proves> --success-condition <observable-resolution> # final_review only; report-only
<absolute-hwahap-skill-dir>/scripts/hwahap record-deviation --workspace <workspace> --run-id <goal-id> --summary <summary> --root-cause <root-cause> --impact <impact> --prevention <prevention> --evidence-explanation <explanation> --evidence <reference>
<absolute-hwahap-skill-dir>/scripts/hwahap goal-sync --workspace <workspace> --run-id <goal-id> --mode <bound|no_active_goal|unavailable> --reason <reason> --evidence-ref <reference> [--thread-id <id> --objective-sha256 <sha256:...> --receipt-sha256 <sha256:...> --token-total <nonnegative-int>]
<absolute-hwahap-skill-dir>/scripts/hwahap goal-complete-sync --workspace <workspace> --run-id <goal-id> --sync-result <completed|already_completed|failed> --receipt-sha256 <sha256:...> --reason <reason> --evidence-ref <reference> [--token-total <nonnegative-int>]
<absolute-hwahap-skill-dir>/scripts/hwahap complete --workspace <workspace> --run-id <goal-id> --actor <sol-thread> --reason <reason> --input-digest <digest> --evidence-ref <reference>
<absolute-hwahap-skill-dir>/scripts/hwahap validate --workspace <workspace> --run-id <goal-id>
```

Repeat `--allowed-path`, `--acceptance-command`, and `--evidence-ref` when more
than one value is required. A transition to `blocked`, `failed`,
`replan_required`, or `awaiting_user` also requires `--failure-code`,
`--failure-reason`, one or more `--failure-evidence`, and
`--failure-recovery`. State-changing commands validate immediately and restore
all affected state files and the event log byte-for-byte when a write or
validation fails where restoration is possible. Non-Hwahap write failures are
reported as generic `HW_STATE_INVALID` without path or value details.
Rollback is best-effort and non-durable: a persistent filesystem failure may
leave incomplete state and requires operator inspection.

`record-deviation` is the only deviation creation API. It requires the exact
v4 fields and atomically updates `run.json`; stale or credential-bearing input
is rejected without silent migration.

Every terminal run outcome—`completed`, `blocked`, `failed`, `awaiting_user`,
or `cancelled`—automatically publishes both `report-data.json` and
`report.html`; artifact publication does not alter the terminal status.

Before an existing run is read or changed, validation rejects a pre-existing
symlink at any required state path, including `events.jsonl`, with generic
`HW_STATE_INVALID`. This is a static pre-existing-link check; it is not a
claim of race-proof concurrent access.

While a unit is `reviewing` with its latest failed review still awaiting an
improvement record, the run must remain `reviewing` or move directly to a
terminal failure state with complete failure evidence. `implementing`,
`recovering`, `replanning`, and `final_review` are invalid during this pending
improvement interval.

`goal-sync` always requires the common `--reason` and `--evidence-ref` values.
`bound` additionally requires `--thread-id`, `--objective-sha256`, and
`--receipt-sha256`; `no_active_goal` requires `--receipt-sha256`; `unavailable`
must not include a receipt hash. The receipt hash is SHA-256 over the canonical
JSON of the `get_goal` tool result. Store only the normalized digest and
bounded evidence, never the raw receipt, logs, prompts, or hidden reasoning.

Every unit review, test receipt, and final-review attempt carries one exact
`diff_snapshot`: `base_commit`, `target_commit`, `base_tree`, `target_tree`,
`diff_digest`, and nonempty `changed_paths`. The commits are lowercase 40-hex
objects resolved at the workspace's exact Git top-level. The digest is over a
canonical binary diff with fixed `--full-index --binary --no-ext-diff
--no-textconv --no-color --diff-algorithm=myers --no-indent-heuristic
--unified=3 --src-prefix=a/ --dst-prefix=b/ --no-renames` options under isolated
Git configuration/environment (`GIT_NO_REPLACE_OBJECTS=1`, system/global config
disabled, `GIT_ATTR_NOSYSTEM=1`, `LC_ALL=C`, `LANG=C`, trusted default `PATH`).
Dirty working-tree changes do not affect it.
Non-Git workspaces, subdirectories, missing objects, invalid paths, or stale snapshots fail closed as `HW_STATE_INVALID`.

For `bound`, `--token-total` is optional and is stored in the `codex.get_goal`
receipt as a nonnegative integer or `null`. Without it, and for unbound modes,
`metrics.token_usage` remains unavailable. `goal-complete-sync` requires a
nonnegative `--token-total` for `completed` or `already_completed`, stores it
in the `codex.update_goal` receipt, and forbids it for `failed`; failed sync
preserves the prior token receipt. It regenerates the report and rolls back
`run.json`, `report-data.json`, and `report.html` byte-for-byte if validation
fails. A recovery journal is retained when rollback is incomplete and is
replayed only when its run marker and bound digests validate; a journal alone
never mutates state.


## Detailed state references

- [state-run.md](state-run.md): locked contract, run, Goal, report transaction.
- [state-units.md](state-units.md): units, reviews, failures, recovery, replans.
- [state-lifecycle.md](state-lifecycle.md): transitions, final review, completion.
- [state-limits.md](state-limits.md): explicit security and durability limits.
