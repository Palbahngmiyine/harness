# Hwahap contract and run state

## Contract and run

`contract.json` has `schema_version: 1`, `goal_id`, `goal`, approved `spec`
evidence, `locked`, `lock_sha256`, and these six lists: `goals`, `non_goals`,
`allowed_paths`, `forbidden_changes`, `acceptance_criteria`, and
`test_commands`. Sol fills all six lists before `lock`. The command sets
`locked: true` and records a canonical `lock_sha256`; any later contract change
invalidates the run.

`run.json` has `schema_version: 1`, `goal_id`, fixed `status`, timestamps, the
exact role map, and the SHA-256 digest of every installed custom-agent profile.
The source and installed Hwahap set is exactly these six regular files:
`hwahap-sol-planner.toml` (Sol, `xhigh`, `read-only`),
`hwahap-luna-implementer.toml` (Luna, `high`, `workspace-write`),
`hwahap-luna-verifier.toml` (Luna, `xhigh`, `read-only`),
`hwahap-sol-final-reviewer.toml` (Sol, `read-only`, effort omitted so the
invocation chooses `ultra`), `hwahap-sol-orchestrator.toml` (Sol, `xhigh`, `workspace-write`,
`service_tier = "fast"`, `fast_mode = true`), and
`hwahap-terra-scope-reviewer.toml` (Terra, `xhigh`, `read-only`). The target
may retain unrelated user-agent files; an extra `hwahap-*.toml`, missing file,
symlink, metadata mismatch, or byte mismatch is invalid.
These sandbox modes are agent defaults, not an absolute security boundary:
Codex reapplies live parent permission overrides when spawning a child. The
locked contract and reviewer instructions therefore remain mandatory.
It also records:

- `metrics`: `unit_count`, `agent_runs`, `review_rounds`, `recoveries`,
  `replans`, `scope_deviations`, `test_runs`, `elapsed_seconds`, and
  `token_usage`.
- `agent_runs`: `{availability: unavailable, reason: "platform aggregate not
  exposed", source: null, total: null}`. This fixed receipt prevents an
  unverified local numeric self-report.
- `token_usage`: `{availability, reason, source, total}`. Use
  `availability: unavailable` and `total: null` when no exact aggregate is
  surfaced; `available` is valid only when `source` and `total` exactly match
  a Goal receipt's `source` and `token_total`. Never estimate it. Local
  `elapsed_seconds` and `test_runs` are derived metrics; an external receipt,
  model identity, or true parallel execution cannot be proven from local files.
- `fast_status`: always `unknown` on this platform. The Sol profile continues
  to request Fast, but local state records `unknown` until a verifiable runtime
  receipt is exposed; never infer `enabled` or `disabled` from the profile.
- `deviations`: exact v4 records with only `summary`, `root_cause`, `impact`,
  `prevention`, `evidence_explanation`, and nonempty `evidence`. The explanation states why
  that evidence supports the prevention instead of merely naming a test.
- `deferred_security`: records with `summary`, `reason`, `next_action`, and
  nonempty `evidence`, plus the exact `decision_context` below.
- `final_review`: `status` and append-only `attempts`.
- `improvement_candidates`: an append-only list of report-only proposals. Each
  item has `status: proposed`, `summary`, nonempty `evidence`,
  `expected_effect`, `next_action`, and the exact `decision_context`. The candidate command accepts records
  only while the run is `final_review`; it does not append a transition event.
- `goal_link`: current normalized Goal receipt and append-only history. An
  active bound receipt comes from `codex.get_goal`; a post-completion bound
  receipt comes from `codex.update_goal` and records `sync_result`. No-active
  and unavailable receipts keep thread/objective null. Once history contains a
  bound receipt, no-active/unavailable downgrade is invalid; every later bound
  receipt and completion sync retains that receipt's thread/objective pair.
- `report`: a v4 receipt with the exact fields `schema_version`, `status`,
  `generator` (`name: hwahap-report`, `version: 5`,
  `design_system: material-design-3`, and pinned Icy Blue `theme_source`),
  `source_payload_sha256`, `data`, `html`, `generated_at`, and
  `redaction_policy: hwahap-report-v4`. Pending init uses null source,
  file digests, and generated values; its data/html path entries are present
  with null digests and no physical artifact files. Completed uses
  `report-data.json` and `report.html`; both must be regular, non-symlink,
  single-link files, the source digest equals the canonical data bytes digest,
  and the HTML digest and payload-bound validation pass. v3 and earlier are
  incompatible: reject them with no silent migration; archive or replay old
  runs with the version that created them.

After a passing final-review envelope, Sol may record each returned candidate
with `record-improvement-candidate` before `complete`; an empty list is valid.
The record is only a proposal: user approval is required before any new Goal,
scope, path, or implementation action, and the command never executes it.
`complete` is the only completion command. It requires a locked contract, an
observed Goal receipt, passed units, and a valid passing final review. It
computes completed metrics, appends `final_review -> completed`, builds the
allowlisted report payload, validates the offline Material Design 3 report
pins, and writes `report-data.json`, `report.html`, `run.json`, and
`events.jsonl` with rollback on any failure. A generic transition to
`completed` is invalid.
After local `validate` passes, Sol may call external `update_goal(complete)`;
that call cannot expand scope or authority. Sol then records the normalized
result with `goal-complete-sync` and validates the regenerated report.

`report-data.json` is the canonical report source. Its visible ledger contains
every scalar and empty object/list with a JSON pointer, type, and value; curated
HTML sections repeat human-readable fields but are not a second source of
truth. There is no arbitrary record-count cap, slicing, or pagination: stress
fixtures cover more than 100 histories and 501 events. The completed HTML is
complete on its own: it visibly shows outcome, timeline,
agents, units, tests/metrics, reviews, failures/recoveries, deviations,
provenance, candidates, next actions, and the full diff snapshot. Its static
HTML remains usable without a network. Every allowlisted history and long
sanitized text is retained without silent truncation; raw logs, secrets, and
hidden reasoning are never included.

The renderer and validator use the same canonical payload ledger, so adding a
field cannot silently omit it from the visible report: the complete ledger is
validated as one exact payload-bound block.

Use `record-deviation` to append causal records atomically. It rejects stale
pre-v4 records and preserves `metrics.scope_deviations == len(deviations)`;
there is no silent migration of existing state.

`decision_context` has exactly six nonempty strings: `scenario` describes the
concrete condition in which the item matters; `affected_scope` names the
affected person, artifact, workflow, or trust boundary; `impact` states the
consequence if ignored; `decision_reason` explains why the user owns the
tradeoff; `evidence_relation` explains what each bounded evidence reference
actually proves; and `success_condition` defines the observable result that
would resolve the risk or validate the candidate. Missing, extra, or empty
fields are invalid. Generic shared warnings and title-only explanations are
not valid substitutes.

Report transactions first bind original and prospective bytes in the fixed
`.report-recovery.json` journal and `run.json` `report_transaction` marker.
During an uninterrupted invocation, the marker binds partial writes. A caught
exception attempts in-process rollback; only an incomplete rollback retains
the marker and journal for a next-entry retry. Abrupt process termination is
outside this guarantee: the marker-free final `run.json` write can precede the
`events.jsonl` write, leaving an unbound journal that next validation rejects
safely without automatic recovery; archive, repair, or replay it manually.
This does not claim `fsync` or power-loss durability. A journal over 128 MiB is
rejected before reading and never truncated. Journal/marker co-forgery, a live
temp inode, and a same-UID concurrent writer remain outside this boundary.

Run terminal states include `completed`, `blocked`, `failed`, `awaiting_user`,
and `cancelled`. After a terminal run, unit creation, unit mutation,
test-receipt recording, and improvement recording are forbidden. The event
validator rejects any unit successor event after a terminal run as well.
