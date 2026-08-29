# Hwahap evidence and reporting

## State, evidence, and reporting

Sol alone writes `.hwahap`; all other agents return structured results. Store
state transitions, summaries, test results, failure evidence, recovery actions,
review digests, and deviations. Store no secrets, credentials, or raw logs.
Use stable summaries and bounded excerpts instead. Completed
`report-data.json` is the canonical payload: its visible ledger lists every
scalar and empty container, while `report.html` provides curated sections plus
the same exact ledger. There is no arbitrary count cap or slicing; the existing
stress coverage includes more than 100 histories and 501 events. The completed
`report.html`
has visible outcome, agents, units, timeline, reviews, tests/metrics,
failures/recovery, deviations, provenance, improvement-candidates, and
next-actions sections. Its first visible sections explain the conclusion,
previous problem, cause, applied improvement, expected change, remaining risk,
and next user decision. The full canonical ledger follows inside a collapsed
evidence disclosure. The offline static HTML follows the exact Material Design
3 contract in [material3-report.md](material3-report.md).
The report shows the observed Fast status, Goal/spec/contract/state digests,
profile hashes, and full diff snapshot (commits, trees, digest, paths). It preserves every allowlisted history
and long sanitized text without silent count or length truncation. Its derived
`scope_audit` is report-only (`affects_gate: false`). It contains
no raw logs, secrets, or hidden reasoning.

Report generation binds originals and prospective artifacts in the fixed
`.report-recovery.json` journal and a `run.json` transaction marker, writes via
same-directory exclusive temporary files and atomic replacement, then clears
both after validation. Failed rollback is retried on the next entry only when
the marker and journal digests match; this is not an `fsync` or power-loss
durability guarantee.

Record per-goal elapsed time and exact tokens only when a source surfaced those
values. Otherwise report token availability as `unavailable` with the reason,
and keep `metrics.agent_runs` as the fixed unavailable platform receipt. Exact
token totals are accepted only when the matching Goal receipt records the same
source and `token_total`; elapsed time and `test_runs` are derived locally.
Do not estimate exact totals, actual external receipt contents, model identity,
or true parallel execution from local files alone. The Git snapshot relies on
the binary object store and exact diff bytes and cannot prevent mutation after
a read. Installer exact-five and lstat/unlink checks describe an observation
with a race window; rollback cannot guarantee recovery across a crash or
non-durable disk write.

After all units pass and the final-review entry gate is satisfied, attempt one
Sol final review at `ultra`. Every Sol attempt, including an unavailable or
unsupported Ultra attempt, must carry the same full valid final `diff_snapshot`.
If Ultra is unavailable or unsupported, keep `final_review` pending and run
exactly one Sol `xhigh` fallback with the same snapshot, recording the reason.
Only an aggregate final-review failure awaits the user: use
`HW_FINAL_REVIEW_FAILED` when the final result fails, and
`HW_MODEL_UNAVAILABLE` when the xhigh fallback is unavailable or unsupported.
Do not retry after an aggregate failure.
After a final pass, invoke
`record-improvement-candidate --workspace <workspace> --run-id <goal-id>
--summary <summary> --expected-effect <effect> --next-action <action>
--evidence-ref <final-review-evidence>` once for each candidate returned by the
final reviewer, while the run is still `final_review`. This is optional: an
empty candidate list is valid. The command records `status: proposed` only;
it must not execute the proposal or expand the Goal, contract, paths, or
authority. Then invoke
`complete --workspace <workspace> --run-id <goal-id> --actor <sol-thread>
--reason <reason> --input-digest <digest> --evidence-ref <reference>`. The
complete command's `--input-digest` must exactly equal the verified digest in
the sole passing final-review snapshot. It atomically generates and validates fixed
`report-data.json` and `report.html`, records the exact official-guidance Material 3
receipt with source, data, and HTML digests, and appends the completed event
and metrics.
Run `validate` again; do not use a generic transition to `completed`. Only
after this local proof passes may Sol call external `update_goal(complete)`.
Record that tool result with `goal-complete-sync`, including its canonical
receipt digest and final token total for a successful result, then validate the
locally regenerated report once more.

The final user report states the outcome, evidence, metrics availability, and
any deviation. For every deviation, include root cause, user impact, and a
specific prevention or recovery action. Report deferred security work and
out-of-scope requests separately. Never claim completion until the final
validator passes and the run is `completed` with every unit passed.
