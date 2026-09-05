---
name: hwahap
description: "Build, test and review implementation requests with Codex native sub-agents. Use PLAN unless the user explicitly authorizes direct BUILD. Publish a draft and run independent Astra attack and defense. Never for questions, documentation-only work or ideation."
---

# Hwahap

Use Astra as parent. Call `hwahap_step` with the repository path, stable `host_session_id`, and request.
If the user explicitly skips planning, use the server's `build` contract and verbatim authorization.
Follow the MCP server's `instructions`; it owns scheduling, scope, tests, commits, and publication gates.

Forward user messages verbatim in `user_input`. Never invent, complete, or infer a decision,
`CONFIRM PLAN`, or `SHIP` line. Call `hwahap_ship` only for the user's exact `SHIP <challenge>`.

Follow `next`:

- `continue`: call `hwahap_step` again.
- `native_dispatch`: execute the exact returned native dispatch using the server protocol.
  Retain Critic and Auditor (also Worker in PLAN mode); follow the server's spawn/follow-up protocol.
  Only new children use `fork_turns=none`; coordinator work runs in this Astra parent.
  Never create replacements, switch lanes, or change retained models/efforts.
- `native_wait`: for `agent_id=coordinator`, perform the assigned role here and send completion;
  otherwise use event-driven waits of at most 30 seconds; follow server polling instructions.
  Relay exact final text after the child and its commands stop. Usage is null unless tools report it.
- `native_paused`: show the recorded failure; stop polling, spawning, and new requests.
  Preserve this run; resume only with new observed host recovery evidence under the server protocol.
- `native_stop`: stop the exact child (or this coordinator task) and its commands, then acknowledge.
  Do not acknowledge an uncertain stop; locate unregistered children by `hwahap_<dispatch_id>`.
- `await_user`: show `message` and wait for the user.
- `completed` or `blocked`: show `message` and stop.

Outside the assigned dispatch, do not edit files, run tests, spawn agents, or create branches/PRs.
After draft publication, distinct Astra Critic/Auditor check defects and mandatory security coverage; parent repairs.
Use `recheck_pr=true` to recheck this run's draft. Native workers must not invoke Hwahap recursively.
Record spawn failures or unavailable native tools through the server protocol; never repeat spawn,
use ACP/CLI substitutes, or fabricate results. Requested settings and read-only instructions are
not independent proof of the applied model or OS isolation. Unknown usage is never zero cost.

Use `hwahap_status` for progress; host-side [usage metering](USAGE.md) is allowed. See [README.md](README.md).
For staged runs and capacity recovery, read [OPERATIONS.md](OPERATIONS.md).
