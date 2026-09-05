---
name: hwahap
description: "Turn an implementation or refactoring request into a confirmed plan, then build, test, independently review, and open a draft PR with Codex native sub-agents. Never for questions, documentation-only work, or ideation."
---

# Hwahap

Call `hwahap_step` with the repository path and the user's request. Follow the MCP server's
`instructions`; it owns scheduling, scope, tests, commits, and publication gates.

Forward user messages verbatim in `user_input`. Never invent, complete, or infer a decision,
`CONFIRM PLAN`, or `SHIP` line. Call `hwahap_ship` only for the user's exact `SHIP <challenge>`.

Follow `next`:

- `continue`: call `hwahap_step` again.
- `native_dispatch`: execute the exact returned native dispatch using the server protocol.
  Use one Codex native child with `fork_turns=none`, the requested model/effort and exact brief.
  Only an already-Astra host may handle a `coordinator_allowed` planning role itself.
  Register the returned agent ID immediately; never create two children for one dispatch.
- `native_wait`: for `agent_id=coordinator`, perform the planning role here and send completion;
  otherwise wait for the registered child, or poll after one second during host validation.
  Relay exact final text after the child and its commands stop. Usage is null unless tools report it.
- `native_paused`: show the recorded failure; stop polling, spawning, and new requests.
  Preserve this run; resume only with new observed host recovery evidence under the server protocol.
- `native_stop`: stop the exact child (or this coordinator task) and its commands, then acknowledge.
  Do not acknowledge an uncertain stop; locate unregistered children by `hwahap_<dispatch_id>`.
- `await_user`: show `message` and wait for the user.
- `completed` or `blocked`: show `message` and stop.

Outside the assigned dispatch, do not edit files, run tests, spawn agents, or create branches/PRs.
Final review always uses an independent child. Native workers must not invoke Hwahap recursively.
Record spawn failures or unavailable native tools through the server protocol; never repeat spawn,
use ACP/CLI substitutes, or fabricate results. Requested settings and read-only instructions are
not independent proof of the applied model or OS isolation. Unknown usage is never zero cost.

Use `hwahap_status` for progress and cost evidence. Installation and scope are in [README.md](README.md).
For staged runs and capacity recovery, read [OPERATIONS.md](OPERATIONS.md).
