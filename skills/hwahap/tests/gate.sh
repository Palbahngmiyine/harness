#!/bin/bash
# Exercise every Stop gate family, align non-blocking mode, and durable reports.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-gate.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo" codex_home="$tmp/codex"
mkdir -p "$repo/src" "$repo/.hwahap/out/review"
git -C "$repo" init -q
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"
git -C "$repo" add src && git -C "$repo" commit -qm base
cp "$root/tests/fixtures/check/valid/goal.json" "$repo/.hwahap/goal.json"

digest() { shasum -a 256 | awk '{print "sha256:" $1}'; }
prompt() {
  jq -nc --arg cwd "$repo" --arg prompt "$1" '{cwd:$cwd,prompt:$prompt}' |
    CODEX_HOME="$codex_home" HWAHAP_NOW=2026-09-02T00:00:00Z "$root/hooks/prompt.sh"
}
prompt 'C1=ALT1 C2=ALT1 S2=NA S3=NA S4=NA S5=NA S6=NA S7=NA S8=NA S9=NA S10=NA S11=NA S12=NA'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '
  .choices |= map(. as $c | .answer.choice_sha256=([$a[] | select(.key==$c.id)][-1].bound_sha256)) |
  .surfaces.not_applicable |= with_entries(.key as $k | .value.answer.hash=([$a[] | select(.key==$k)][-1].bound_sha256))' \
  "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
jq -r -f "$root/jq/render.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/align.md"
prompt 'CONFIRM ALIGN'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '([$a[] | select(.key=="CONFIRM")][-1]) as $c |
  .confirm={text:$c.text,ts:$c.ts,revision:.revision,goal_sha256:$c.bound_sha256,render_sha256:$c.render_sha256}' \
  "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
repo_id=$(printf '%s' "$(git -C "$repo" rev-parse --show-toplevel)" | digest | cut -c8-23)
outside="$codex_home/hwahap/$repo_id/answers.jsonl"
cp "$repo/.hwahap/goal.json" "$tmp/base-goal"
cp "$repo/.hwahap/answers.jsonl" "$tmp/base-answers"

git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
printf 'unit1\n' >"$repo/.hwahap/wt/U1/src/check.sh"
git -C "$repo/.hwahap/wt/U1" diff HEAD >"$repo/.hwahap/out/U1.patch"
printf 'exit 0\n' >"$repo/.hwahap/out/U1.test.txt"
printf '1\n' >"$repo/.hwahap/out/U1.attempt"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U1.md"
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/out/U1.events.jsonl"
jq -s --slurpfile prices "$root/data/prices.json" --arg unit U1 --arg attempt 1 --arg model gpt-5.6-luna --arg effort high --arg started s --arg ended e --arg seconds 2 \
  -f "$root/jq/usage.jq" "$repo/.hwahap/out/U1.events.jsonl" >"$repo/.hwahap/out/U1.usage.1.json"
cp "$repo/.hwahap/out/U1.usage.1.json" "$repo/.hwahap/out/U1.usage.json"
git -C "$repo" worktree add -q --detach .hwahap/wt/integration HEAD
git -C "$repo/.hwahap/wt/integration" apply ../../out/U1.patch
printf 'exit 0\n' >"$repo/.hwahap/out/integration.test.txt"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/integration.md"
session_id=11111111-2222-3333-4444-555555555555
mkdir -p "$codex_home/sessions/2026/09/02"
printf '%s\n' '{"payload":{"type":"token_count","info":{"total_token_usage":{"total_tokens":4321}}}}' >"$codex_home/sessions/2026/09/02/rollout-fixture-$session_id.jsonl"
payload=$(jq -nc --arg cwd "$repo" --arg session_id "$session_id" '{cwd:$cwd,session_id:$session_id,stop_hook_active:false}')

run_gate() { (cd "$repo" && CODEX_HOME="$codex_home" HWAHAP_UNATTENDED=1 "$root/hooks/gate.sh" <<<"$payload") 2>"$tmp/gate.err"; }
expect_block() {
  output=$(run_gate)
  printf '%s' "$output" | jq -e --arg reason "$1" '.decision=="block" and (.reason | contains($reason))' >/dev/null
}
restore_goal() { cp "$tmp/base-goal" "$repo/.hwahap/goal.json"; cp "$tmp/base-answers" "$repo/.hwahap/answers.jsonl"; cp "$tmp/base-answers" "$outside"; }
rewrite_confirm() {
  line=$(tail -n 1 "$repo/.hwahap/answers.jsonl" | jq -c --arg bound "$(jq -r '.confirm.goal_sha256' "$repo/.hwahap/goal.json")" --arg render "$(jq -r '.confirm.render_sha256' "$repo/.hwahap/goal.json")" '.bound_sha256=$bound | .render_sha256=$render | del(.hash)')
  hash=$(printf '%s' "$line" | jq -S -c . | digest)
  line=$(printf '%s' "$line" | jq -c --arg hash "$hash" '.hash=$hash')
  sed '$d' "$repo/.hwahap/answers.jsonl" >"$tmp/answers"; printf '%s\n' "$line" >>"$tmp/answers"
  mv "$tmp/answers" "$repo/.hwahap/answers.jsonl"; cp "$repo/.hwahap/answers.jsonl" "$outside"
}
rebind_goal() {
  bound=$(jq -S -c 'del(.review,.confirm)' "$repo/.hwahap/goal.json" | digest)
  jq --arg bound "$bound" '.confirm.goal_sha256=$bound' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
  rewrite_confirm
}

mv "$repo/.hwahap/out/U1.attempt" "$tmp/attempt"
jq '.confirm.goal_sha256="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"' "$tmp/base-goal" >"$repo/.hwahap/goal.json"
test -z "$(run_gate)"
mv "$tmp/attempt" "$repo/.hwahap/out/U1.attempt"; restore_goal
jq '.confirm.goal_sha256="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"' "$tmp/base-goal" >"$repo/.hwahap/goal.json"
expect_block 'goal hash'; restore_goal
printf '%s\n' '{"extra":true}' >>"$repo/.hwahap/answers.jsonl"
expect_block 'copies differ'; restore_goal
grep -v '"key":"S2"' "$tmp/base-answers" >"$repo/.hwahap/answers.jsonl"; cp "$repo/.hwahap/answers.jsonl" "$outside"
expect_block 'not bound'; restore_goal
jq '.confirm.render_sha256="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"; rewrite_confirm
expect_block 'render is stale'; restore_goal
jq -c 'if input_line_number==1 then .hash="sha256:ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff" else . end' "$repo/.hwahap/answers.jsonl" >"$tmp/answers"; mv "$tmp/answers" "$repo/.hwahap/answers.jsonl"; cp "$repo/.hwahap/answers.jsonl" "$outside"
expect_block 'answer hash is invalid'; restore_goal

mv "$repo/.hwahap/out/U1.patch" "$tmp/patch"; expect_block 'patch is missing'; mv "$tmp/patch" "$repo/.hwahap/out/U1.patch"
: >"$repo/.hwahap/out/U1.needs_decision"; expect_block 'decision is unresolved'; rm "$repo/.hwahap/out/U1.needs_decision"
cp "$repo/.hwahap/out/U1.patch" "$tmp/patch"; printf 'outside\n' >"$repo/.hwahap/wt/U1/outside.txt"; git -C "$repo/.hwahap/wt/U1" add -N outside.txt; git -C "$repo/.hwahap/wt/U1" diff HEAD >"$repo/.hwahap/out/U1.patch"
expect_block 'escaped scope'; cp "$tmp/patch" "$repo/.hwahap/out/U1.patch"
printf 'verdict: fail\n' >"$repo/.hwahap/out/review/U1.md"; expect_block 'review failed'; printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U1.md"
printf 'exit 1\n' >"$repo/.hwahap/out/integration.test.txt"; expect_block 'integration test failed'; printf 'exit 0\n' >"$repo/.hwahap/out/integration.test.txt"
printf 'verdict: fail\n' >"$repo/.hwahap/out/review/integration.md"; expect_block 'integration review failed'; printf 'verdict: pass\n' >"$repo/.hwahap/out/review/integration.md"
printf '2026-09-01T00:00:00Z\n' >"$repo/.hwahap/human.turn"; expect_block 'predates human'; printf '2026-09-02T00:00:00Z\n' >"$repo/.hwahap/human.turn"
jq '.final_review="bad"' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"; rebind_goal
expect_block 'goal contract'; restore_goal
mkdir -p "$repo/.hwahap/facts"; printf 'fact\n' >"$repo/.hwahap/facts/F1.md"; fact_hash=$(digest <"$repo/.hwahap/facts/F1.md")
jq --arg hash "$fact_hash" '.facts=[{id:"F1",path:".hwahap/facts/F1.md",sha256:$hash}]' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"; rebind_goal; printf 'changed\n' >"$repo/.hwahap/facts/F1.md"
expect_block 'fact hash changed'; restore_goal
printf 'unit1\nAKIA1234567890ABCDEF\n' >"$repo/.hwahap/wt/integration/src/check.sh"; expect_block 'secret pattern'; printf 'unit1\n' >"$repo/.hwahap/wt/integration/src/check.sh"

test -z "$(run_gate)"
jq -e '.units_total==1 and .units_passed==1 and .first_try_pass==1 and .tokens.workers==1800 and .tokens.orchestrator==4321 and .units[0].cache_hit_ratio==0.4 and .units[0].reasoning_ratio==(1/3) and .cache_hit_ratio==0.4 and .deliver=="skipped:unattended"' "$repo/.hwahap/summary.json" >/dev/null
test -f "$repo/.hwahap/report.md"
test -f "$codex_home/hwahap/$repo_id/runs/2026-09-02-test/summary.json"
headings=$(grep '^## ' "$repo/.hwahap/report.md" | tr '\n' '|')
test "$headings" = '## 결론|## 근거|## 확인 과정|## 한계|## 비용|'
printf 'gate failures=12 align=nonblocking report=durable\n'
