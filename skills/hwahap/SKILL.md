---
name: hwahap
description: "Execute an implementation request or approved `status: prfaq` spec with staged Sol/Luna/Terra orchestration, automatic Goal binding, atomic units, scope control, and structured evidence. Trigger for implementation or orchestration; do not trigger for ideation or grilling."
---

# Hwahap

Use this skill for an implementation request that is authoritative in the
current conversation or for an explicitly provided approved PR/FAQ. A direct
request does not need a PR/FAQ path; an idea, question, grill, or planning-only
request is not implementation authority. The current request is authoritative
over stored context.
Only two input modes are authoritative: direct-request mode and approved-spec
mode.
Resolve `<hwahap-skill-dir>` from this loaded `SKILL.md`; it may be installed
outside the target workspace.
An approved PR/FAQ may live outside the target repository; never copy it into
that repository's `docs/prfaq`. Hwahap requires no login, API key, access token,
or other credential and rejects such values in state. `token_total` means a
numeric model-usage receipt, not an authentication token.

Use `<absolute-hwahap-skill-dir>/scripts/hwahap` as the official state entrypoint. It
starts the fixed adjacent trusted state script with an isolated (`-I`) trusted interpreter;
running `hwahap_state.py` directly is not the official security boundary.
Embedding callers must provide an isolated, validated interpreter and a clean
module environment themselves.

Invoke the launcher only by the absolute path resolved from this loaded skill.
Copied, hard-linked, symlinked, or replaced entrypoints are outside the
boundary. The launcher, adjacent state script, `/bin/sh`, kernel file-system
semantics, and selected absolute Python plus its standard library are the trust
roots; the launcher itself does not pin state data. Same-UID concurrent races
and a stronger native or signed bootstrap are not covered.

## Start gate

### Observable fail-closed checks

Before implementation, check these four inputs explicitly:

1. Workspace and selected input paths must be existing regular
   directories/files with no symlink in any lexical ancestor. An unsafe
   workspace returns `HW_STATE_INVALID`; an unsafe approved spec returns
   `HW_SPEC_UNCONFIRMED`; an unsafe request capsule returns
   `HW_REQUEST_UNCONFIRMED`.
2. Select exactly one authoritative input mode. Approved-spec mode requires
   readable UTF-8 with `status: prfaq` and nonempty `confirmed_at`. Direct-
   request mode is available only for a current implementation instruction;
   Sol writes a credential-free capsule under `.hwahap/requests/` with
   `status: request`, a concise title, and `confirmed_at`, then pins its bytes
   with `init-request --request`. A draft, idea, or planning-only conversation
   never becomes a request capsule.
3. Installed profiles must be the exact six Hwahap source profiles, each a
   regular byte-identical file with the source role metadata:
   `hwahap-luna-implementer` (Luna/high/workspace-write), `hwahap-luna-verifier`
   (Luna/xhigh/read-only), `hwahap-sol-planner` (Sol/xhigh/read-only), `hwahap-sol-final-reviewer` (Sol/read-only with no
   configured effort), `hwahap-sol-orchestrator` (Sol/xhigh/Fast/workspace-write), and
   `hwahap-terra-scope-reviewer` (Terra/xhigh/read-only). The installer must
   return `HW_OK`; otherwise return
   `HW_AGENT_CONFIG_INVALID`, do not overwrite conflicts or
   `.codex/config.toml`, and repair the installation. In plain terms: every
   named role must be the expected file. Six byte-identical profiles pass; a
   missing, symlinked, conflicting, or extra `hwahap-*.toml` fails. Unrelated
   user agent files are preserved and do not count toward the Hwahap set.
4. Before `lock`, the contract must contain all six nonempty lists and safe,
   sensitive-data-free allowlisted test/check/lint commands. Command input
   rejects arbitrary scripts, network/deploy/VCS tools, external paths, URLs,
   shell expansion, shell interpreter/wrapper tokens, and `-lc`. A
   pass records a matching `lock_sha256`; a
   failure returns `HW_STATE_INVALID` or `HW_SCOPE_DRIFT`, preserves files,
   and requests corrected in-scope inputs. In plain terms: the plan must say
   what is included, excluded, allowed, forbidden, how success is checked, and
   which commands are definitions. Six filled lists and `pytest` pass; an empty
   list, `env TOKEN=...`, or shell control operator fails before lock and must
   be replaced by safe in-scope input.

1. Read the applicable `AGENTS.md` files, then inspect the Git root, branch, and
   current working-tree changes. Preserve unrelated work and limit edits to the
   approved contract paths.
2. Before execution, read [references/protocol.md](references/protocol.md) and
   select direct-request or approved-spec mode. Require a PR/FAQ path only
   when the user chose or supplied that mode. For direct mode, require an
   explicit current implementation instruction and create the internal
   request capsule; do not infer authority from an idea, draft, title, or
   stored context.
3. Install the project-scoped custom agents before initializing state:

   `<absolute-hwahap-skill-dir>/scripts/install-project-agents --workspace <workspace>`

   Require `HW_OK`. A conflict or path/source error is a stable failure; record
   its code and bounded evidence and stop. The installer never edits
   `.codex/config.toml` and never overwrites a different existing profile.
4. After installation, spawn only `hwahap-sol-orchestrator`. It owns Goal and
   run setup. The orchestrator first calls `get_goal`; when no active Goal
   exists, it automatically calls `create_goal` with the current implementation
   objective, then calls `get_goal` again for the bound receipt. A conflicting
   active Goal requires `HW_USER_DECISION_REQUIRED`; Goal-tool unavailability
   requires `HW_GOAL_REQUIRED`. Do not silently run without a Goal.

5. Run the initializer selected by the input mode:

   `<absolute-hwahap-skill-dir>/scripts/hwahap init --workspace <workspace> --goal-id <goal-id> --spec <approved-prfaq-path>`

   `<absolute-hwahap-skill-dir>/scripts/hwahap init-request --workspace <workspace> --goal-id <goal-id> --request <request-capsule-path>`

   Treat any non-zero result as a stable failure; record its code and evidence
   and stop unless the defined recovery is safe and in scope.

   Initialization constructs and scans the complete initial state in memory
   before creating the run directory; sensitive title or source
   inputs fail with a generic `HW_STATE_INVALID` and no state files are made.
6. Before Sol writes or validates state, read
   [references/state-contract.md](references/state-contract.md). Sol then fills
   one contract containing nonempty `goals`, `non_goals`,
   `allowed_paths`, `forbidden_changes`, `acceptance_criteria`, and
   `test_commands`, but leaves `locked: false`. Lock it with the bundled
   `lock` command so the tool records `lock_sha256` and the first transition.
   The locked contract is the sole scope authority for the run; never edit it
   after locking.

At every direct implementation start, call `get_goal`. If no active Goal
exists, automatically call `create_goal` with the current implementation
objective, then call `get_goal` again and record its normalized receipt with
`goal-sync --mode bound`. Reuse a compatible active Goal. A conflicting active
Goal requires `HW_USER_DECISION_REQUIRED`; unavailable or failed Goal tooling
stops with `HW_GOAL_REQUIRED`. Once a bound receipt is in Goal history, later
syncs cannot downgrade it; every bound receipt and the eventual completion sync
retain the same Goal thread/objective pair. A Goal receipt never expands the
locked scope or authority.

If the current request conflicts with the approved spec or locked contract, do
not silently expand or reinterpret scope. Set the run/unit to `awaiting_user`,
record `HW_SCOPE_DRIFT` or `HW_USER_DECISION_REQUIRED` with a plain explanation,
evidence, recovery/next action, and ask the user.

For a bound Goal, `goal-sync` may receive `--token-total <nonnegative-int>`.
It records that value only as a `codex.get_goal` token receipt; without it,
and for `no_active_goal` or `unavailable`, token availability remains
`unavailable`. After local completion, `goal-complete-sync` requires
`--token-total` for `completed` or `already_completed`; `failed` forbids it and
preserves the prior token receipt. `goal-sync` rolls back `run.json` on
validation failure. `goal-complete-sync` regenerates canonical
`report-data.json` and `report.html` and rolls back `run.json`, both artifacts,
and their receipt byte-for-byte on failure.

## Goal binding

At every direct implementation start, Sol calls `get_goal`. If no active Goal
exists, Sol automatically calls `create_goal` with the current objective and
then calls `get_goal` again. A compatible active Goal is reused; a conflicting
active Goal requires `HW_USER_DECISION_REQUIRED`. Sol records the bound receipt
with `goal-sync` and binds its objective, non-goals,
proof, and checkpoint to the locked contract. Local state and a Goal never
expand locked scope or authority. A bound Goal history is sticky: no later
`no_active_goal` or `unavailable` downgrade is valid, and completion sync keeps
the same thread/objective pair. If Goal tooling is unavailable or fails, stop
with `HW_GOAL_REQUIRED`. A direct request does not need a PR/FAQ path; approved
PR/FAQ remains a separate mode. After
completion, improvement candidates are report-only; do not implement one
until the user approves a new Goal or scope.


## Detailed contracts

Read only the reference needed for the current operation:

- For unit execution, receipts, failures, and recursive recovery, read [references/execution-review.md](references/execution-review.md).
- For state and report persistence, read [references/reporting.md](references/reporting.md).
- Follow [references/protocol.md](references/protocol.md) and its routed review/report continuation before orchestration.
- Use [references/state-contract.md](references/state-contract.md) as the router for exact JSON state fields.
- For report rendering or review, also read [references/material3-report.md](references/material3-report.md).
