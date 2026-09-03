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
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print "sha256:" $1}'; else shasum -a 256 | awk '{print "sha256:" $1}'; fi; } # MUTATION-IGNORE equivalent digest providers
goal_hash=$(jq -S -c 'del(.review,.confirm)' "$goal" | sha)
[ "$(jq -r '.review.cold.goal_sha256 // empty' "$goal")" = "$goal_hash" ] || fail 'cold review is stale'
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
  [ "$stored" = "$actual" ] || fail 'answer hash is invalid'; prev=$stored; done <.hwahap/answers.jsonl
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
metrics=$("$skill/hooks/lib/usage.sh" metrics); worker_receipts=$(printf '%s' "$metrics" | jq '.roles.worker.receipts')
worker_tokens=$(printf '%s' "$metrics" | jq '.roles.worker.tokens'); reviewer_tokens=$(printf '%s' "$metrics" | jq '.roles.reviewer.tokens'); fact_tokens=$(printf '%s' "$metrics" | jq '.roles.fact.tokens')
tokens=$(printf '%s' "$metrics" | jq '.total.tokens'); cost=$(printf '%s' "$metrics" | jq '.total.cost'); seconds=$(printf '%s' "$metrics" | jq '.total.seconds'); cache=$(printf '%s' "$metrics" | jq 'if .total.input==0 then 0 else .total.cached/.total.input end')
goal_id=$(jq -r '.goal_id' "$goal"); revision=$(jq '.revision' "$goal"); base=$(jq -r '.base_branch' "$goal"); max_parallel=$(jq '.budget.max_parallel' "$goal"); base_sha=$(git rev-parse HEAD)
session_id=$(printf '%s' "$payload" | jq -r '.session_id // empty'); rollout=; orchestrator=0; orchestrator_note='unavailable'
if [ -n "$session_id" ]; then rollout=$(find "${CODEX_HOME:-$HOME/.codex}/sessions" -type f -name "*-$session_id.jsonl" -print -quit 2>/dev/null || true); fi
if [ -f "$rollout" ]; then orchestrator=$(jq -s '[.[] | select(.payload.type?=="token_count") | .payload.info.total_token_usage.total_tokens][-1] // 0' "$rollout"); orchestrator_note=$orchestrator; fi
jq -n --arg id "$goal_id" --arg base "$base" --arg base_sha "$base_sha" --arg repo "$repo" --argjson revision "$revision" --argjson total "$units_total" --argjson passed "$passed" --argjson cached "$cached" --argjson first "$first_try" --argjson workers "$worker_tokens" --argjson reviewers "$reviewer_tokens" --argjson facts "$fact_tokens" --argjson orchestrator "$orchestrator" --argjson cache "$cache" --argjson cost "$cost" --argjson seconds "$seconds" --argjson parallel "$max_parallel" --argjson receipts "$worker_receipts" --slurpfile g "$goal" --slurpfile s "$skill/data/settings.json" '{goal_id:$id,revision:$revision,base_branch:$base,base_sha:$base_sha,repo_path:$repo,units_total:$total,units_passed:$passed,units_cached:$cached,first_try_pass:$first,tokens:{workers:$workers,reviewers:$reviewers,facts:$facts,orchestrator:$orchestrator},units:[$g[0].units[]|select(.probe|not)|.id as $id|([$receipts[]|select(.unit==$id)]|{id:$id,cache_hit_ratio:(if (map(.input_tokens)|add//0)==0 then 0 else (map(.cached_input_tokens)|add)/(map(.input_tokens)|add) end),reasoning_ratio:(if (map(.output_tokens)|add//0)==0 then 0 else (map(.reasoning_output_tokens)|add)/(map(.output_tokens)|add) end)})],cache_hit_ratio:$cache,cost_usd:$cost,cost_per_passed_unit:(if $passed==0 then 0 else $cost/$passed end),seconds:$seconds,pr_url:null,deliver:"skipped:pending",improve:{signal:"none",started:false,reason:"not evaluated"},config:{worker_model:$s[0].worker.model,worker_effort:$s[0].worker.effort,reviewer_model:$s[0].reviewer.model,reviewer_effort:$s[0].reviewer.effort,max_parallel:$parallel}}' >.hwahap/summary.json
{
  printf '# hwahap 보고서: %s (revision %s)\n## 결론\n%s/%s unit 통과. 통합 검사와 최종 검토 통과. 인도 대기.\n## 근거\n' "$goal_id" "$revision" "$passed" "$units_total"
  printf '| unit | attempt | cached | test | verdict | patch | tokens | cache hit | cost | seconds |\n|---|---:|---|---|---|---|---:|---:|---:|---:|\n'
  while IFS= read -r unit; do
    attempt=0; [ ! -f ".hwahap/out/$unit.attempt" ] || attempt=$(<".hwahap/out/$unit.attempt")
    cached_unit=no; [ ! -f ".hwahap/out/$unit.cached" ] || cached_unit=yes
    unit_usage=$(jq -s '{tokens:([.[].input_tokens+.[].output_tokens]|add//0),input:([.[].input_tokens]|add//0),cached:([.[].cached_input_tokens]|add//0),cost:([.[].cost_usd]|add//0),seconds:([.[].seconds]|add//0)}' .hwahap/out/"$unit".usage.[0-9]*.json 2>/dev/null || printf '{"tokens":0,"input":0,"cached":0,"cost":0,"seconds":0}')
    printf '| %s | %s | %s | %s | %s | out/%s.patch | %s | %s | %s | %s |\n' "$unit" "$attempt" "$cached_unit" "$(tail -n 1 ".hwahap/out/$unit.test.txt" 2>/dev/null)" "$(head -n 1 ".hwahap/out/review/$unit.md" 2>/dev/null)" "$unit" "$(printf '%s' "$unit_usage"|jq '.tokens')" "$(printf '%s' "$unit_usage"|jq 'if .input==0 then 0 else .cached/.input end')" "$(printf '%s' "$unit_usage"|jq '.cost')" "$(printf '%s' "$unit_usage"|jq '.seconds')"; done < <(jq -r '.units[] | select(.probe|not) | .id' "$goal")
  printf '## 확인 과정\nGoal, 답변 원장, hash chain, unit 범위, unit test/review, 통합 test/review, human turn을 확인했다.\n## 한계\n'
  if [ -f .hwahap/diary.md ]; then awk '/^## (Deviations|Open questions)$/{show=1; sub(/^## /,"### "); print; next} /^## /{show=0} show' .hwahap/diary.md; else printf 'diary 없음.\n'; fi
  worker_cost=$(printf '%s' "$metrics" | jq '.roles.worker.cost'); reviewer_cost=$(printf '%s' "$metrics" | jq '.roles.reviewer.cost'); fact_cost=$(printf '%s' "$metrics" | jq '.roles.fact.cost')
  printf '## 비용\nworker tokens=%s cost_usd=%s; reviewer tokens=%s cost_usd=%s; fact tokens=%s cost_usd=%s; total tokens=%s cache_hit_ratio=%s cost_usd=%s seconds=%s cost_per_passed_unit=%s. 오케스트레이터 tokens=%s.\n' "$worker_tokens" "$worker_cost" "$reviewer_tokens" "$reviewer_cost" "$fact_tokens" "$fact_cost" "$tokens" "$cache" "$cost" "$seconds" "$(jq '.cost_per_passed_unit' .hwahap/summary.json)" "$orchestrator_note"
} >.hwahap/report.md
"$skill/hooks/lib/deliver.sh"
"$skill/hooks/lib/improve-gate.sh" "$repo_id"
run_dir="${CODEX_HOME:-$HOME/.codex}/hwahap/$repo_id/runs/$goal_id"; mkdir -p "$run_dir"; cp "$goal" .hwahap/summary.json .hwahap/report.md "$run_dir/"
