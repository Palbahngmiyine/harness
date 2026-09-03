---
name: hwahap
description: "Align an implementation request into a confirmed hwahap/v2 goal, run isolated Codex workers and reviews, integrate evidence, and deliver a draft PR. Trigger for implementation or orchestration requests; never use for questions, documentation-only work, ideation, or grilling."
---

# Hwahap

The first rule is classification: do not use Hwahap for questions, documentation-only requests, ideation, or grilling. For an implementation request, keep align, build, delivery, and optional improve in the current Codex session. The user's current request is authoritative.

Resolve `<skill>` to this `SKILL.md` directory. Read applicable `AGENTS.md` files and preserve unrelated work. Hwahap needs Bash, jq, Git, gh, and Codex CLI 0.151 or newer; it has no Python runtime and creates no custom agent profiles.

## 0. Preflight

Run exactly these checks before creating `.hwahap`; report the failed command and stop if any fails.

```sh
jq --version
gh auth status
git check-ignore -q .hwahap
```

If `.hwahap` is not ignored, ask before adding it to `.gitignore`. Do not infer network approval for nested `codex exec`; on a recorded `network=1`, request the required escalation. The verified manual fallback is `prefix_rule(pattern=["codex", "exec"], decision="allow")` followed by a Codex restart.

## 1. Align

Create `.hwahap/goal.json` with schema `hwahap/v2`, the current base branch, revision 1, and the user's goal. Ask the technical stack first. Read [SURFACES.md](SURFACES.md), inspect all twelve surfaces in order, and query repository facts with the fact template instead of asking the user.

For each applicable surface add at least one `decision` and one "what happens when" `scenario`; reconcile conflicting terminology with a `term` choice. Record facts when source behavior differs from the request. For a proposed NA surface, state the reason and require `S<n>=NA`.

Present the whole dependency frontier in one round. Accept only `C<n>=ALT<n>`, `C<n>=OTHER: <value>`, `C<n>=UNKNOWN`, `S<n>=NA`, `CP<k>=OK`, and exact `CONFIRM ALIGN`. After every round, derive new choices from the answers. At rounds 4, 8, and so on, require the checkpoint. Suggest splitting above 40 choices or 6 rounds; continue only if the user declines and record that in `diary.md`.

Resolve `UNKNOWN` with a fact or reversible `probe: true` unit. When the frontier is empty, write specs, acceptance criteria, atomic units, and a DAG; then run `jq -e -f <skill>/jq/check.jq .hwahap/goal.json`. Generate and run the cold review. Convert every cold finding into a choice and repeat until its three lists are empty.

Render with `jq -r -f <skill>/jq/render.jq .hwahap/goal.json > .hwahap/align.md`, tell the user to inspect that file, explain autonomous build and draft delivery, and request `CONFIRM ALIGN`. `prompt.sh` records the human-authored stamp; do not write answer ledgers yourself.

## 2. Fixed execution templates

Only the unit id or fact question may vary. Generate every brief with `jq/brief.jq` and `data/brief.head.md`; never hand-write or print it. Because shell-wrapper rules do not match, issue each `codex exec` as a direct command and use parallel tool calls for a batch.

Worker:

```sh
codex exec -C .hwahap/wt/U1 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled -c tool_output_token_limit=4000 --ephemeral --json -o .hwahap/out/U1.last.md < .hwahap/out/U1.brief.md > .hwahap/out/U1.events.jsonl
```

Reviewer, including `cold` at `-C .` and `integration` at its worktree:

```sh
codex exec -C .hwahap/wt/U1 -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral --json -o .hwahap/out/review/U1.md < .hwahap/out/review/U1.brief.md > .hwahap/out/review/U1.events.jsonl
```

Fact worker:

```sh
codex exec -C . -s read-only --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=medium --ephemeral --json -o .hwahap/facts/F1.md < .hwahap/out/F1.brief.md > .hwahap/facts/F1.events.jsonl
```

## 3. Build

Batch dependency-ready units up to `budget.max_parallel`. Add detached worktrees, generate byte-stable worker briefs, and run the worker template. Read only the PostToolUse summary; retry a failed worker once. After the second failure ask `retry`, `skip`, or `abort`. Never run a dependent unit whose prerequisite was skipped.

Run the reviewer template for every passing unit. On `verdict: fail`, regenerate the worker brief with findings and return to the worker, up to two review rounds. PostToolUse integrates once all non-probe units are ready. Generate the integration patch brief and run the final reviewer, changing only `-m` to `gpt-5.6-sol` when `final_review` is `sol`.

A worker may decide only a reversible detail inside its unit that changes no observable behavior, named identifier, path, format, schema, stored field, dependency, concurrency, security, performance, or compatibility. Otherwise it must change nothing and put `NEEDS_DECISION: <question>` on its first final-message line. Turn that into a new choice, increment revision, repeat cold review/render/`CONFIRM ALIGN`, and resume; unchanged unit briefs are cached.

Budget notices are 50%, 80%, and 100%. At 100% ask the user before any new worker. Do not bypass a hook denial. Stop after the final integration review; Stop gate creates the ordered Markdown report, durable summary, commit, push, and draft PR. It never marks ready, merges, or enables auto-merge. `HWAHAP_UNATTENDED=1` validates but does not deliver.

## Operator boundary

The orchestrator may read only PostToolUse summary lines, the first line of `out/review/*.md`, `out/*.needs_decision`, `facts/F<n>.md`, and `report.md`. It must not read `out/*.events.jsonl`, `out/review/*.events.jsonl`, `facts/*.events.jsonl`, patches, or worker final messages. Reports are ordered conclusion, evidence, verification process, limitations, cost.

Delivery retry is another normal session stop. After the user handles the PR, remove a requested worktree with `git worktree remove .hwahap/wt/<unit>`; never delete worktrees implicitly. Improve runs only under the configured signal, cadence, benchmark, and hard-budget gates and never expands the current goal.
