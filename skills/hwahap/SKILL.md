---
name: hwahap
description: "Turn an implementation or refactoring request into a confirmed plan, then let Hwahap build, test, review, and open a draft PR autonomously. Trigger for implementation, refactoring, or build requests; never for questions, documentation-only work, or ideation."
---

# Hwahap

Use Hwahap only for implementation or refactoring requests. For questions, documentation-only work,
or ideation, answer directly instead.

Call `hwahap_step` with the repository path and the user's request. Do not implement anything, run
tests, spawn workers, or edit files yourself: Hwahap owns the whole cycle.

Forward the user's message verbatim in `user_input`. Never write, complete, correct, or infer a
`CONFIRM PLAN` or `SHIP` line on the user's behalf, and never answer a decision for them.

Then follow `next` in the response:

- `continue` — call `hwahap_step` again immediately, without asking the user anything.
- `await_user` — show `message` and stop. Send whatever the user replies as the next `user_input`.
- `completed` or `blocked` — show `message` and stop.

Call `hwahap_status` to report progress without changing anything.

Call `hwahap_ship` only after the user has typed an exact `SHIP <challenge>` line themselves.
