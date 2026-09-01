# Align-goal handoff

This mode consumes an implementation artifact whose frontmatter is exactly
`schema: align-goal/v1`, `target: implementation`, `session_status: complete`,
`alignment_status: aligned`, and `handoff_status: ready`. It is independent of
PR/FAQ and direct-request mode. Start it with:

```text
<absolute-hwahap-skill-dir>/scripts/hwahap init-goal --workspace <workspace> --goal-id <goal-id> --goal-spec <goal-path>
```

Before initialization, Sol runs the installed align-goal validator with
`--require handoff-ready --json` against the same file and repository root.
It proceeds only when the result is valid, `substance.handoff_ready` is true,
`next_action` is `complete`, and repository observation was not skipped. If
align-goal or that validation is unavailable, stop with
`HW_HANDOFF_UNCONFIRMED`; do not reinterpret the file as PR/FAQ or a request.

Hwahap then performs its own consumer checks. It requires exactly one canonical
`json align-goal-contract` fence, recomputes the NFC canonical spec digest,
checks the pass receipts and handoff confirmation bindings, rejects open or
unresolved choices/items, and verifies complete S/A/U cross-mapping. It seals
the source bytes and a minimal S/A/U projection in `contract.spec.handoff`.
These checks preserve handoff integrity; they do not replace align-goal's full
response-log, repository-observation, or semantic-review validator.

For each source U, Sol creates one execution unit with
`add-unit --source-unit-id <U-id>`. Hwahap derives its exact `spec_ids` and
`acceptance_ids`; callers cannot supply or rewrite them. A source U may map
once only. All source U IDs must be covered before `final_review`. The source
`change_boundary` is planning context, not an automatic filesystem allowlist;
Sol still fills and locks Hwahap's exact `allowed_paths` and `test_commands`.
A new mapping choice or scope expansion returns to align-goal or awaits the
user rather than becoming a local assumption.

Every terminal report preserves the sealed source S/A/U projection. Execution
units include their source trace. `completed` reports require exact full U
coverage; failure, cancellation, blocked, and awaiting-user reports preserve
the handoff without claiming unexecuted units. Report validation rejects a
missing, mismatched, or duplicated trace.

Report `deviations.classification` is `process`. Those entries describe only
orchestration-procedure departures, causes, impact, and prevention. They do not
authorize or describe source-plan changes. Scope remains in `scope_audit`,
implementation failures remain in `failures-recovery`, and feature changes
remain bound to the locked contract and unit snapshots.
