---
name: hwahap
description: "Plan implementation requests through decision rounds, or build an explicitly authorized contract. Use for implementation planning, execution and draft PR review; never for general questions or documentation-only work."
---

# Hwahap

Use Astra as parent. Read and follow the MCP server's `instructions` as the execution protocol.
Call `hwahap_step` with the repository path and the same stable `host_session_id` throughout.

For planning without implementation, start `request` with `plan_only:true`; stop at `plan_ready`.
Use `build_confirmed` with the full stored plan digest only when the user explicitly requests BUILD.
An ordinary implementation `request` keeps `plan_only:false` and proceeds after plan confirmation.
When the user explicitly skips planning, use `build` with their verbatim authorization instead.
For requested repairs under unchanged contracts use `adjust_build`; contract changes reopen PLAN.

Use the server's `question_batch` and `question_response` protocol for decision rounds.
Detect actually callable Codex question tools and their limits; never invent an AskUserQuestion tool
or change Codex collaboration mode. See [USAGE.md](USAGE.md) for UI adaptation and raw answer handling.
Do not infer an answer from a default, missing response, cancellation or timeout.
Forward other user messages verbatim. Never invent, complete or infer `CONFIRM PLAN` or `SHIP`.
These two gates require the user's exact typed line, not a question-UI choice.

Follow every returned `next`, including native dispatch, wait, stop and pause recovery instructions.
Outside an assigned dispatch, do not independently edit, test, spawn or publish.
Retain the server's worker identities and roles; never invoke Hwahap recursively from a worker.
Use `hwahap_status` for progress and `recheck_pr:true` for the current draft's review recovery.
Host-reported answers, models and usage are not independent identity, isolation or billing proof.

[README.md](README.md) covers setup; [OPERATIONS.md](OPERATIONS.md) covers boundaries and recovery.
[USAGE.md](USAGE.md) covers request shapes, question UI and allowed host-side usage metering.
