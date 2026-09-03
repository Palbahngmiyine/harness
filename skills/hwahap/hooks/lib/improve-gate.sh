#!/bin/bash
# Evaluate the U9a improve signal and six start conditions without starting a runner.
set -euo pipefail
repo_id=${1:?repo id is required}
summary=.hwahap/summary.json
hwahap_home=${CODEX_HOME:-$HOME/.codex}
runs=$hwahap_home/hwahap/$repo_id/runs
config=$hwahap_home/hwahap/config.json
state=$hwahap_home/hwahap/$repo_id/improve.state.json
goal_id=$(jq -r '.goal_id' "$summary")
history=()
for file in "$runs"/*/summary.json; do
  [ -f "$file" ] || continue
  if [ "$(jq -r '.goal_id' "$file")" = "$goal_id" ]; then continue; fi
  history+=("$file")
done
count=${#history[@]}
costs='[]'
if [ "$count" -gt 0 ]; then costs=$(jq -s '[.[].cost_per_passed_unit] | sort' "${history[@]}"); fi
median=$(printf '%s' "$costs" | jq 'if length==0 then null elif length%2==1 then .[length/2|floor] else (.[length/2-1]+.[length/2])/2 end')
signal=none
if [ "$median" != null ]; then
  if jq -e --argjson median "$median" '.cost_per_passed_unit > $median' "$summary" >/dev/null; then signal=cost_above_median; fi
fi
if [ "$signal" = none ]; then
  if jq -e '.first_try_pass < .units_passed' "$summary" >/dev/null; then signal=retry_seen; fi
fi
if [ "$signal" = none ]; then
  if jq -e '.cache_hit_ratio < 0.5' "$summary" >/dev/null; then signal=cache_miss; fi
fi
finish() {
  reason=$1; tmp=$(mktemp .hwahap/summary.XXXXXX)
  jq --arg signal "$signal" --arg reason "$reason" --argjson count "$count" '.improve={signal:$signal,started:false,reason:$reason,benchmark_count:$count}' "$summary" >"$tmp"
  mv "$tmp" "$summary"
  printf 'improve started=false signal=%s reason=%s.\n' "$signal" "$reason" >>.hwahap/report.md
  exit 0
}
if ! jq -e '.improve.auto==true' "$config" >/dev/null 2>&1; then finish 'auto disabled'; fi
if ! jq -e '.improve.budget_tokens != null' "$config" >/dev/null 2>&1; then finish 'budget_tokens missing'; fi
harness=$(jq -r '.harness_repo // empty' "$config")
if [ -z "$harness" ]; then finish 'harness_repo is not a git repository'; fi
if ! git -C "$harness" rev-parse --is-inside-work-tree >/dev/null 2>&1; then finish 'harness_repo is not a git repository'; fi
if [ "$signal" = none ]; then finish 'no improve signal'; fi
if [ -f "$state" ]; then
  last=$(jq -r '.last_auto // empty' "$state")
  if [ -n "$last" ]; then
    elapsed=$(jq -nr --arg last "$last" --arg current "${HWAHAP_NOW:-}" 'def epoch: capture("^(?<stamp>[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2})(?<zone>Z|(?<sign>[+-])(?<hours>[0-9]{2}):?(?<minutes>[0-9]{2}))$") | (.stamp|strptime("%Y-%m-%dT%H:%M:%S")|mktime) as $base | if .zone=="Z" then $base else $base-((((.hours|tonumber)*60)+(.minutes|tonumber))*60*(if .sign=="+" then 1 else -1 end)) end; ($last|epoch) as $start | (if $current=="" then now else ($current|epoch) end) - $start | floor')
    if [ "$elapsed" -lt 604800 ]; then finish 'last auto improve is within 7 days'; fi
  fi
fi
if [ "$count" -lt 5 ]; then finish 'fewer than 5 benchmarks'; fi
if [ "$(jq -r '.deliver' "$summary")" != "done" ]; then finish 'deliver is not done'; fi
finish 'runner pending (U9b)'
