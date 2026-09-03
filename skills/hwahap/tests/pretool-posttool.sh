#!/bin/bash
# Verify all eight worker gates plus fact, cold, and reviewer reductions.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-pretool.XXXXXX")
if [ "${KEEP_TMP:-}" = 1 ]; then printf 'fixture: %s\n' "$tmp"; else trap 'rm -rf "$tmp"' EXIT; fi
repo="$tmp/repo" codex_home="$tmp/codex"
mkdir -p "$repo/.hwahap/out/review" "$repo/src"
git -C "$repo" init -q
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"
git -C "$repo" add src/check.sh && git -C "$repo" commit -qm base
git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
cp "$root/tests/fixtures/check/valid/goal.json" "$repo/.hwahap/goal.json"

prompt() {
  jq -nc --arg cwd "$repo" --arg prompt "$1" '{cwd:$cwd,prompt:$prompt}' |
    CODEX_HOME="$codex_home" HWAHAP_NOW=2026-09-02T00:00:00Z "$root/hooks/prompt.sh"
}
prompt 'C1=ALT1 C2=ALT1 S2=NA S3=NA S4=NA S5=NA S6=NA S7=NA S8=NA S9=NA S10=NA S11=NA S12=NA'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '
  .choices |= map(. as $c | .answer.choice_sha256=([$a[] | select(.key==$c.id)][-1].bound_sha256)) |
  .surfaces.not_applicable |= with_entries(.key as $k | .value.answer.hash=([$a[] | select(.key==$k)][-1].bound_sha256))' \
  "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/cold.md"
cold='codex exec -C . -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral --json -o .hwahap/out/review/cold.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$cold" '{cwd:$cwd,tool_input:{command:$command}}')
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/out/review/cold.events.jsonl"
test "$(cd "$repo" && HWAHAP_NOW=2026-09-02T00:00:00Z "$root/hooks/posttool.sh" <<<"$payload")" = 'cold review pass'
jq -r -f "$root/jq/render.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/align.md"
prompt 'CONFIRM ALIGN'
jq --slurpfile a "$repo/.hwahap/answers.jsonl" '([$a[] | select(.key=="CONFIRM")][-1]) as $c |
  .confirm={text:$c.text,ts:$c.ts,revision:.revision,goal_sha256:$c.bound_sha256,render_sha256:$c.render_sha256}' \
  "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
jq -e -f "$root/jq/check.jq" "$repo/.hwahap/goal.json" >/dev/null
jq -r --rawfile head "$root/data/brief.head.md" --arg mode worker --arg unit U1 --arg patch '' --arg question '' \
  -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/U1.brief.md"
cp "$repo/.hwahap/goal.json" "$tmp/base-goal"
cp "$repo/.hwahap/out/U1.brief.md" "$tmp/base-brief"

worker='codex exec -C .hwahap/wt/U1 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled -c tool_output_token_limit=4000 --ephemeral --json -o .hwahap/out/U1.last.md'
run_pretool() {
  jq -nc --arg cwd "$repo" --arg command "$1" '{cwd:$cwd,tool_input:{command:$command}}' |
    CODEX_HOME="$codex_home" "$root/hooks/pretool.sh" 2>"$tmp/pretool.err"
}
expect_deny() {
  output=$(run_pretool "$1")
  printf '%s' "$output" | jq -e --arg reason "$2" '.hookSpecificOutput.permissionDecision=="deny" and (.hookSpecificOutput.permissionDecisionReason | contains($reason))' >/dev/null
}
test -z "$(run_pretool "$worker")"
expect_deny "${worker/ --json/}" 'required codex exec flags'
expect_deny "${worker/gpt-5.6-luna/gpt-5.6-terra}" 'model or effort differs from settings'
expect_deny "${worker/model_reasoning_effort=high/model_reasoning_effort=medium}" 'model or effort differs from settings'
jq '(.units[] | select(.id=="U1")) |= (.model="gpt-5.6-terra" | .effort="medium")' "$tmp/base-goal" >"$repo/.hwahap/goal.json"
override=${worker/gpt-5.6-luna/gpt-5.6-terra}; override=${override/model_reasoning_effort=high/model_reasoning_effort=medium}
expect_deny "$worker" 'model or effort differs from settings'
(cd "$repo" && "$root/hooks/lib/usage.sh" validate "$override" .hwahap/wt/U1 workspace-write .hwahap/out/U1.last.md U1)
cp "$tmp/base-goal" "$repo/.hwahap/goal.json"
jq '.schema="bad"' "$tmp/base-goal" >"$repo/.hwahap/goal.json"
expect_deny "$worker" 'goal contract'
cp "$tmp/base-goal" "$repo/.hwahap/goal.json"
printf 'tamper\n' >>"$repo/.hwahap/out/U1.brief.md"
expect_deny "$worker" 'brief differs'
cp "$tmp/base-brief" "$repo/.hwahap/out/U1.brief.md"

printf 'patch\n' >"$repo/.hwahap/out/U1.patch"
printf 'exit 0\n' >"$repo/.hwahap/out/U1.test.txt"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U1.md"
test -z "$(run_pretool "$worker")"
shasum -a 256 "$repo/.hwahap/out/U1.brief.md" | awk '{print "sha256:" $1}' >"$repo/.hwahap/out/U1.brief.sha256"
expect_deny "$worker" cached
rm "$repo/.hwahap/out/U1.patch" "$repo/.hwahap/out/U1.test.txt" "$repo/.hwahap/out/review/U1.md" "$repo/.hwahap/out/U1.brief.sha256"
: >"$repo/.hwahap/out/U1.needs_decision"
expect_deny "$worker" 'decision is unresolved'
rm "$repo/.hwahap/out/U1.needs_decision"

jq -n '{input_tokens:499900,output_tokens:100}' >"$repo/.hwahap/out/U1.usage.1.json"
expect_deny "$worker" 'budget is exhausted'
rm "$repo/.hwahap/out/U1.usage.1.json"
jq -n '{input_tokens:499900,output_tokens:100}' >"$repo/.hwahap/out/review/U1.usage.1.json"
expect_deny "$worker" 'budget is exhausted'
rm "$repo/.hwahap/out/review/U1.usage.1.json"
mkdir -p "$repo/.hwahap/facts"; jq -n '{input_tokens:499900,output_tokens:100}' >"$repo/.hwahap/facts/F1.usage.json"
expect_deny "$worker" 'budget is exhausted'
rm "$repo/.hwahap/facts/F1.usage.json"
printf '2\n' >"$repo/.hwahap/out/U1.attempt"
expect_deny "$worker" 'retry limit'
rm "$repo/.hwahap/out/U1.attempt"

jq '.units += [{id:"P1",title:"probe",paths:["src/other.sh"],test:"true",acceptance_ids:[],depends_on:["U1"],probe:true,model:null,effort:null}]' \
  "$tmp/base-goal" >"$repo/.hwahap/goal.json"
git -C "$repo" worktree add -q --detach .hwahap/wt/P1 HEAD
jq -r --rawfile head "$root/data/brief.head.md" --arg mode worker --arg unit P1 --arg patch '' --arg question '' \
  -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/P1.brief.md"
worker2=${worker//U1/P1}
expect_deny "$worker2" 'dependency U1'

cp "$tmp/base-goal" "$repo/.hwahap/goal.json"
jq '.facts=[{id:"F1",path:".hwahap/facts/F1.md",sha256:"sha256:0000000000000000000000000000000000000000000000000000000000000000"}]' \
  "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
printf 'observed\n' >"$repo/.hwahap/facts/F1.md"
fact='codex exec -C . -s read-only --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=medium --ephemeral --json -o .hwahap/facts/F1.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$fact" '{cwd:$cwd,tool_input:{command:$command}}')
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/facts/F1.events.jsonl"
rm "$repo/.hwahap/facts/F1.md"; test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'F1 fact fail'; printf 'observed\n' >"$repo/.hwahap/facts/F1.md"
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'F1 fact pass'
test "$(jq -r '.facts[0].sha256' "$repo/.hwahap/goal.json")" != 'sha256:0000000000000000000000000000000000000000000000000000000000000000'
test -f "$repo/.hwahap/facts/F1.usage.json"
test -z "$(run_pretool "$fact")"
integration='codex exec -C .hwahap/wt/integration -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral --json -o .hwahap/out/review/integration.md'
test -z "$(run_pretool "$integration")"
jq '.final_review="sol"' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
expect_deny "$integration" 'model or effort differs from settings'
test -z "$(run_pretool "${integration/gpt-5.6-terra/gpt-5.6-sol}")"
jq '.final_review="terra"' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"

printf 'bad\n' >"$repo/.hwahap/out/review/cold.md"
payload=$(jq -nc --arg cwd "$repo" --arg command "$cold" '{cwd:$cwd,tool_input:{command:$command}}')
test -z "$(run_pretool "$cold")"
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'cold review fail verdict_invalid=1'
printf 'verdict: fail\n' >"$repo/.hwahap/out/review/cold.md"
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'cold review fail'
printf 'bad\n' >"$repo/.hwahap/out/review/U1.md"
review='codex exec -C .hwahap/wt/U1 -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral --json -o .hwahap/out/review/U1.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$review" '{cwd:$cwd,tool_input:{command:$command}}')
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/out/review/U1.events.jsonl"
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'U1 review fail verdict_invalid=1'
test "$(<"$repo/.hwahap/out/review/U1.attempt")" -eq 1
test -f "$repo/.hwahap/out/review/U1.usage.1.json"
test -z "$(run_pretool "$review")"
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'U1 review fail verdict_invalid=1'
expect_deny "$review" 'reviewer retry limit'
rm "$repo/.hwahap/facts/F1.events.jsonl"; payload=$(jq -nc --arg cwd "$repo" --arg command "$fact" '{cwd:$cwd,tool_input:{command:$command}}')
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'F1 fact pass usage_error=1'
printf 'pretool gates=8 posttool fact cold reviewer\n'
