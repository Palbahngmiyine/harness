#!/bin/bash
# Block an incomplete build, then publish its report and durable run record.
set -euo pipefail
[ "${HWAHAP_DISABLE_HOOKS:-}" = 1 ] && exit 0
payload=$(</dev/stdin)
printf '%s' "$payload" | jq -e . >/dev/null 2>&1 || { printf 'hwahap gate: invalid hook payload\n' >&2; exit 1; }
[ "$(printf '%s' "$payload" | jq -r '.stop_hook_active // false')" = false ] || exit 0
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty'); [ -n "$cwd" ] || exit 0
cd "$cwd" || exit 0
goal=.hwahap/goal.json; [ -f "$goal" ] || exit 0
skill=$(cd "$(dirname "$0")/.." && pwd)
building=0; compgen -G '.hwahap/out/U*.attempt' >/dev/null && building=1
fail() { printf 'hwahap gate: %s\n' "$1" >&2; if [ "$building" -eq 1 ]; then jq -nc --arg reason "$1" '{decision:"block",reason:$reason}'; fi; exit 0; }
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print "sha256:" $1}'; else shasum -a 256 | awk '{print "sha256:" $1}'; fi; }
goal_hash=$(jq -S -c 'del(.review,.confirm)' "$goal" | sha)
[ "$(jq -r '.confirm.goal_sha256 // empty' "$goal")" = "$goal_hash" ] || fail 'confirmation goal hash is stale'
jq -e '.confirm.revision==.revision' "$goal" >/dev/null || fail 'confirmation revision is stale'
repo=$(git rev-parse --show-toplevel); repo_id=$(printf '%s' "$repo" | sha | cut -c8-23)
outside="${CODEX_HOME:-$HOME/.codex}/hwahap/$repo_id/answers.jsonl"
[ -f .hwahap/answers.jsonl ] || fail 'workspace answer ledger is missing'
[ -f "$outside" ] || fail 'outside answer ledger is missing'
jq -e -s . .hwahap/answers.jsonl >/dev/null || fail 'answer ledger is malformed'
while IFS= read -r line; do grep -Fqx "$line" "$outside" || fail 'answer ledger copies differ'; done <.hwahap/answers.jsonl
jq -e --slurpfile a .hwahap/answers.jsonl 'all(.choices[] | select(.answer!=null); . as $c | any($a[]; .key==$c.id and .text==$c.answer.text and .bound_sha256==$c.answer.choice_sha256)) and all(.surfaces.not_applicable | to_entries[]; . as $s | any($a[]; .key==$s.key and .text==$s.value.answer.text and .bound_sha256==$s.value.answer.hash)) and all(.rounds[] | select((.n%4)==0); . as $r | any($a[]; .key==("CP"+(($r.n/4)|tostring)) and .text==$r.checkpoint.answer.text and .bound_sha256==$r.checkpoint.answer.hash)) and (.confirm as $c | any($a[]; .key=="CONFIRM" and .bound_sha256==$c.goal_sha256 and .render_sha256==$c.render_sha256))' "$goal" >/dev/null || fail 'answers are not bound to the current goal'
render_hash=$(jq -r -f "$skill/jq/render.jq" "$goal" | sha)
[ "$(jq -r '.confirm.render_sha256 // empty' "$goal")" = "$render_hash" ] || fail 'confirmed render is stale'
prev=null
while IFS= read -r line; do
  [ "$(printf '%s' "$line" | jq -r '.prev')" = "$prev" ] || fail 'answer hash chain is discontinuous'
  stored=$(printf '%s' "$line" | jq -r '.hash'); actual=$(printf '%s' "$line" | jq -S -c 'del(.hash)' | sha)
  [ "$stored" = "$actual" ] || fail 'answer hash is invalid'; prev=$stored
done <.hwahap/answers.jsonl
jq -e -f "$skill/jq/check.jq" "$goal" >/dev/null 2>&1 || fail 'goal contract is invalid'
jq -e 'any(.open_items[]; .status=="open") | not' "$goal" >/dev/null || fail 'open items remain'
while IFS=$'\t' read -r path digest; do [ -f "$path" ] || fail "fact is missing: $path"; [ "$(sha <"$path")" = "$digest" ] || fail "fact hash changed: $path"; done < <(jq -r '.facts[] | [.path,.sha256] | @tsv' "$goal")
[ "$building" -eq 1 ] || exit 0
compgen -G '.hwahap/out/*.needs_decision' >/dev/null && fail 'a worker decision is unresolved'
while IFS= read -r unit; do
  [ ! -f ".hwahap/out/$unit.skipped" ] || continue
  [ -f ".hwahap/out/$unit.patch" ] || fail "$unit patch is missing"
  [ "$(tail -n 1 ".hwahap/out/$unit.test.txt" 2>/dev/null)" = 'exit 0' ] || fail "$unit test failed"
  [ "$(head -n 1 ".hwahap/out/review/$unit.md" 2>/dev/null)" = 'verdict: pass' ] || fail "$unit review failed"
  while IFS=$'\t' read -r _ _ path; do allowed=$(jq -r --arg unit "$unit" --arg path "$path" 'any(.units[] | select(.id==$unit) | .paths[]; . as $p | $path==$p or ($path|startswith($p+"/")))' "$goal"); [ "$allowed" = true ] || fail "$unit patch escaped scope: $path"; done < <(git apply --numstat ".hwahap/out/$unit.patch")
done < <(jq -r '.units[] | select(.probe|not) | .id' "$goal")
[ "$(tail -n 1 .hwahap/out/integration.test.txt 2>/dev/null)" = 'exit 0' ] || fail 'integration test failed'
[ "$(head -n 1 .hwahap/out/review/integration.md 2>/dev/null)" = 'verdict: pass' ] || fail 'integration review failed'
while IFS= read -r path; do allowed=$(jq -r --arg path "$path" 'any(.units[] | select(.probe|not) | .paths[]; . as $p | $path==$p or ($path|startswith($p+"/")))' "$goal"); [ "$allowed" = true ] || fail "integration escaped scope: $path"; done < <(git -C .hwahap/wt/integration diff --name-only HEAD)
[ -f .hwahap/human.turn ] || fail 'human turn marker is missing'
confirm_ts=$(jq -r '.confirm.ts' "$goal"); [[ "$(<.hwahap/human.turn)" < "$confirm_ts" ]] && fail 'build predates human confirmation'
git -C .hwahap/wt/integration diff HEAD | grep -E -f "$skill/data/secrets.regex" >/dev/null && fail 'integration diff contains a secret pattern'
units_total=$(jq '[.units[] | select(.probe|not)] | length' "$goal"); passed=0; cached=0; first_try=0
while IFS= read -r unit; do [ -f ".hwahap/out/$unit.skipped" ] && continue; passed=$((passed+1)); [ ! -f ".hwahap/out/$unit.cached" ] || cached=$((cached+1)); [ "$(<".hwahap/out/$unit.attempt")" -ne 1 ] || first_try=$((first_try+1)); done < <(jq -r '.units[] | select(.probe|not) | .id' "$goal")
receipts='[]'; usage_files=(.hwahap/out/*.usage.[0-9]*.json); if [ -e "${usage_files[0]}" ]; then receipts=$(jq -s . "${usage_files[@]}"); fi
metrics=$(jq -nc --argjson r "$receipts" '{tokens:([$r[].input_tokens+$r[].output_tokens]|add//0),input:([$r[].input_tokens]|add//0),cached:([$r[].cached_input_tokens]|add//0),cost:([$r[].cost_usd]|add//0),seconds:([$r[].seconds]|add//0)}')
tokens=$(printf '%s' "$metrics" | jq '.tokens'); cost=$(printf '%s' "$metrics" | jq '.cost'); seconds=$(printf '%s' "$metrics" | jq '.seconds'); cache=$(printf '%s' "$metrics" | jq 'if .input==0 then 0 else .cached/.input end')
goal_id=$(jq -r '.goal_id' "$goal"); revision=$(jq '.revision' "$goal"); base=$(jq -r '.base_branch' "$goal"); max_parallel=$(jq '.budget.max_parallel' "$goal")
jq -n --arg id "$goal_id" --arg base "$base" --argjson revision "$revision" --argjson total "$units_total" --argjson passed "$passed" --argjson cached "$cached" --argjson first "$first_try" --argjson tokens "$tokens" --argjson cache "$cache" --argjson cost "$cost" --argjson seconds "$seconds" --argjson parallel "$max_parallel" '{goal_id:$id,revision:$revision,base_branch:$base,units_total:$total,units_passed:$passed,units_cached:$cached,first_try_pass:$first,tokens:{workers:$tokens,reviewers:0,facts:0,orchestrator:0},cache_hit_ratio:$cache,cost_usd:$cost,cost_per_passed_unit:(if $passed==0 then 0 else $cost/$passed end),seconds:$seconds,pr_url:null,deliver:"skipped:pending",improve:{signal:"none",started:false,reason:"not evaluated"},config:{worker_model:"gpt-5.6-luna",worker_effort:"high",reviewer_model:"gpt-5.6-terra",reviewer_effort:"high",max_parallel:$parallel}}' >.hwahap/summary.json
{
  printf '# hwahap 보고서: %s (revision %s)\n## 결론\n%s/%s unit 통과. 통합 검사와 최종 검토 통과. 인도 대기.\n## 근거\n' "$goal_id" "$revision" "$passed" "$units_total"
  printf '| unit | attempt | cached | test | verdict | patch | tokens |\n|---|---:|---|---|---|---|---:|\n'; while IFS= read -r unit; do printf '| %s | %s | %s | %s | %s | out/%s.patch | %s |\n' "$unit" "$(<".hwahap/out/$unit.attempt" 2>/dev/null || printf 0)" "$([ -f ".hwahap/out/$unit.cached" ] && printf yes || printf no)" "$(tail -n 1 ".hwahap/out/$unit.test.txt" 2>/dev/null)" "$(head -n 1 ".hwahap/out/review/$unit.md" 2>/dev/null)" "$unit" "$(jq '.input_tokens+.output_tokens' ".hwahap/out/$unit.usage.json" 2>/dev/null || printf 0)"; done < <(jq -r '.units[] | select(.probe|not) | .id' "$goal")
  printf '## 확인 과정\nGoal, 답변 원장, hash chain, unit 범위, unit test/review, 통합 test/review, human turn을 확인했다.\n## 한계\nReviewer와 fact worker token은 비 JSONL 템플릿이라 측정하지 못했다. diary의 Deviations와 Open questions는 별도 확인 대상이다.\n## 비용\nworker tokens=%s, cache_hit_ratio=%s, cost_usd=%s, seconds=%s. 오케스트레이터 token은 측정 불가.\n' "$tokens" "$cache" "$cost" "$seconds"
} >.hwahap/report.md
"$skill/hooks/lib/deliver.sh"
run_dir="${CODEX_HOME:-$HOME/.codex}/hwahap/$repo_id/runs/$goal_id"; mkdir -p "$run_dir"; cp "$goal" .hwahap/summary.json .hwahap/report.md "$run_dir/"
