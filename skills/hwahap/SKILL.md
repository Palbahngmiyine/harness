---
name: hwahap
description: "Execute an explicitly approved `status: prfaq` implementation spec with Sol/Luna/Terra orchestration, atomic units, plan-drift control, structured evidence, and time/token reporting. Trigger for implementation or orchestration requests; do not trigger for ideation, grilling, or unapproved specs."
---

# Hwahap

Use this skill only to execute an implementation request against an explicitly
provided PR/FAQ path. The current request is authoritative over stored context.
Resolve `<hwahap-skill-dir>` from this loaded `SKILL.md`; it may be installed
outside the target workspace.
The approved PR/FAQ is an input and may live outside the target repository;
never copy it into that repository's `docs/prfaq`. Hwahap requires no login,
API key, access token, or other credential and rejects such values in state.
`token_total` means a numeric model-usage receipt, not an authentication token.

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

1. Workspace and spec paths must be existing regular directories/files with no
   symlink in any lexical ancestor. An unsafe workspace returns
   `HW_STATE_INVALID`; an unsafe spec returns `HW_SPEC_UNCONFIRMED`. Preserve
   state and request a real path. In plain terms: the path must point directly
   to the intended workspace/spec. A real directory plus real `spec.md` passes;
   `workspace-link/spec.md` or a symlinked ancestor fails before reading and the
   next action is to provide the real path.
2. The spec must be readable UTF-8 with `status: prfaq` and nonempty
   `confirmed_at`. Any failure returns `HW_SPEC_UNCONFIRMED` with bounded
   evidence and a request for a confirmed accessible PR/FAQ. In plain terms:
   approval must be visible in the file. Matching frontmatter passes; a draft,
   invalid UTF-8, or changed bytes after `init` fails and work stops.
3. Installed profiles must be the exact five Hwahap source profiles, each a
   regular byte-identical file with the source role metadata:
   `hwahap-luna-implementer` (Luna/high/workspace-write), `hwahap-luna-verifier`
   (Luna/xhigh/read-only), `hwahap-sol-final-reviewer` (Sol/read-only with no
   configured effort), `hwahap-sol-orchestrator` (Sol/xhigh/Fast/workspace-write), and
   `hwahap-terra-scope-reviewer` (Terra/xhigh/read-only). The installer must
   return `HW_OK`; otherwise return
   `HW_AGENT_CONFIG_INVALID`, do not overwrite conflicts or
   `.codex/config.toml`, and repair the installation. In plain terms: every
   named role must be the expected file. Five byte-identical profiles pass; a
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
2. Before execution, read [references/protocol.md](references/protocol.md).
   Require the user to provide the exact PR/FAQ path. Read its frontmatter and
   require both `status: prfaq` and `confirmed_at`. If the path is absent,
   inaccessible, or fails either check, return `HW_SPEC_UNCONFIRMED` with the
   reason, evidence, and next action, then stop. Never infer approval from a
   draft, title, conversation, or stored context.
3. Install the project-scoped custom agents before initializing state:

   `<absolute-hwahap-skill-dir>/scripts/install-project-agents --workspace <workspace>`

   Require `HW_OK`. A conflict or path/source error is a stable failure; record
   its code and bounded evidence and stop. The installer never edits
   `.codex/config.toml` and never overwrites a different existing profile.
4. Run the bundled initializer once the installer succeeds:

   `<absolute-hwahap-skill-dir>/scripts/hwahap init --workspace <workspace> --goal-id <goal-id> --spec <approved-prfaq-path>`

   Treat any non-zero result as a stable failure; record its code and evidence
   and stop unless the defined recovery is safe and in scope.

   Initialization constructs and scans the complete initial state in memory
   before creating the run directory; sensitive title or source
   inputs fail with a generic `HW_STATE_INVALID` and no state files are made.
5. Before Sol writes or validates state, read
   [references/state-contract.md](references/state-contract.md). Sol then fills
   one contract containing nonempty `goals`, `non_goals`,
   `allowed_paths`, `forbidden_changes`, `acceptance_criteria`, and
   `test_commands`, but leaves `locked: false`. Lock it with the bundled
   `lock` command so the tool records `lock_sha256` and the first transition.
   The locked contract is the sole scope authority for the run; never edit it
   after locking.

After `init`, if the user explicitly requested a Goal or `get_goal` observes
an active Goal, record its normalized receipt with `goal-sync --mode bound`.
If the receipt confirms no active Goal, use `--mode no_active_goal`; if the
tool is unavailable, use `--mode unavailable` with manual evidence. Once a
bound receipt is in Goal history, later syncs cannot downgrade to
`no_active_goal` or `unavailable`; every bound receipt and the eventual
completion sync retain the same Goal thread/objective pair. A Goal receipt
never expands the locked scope or authority.

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

When the user explicitly requests a Goal, Sol may call `create_goal`; otherwise
Sol never creates one automatically. Sol uses `get_goal` to inspect an active
Goal, records the receipt with `goal-sync`, and binds its objective, non-goals,
proof, and checkpoint to the locked contract. Local state and a Goal never
expand locked scope or authority. A bound Goal history is sticky: no later
`no_active_goal` or `unavailable` downgrade is valid, and completion sync keeps
the same thread/objective pair. If Goal tooling is unavailable, Sol uses the
manual contract/state path and records the unavailable API and evidence. After
completion, improvement candidates are report-only; do not implement one
until the user approves a new Goal or scope.


## Detailed contracts

Read only the reference needed for the current operation:

- For unit execution, receipts, failures, and recursive recovery, read [references/execution-review.md](references/execution-review.md).
- For state and report persistence, read [references/reporting.md](references/reporting.md).
- Follow [references/protocol.md](references/protocol.md) and its routed review/report continuation before orchestration.
- Use [references/state-contract.md](references/state-contract.md) as the router for exact JSON state fields.
- For report rendering or review, also read [references/material3-report.md](references/material3-report.md).
