# Hwahap v2 release checklist

- [ ] `jq --version`, `gh auth status`, and `git check-ignore -q .hwahap` pass in the target repository.
- [ ] The first direct `codex exec` escalation is approved; verify whether `~/.codex/rules/default.rules` recorded the allow rule and document the manual fallback if it did not.
- [ ] Run one small real-model goal and compare its `summary.json` with the retained v1 baseline.
- [ ] Reconfirm `--ignore-user-config`: MCP absent, web search explicitly disabled for workers, global `AGENTS.md` behavior recorded.
- [ ] Merge `hooks/hooks.json`, restart Codex, and observe all four hook payloads.
- [ ] Deliver once to a real remote and verify the PR remains draft with no auto-merge.
- [ ] With no improve signal, verify no nested model call and a recorded skip reason.
- [ ] Run at least two workers concurrently and record the batch cache-hit ratio.
- [ ] Confirm old run directories remain readable or record the incompatibility explicitly.
- [ ] Compare `data/prices.json.updated_at` with the current official API pricing page.
- [ ] Run `tests/all.sh`, Bats, ShellCheck, kcov, mutation, resource, and both CI operating systems.
