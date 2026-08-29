# Hwahap review and report protocol

## Atomic unit and review envelopes

An atomic unit has exactly one observable change, explicit `allowed_paths`
inside the locked contract, at least one mechanical `acceptance_command`, and a
clear pass condition. Test commands containing sensitive data (tokens, cookies,
authorization/bearer values, passwords, secrets, private keys, or credential
URLs) are rejected at contract/unit input with a stable state error. The HTML
report exposes only fixed command names and SHA-256 digests. A unit test is the
command plus its exit status and a bounded result summary; it must be
independently rerunnable.

The storage gate allows only known test/check/lint tools and safe subcommands.
It rejects arbitrary scripts, network/deploy/VCS tools, external paths, URLs,
every `KEY=VALUE` argv token, shell launchers and controls, and malformed shlex
input. Replace a rejected command with an allowlisted in-scope check; do not
weaken the gate or copy sensitive data into state.

The state validator separately walks every nested JSON string in the contract,
run, unit files, and event history. Sensitive assignment/header/flag text,
authenticated URLs, provider tokens, high-entropy secret candidates, and PEM
headers are rejected as `HW_STATE_INVALID`
without echoing the secret. Harmless prose such as `secret handling` and
`token usage unavailable` is allowed. Report generation defensively redacts
credentials and validates the rendered HTML before storing report digests.

Every role returns JSON-like data, never a prose-only handoff:

```json
{"role":"implementer","status":"pass","thread_id":"...","changed_paths":["src/a"],"evidence":["preliminary test summary"]}
```

The implementer envelope has `role: implementer`, `status: pass|blocked|failed|awaiting_user`,
`thread_id`, changed paths, and preliminary evidence; it does not claim the
official snapshot. Sol computes that snapshot after committed objects exist;
failures also have `failure: {code, reason, evidence, recovery}`. The verifier
envelope has `role: verifier`, `status: pass|fail`, `thread_id`, full
`diff_snapshot`, matching `diff_digest`, and `evidence`,
and a bounded `tests` summary. The Terra envelope has the same fields with
`role: scope_reviewer`, plus `reason` and `recovery` on failure. The final
envelope has `role: final_reviewer`, `status: pass|fail|unavailable|unsupported`, `thread_id`,
`evidence`, a valid full `diff_snapshot`, `model: gpt-5.6-sol`, and `effort`
(`ultra` or the recorded `xhigh` fallback). All Sol final attempts share the
exact full snapshot, including an unavailable/unsupported Ultra probe. A
missing/unusable envelope is a model or implementation failure, not an
implicit pass.

## Final report

Report `outcome`, `run_id`, `spec` evidence, `changed_paths`, `test_results`,
`review_rounds`, `recoveries`, `replans`, `agent_runs`, `elapsed_time`,
`token_usage`, `fast_status`, `deviations`, `deferred_security`,
`improvement_candidates`, and `next_action`. Include the actual Goal,
spec/contract/state digests, installed profile hashes, and full final
`diff_snapshot` (commits, trees, digest, paths).
The profile requests Fast, but this platform has no verifiable runtime receipt;
therefore local `fast_status` remains `unknown` and must not be inferred from
profile metadata.
When exact tokens are not surfaced, set
`token_usage: {availability: unavailable, reason: <why>, total: null}` and
report `agent_runs` as the fixed unavailable platform receipt; `elapsed_time`
and `test_runs` are derived locally. An available token total is valid only
when its source and total match the same Goal receipt's `source` and
`token_total`. Do not claim the actual external receipt contents, model
identity, or true parallel execution from local files alone. Every deviation must
state root cause, user impact, and prevention/recovery action.
`report-data.json` is the canonical report source. Its exact visible ledger
lists every scalar and empty container with JSON pointer, type, and value;
curated sections are a readable view of the same payload. There is no arbitrary
record-count cap or slicing, and the derived `scope_audit` is report-only with
`affects_gate: false`. The generated HTML first presents the conclusion,
previous problem, cause, applied improvement, expected change, remaining risk,
and next user decision. It retains all allowlisted histories and long sanitized
text without silent truncation in a collapsed evidence disclosure. The offline
static document implements the fixed OpenDesign-sourced Material theme contract in
`material3-report.md` and must not contain
raw logs, secrets, or hidden reasoning.

The review table keeps its nine columns and uses internal horizontal scrolling
on narrow screens; the page itself must not overflow horizontally.

The renderer and validator share the exact canonical ledger, which prevents a
new allowlisted field from being omitted from visible output.

The v4 receipt is exact: `schema_version`, `status`, `generator` (Hwahap
report version 4, `design_system: material-design-3`, and pinned
`theme_source`),
`source_payload_sha256`, `data`, `html`,
`generated_at`, and `redaction_policy`. Pending runs have null source, file
digests, and generated time; data/html path entries remain with null digests
and no physical artifact files. Completed runs require regular, non-symlink,
single-link data and HTML files; canonical data bytes must match the source
digest and the payload-bound HTML validator must pass. v3 and earlier receipts are rejected without
silent migration; archive or replay them with their original version.
