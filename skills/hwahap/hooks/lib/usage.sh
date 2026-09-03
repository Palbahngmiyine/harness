#!/bin/bash
# Record and aggregate worker, reviewer, and fact usage receipts.
set -euo pipefail
skill=$(cd "$(dirname "$0")/../.." && pwd)
mode=${1:?mode is required}
if [ "$mode" = validate ]; then
  command=${2:?command is required}; workdir=${3:?workdir is required}
  sandbox=${4:?sandbox is required}; output=${5:?output is required}; unit=${6:-}
  model=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-m"){print $(i+1); exit}}')
  effort=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-c" && $(i+1)~/^model_reasoning_effort=/){sub(/^model_reasoning_effort=/,"",$(i+1)); print $(i+1); exit}}')
  role=reviewer
  if [ "$workdir" = . ]; then case "$output" in .hwahap/facts/F*.md) role=fact ;; esac; fi
  if [ "$sandbox" = workspace-write ]; then role=worker; fi
  expected_model=$(jq -r --arg role "$role" '.[$role].model' "$skill/data/settings.json")
  expected_effort=$(jq -r --arg role "$role" '.[$role].effort' "$skill/data/settings.json")
  if [ "$role" = worker ]; then
    expected_model=$(jq -r --arg unit "$unit" --slurpfile s "$skill/data/settings.json" '.units[] | select(.id==$unit) | .model // $s[0].worker.model' .hwahap/goal.json)
    expected_effort=$(jq -r --arg unit "$unit" --slurpfile s "$skill/data/settings.json" '.units[] | select(.id==$unit) | .effort // $s[0].worker.effort' .hwahap/goal.json)
  fi
  if [ "$unit" = integration ]; then if [ "$(jq -r '.final_review' .hwahap/goal.json)" = sol ]; then expected_model=gpt-5.6-sol; fi; fi
  [ "$model" = "$expected_model" ] || exit 1
  [ "$effort" = "$expected_effort" ] || exit 1
  exit 0
fi
if [ "$mode" = record ]; then
  events=${2:?events path is required}; receipt=${3:?receipt path is required}
  unit=${4:?unit is required}; attempt=${5:?attempt is required}
  model=${6:?model is required}; effort=${7:?effort is required}
  now=${HWAHAP_NOW:-$(date '+%Y-%m-%dT%H:%M:%S%z')}
  if jq -s --slurpfile prices "$skill/data/prices.json" --arg unit "$unit" --arg attempt "$attempt" --arg model "$model" --arg effort "$effort" --arg started "$now" --arg ended "$now" --arg seconds "${HWAHAP_SECONDS:-0}" -f "$skill/jq/usage.jq" "$events" >"$receipt"; then exit 0; fi
  rm -f "$receipt"
  exit 2
fi
[ "$mode" = metrics ] || { printf 'hwahap usage: unknown mode %s\n' "$mode" >&2; exit 1; }
workers=(.hwahap/out/*.usage.[0-9]*.json)
reviewers=(.hwahap/out/review/*.usage.[0-9]*.json)
facts=(.hwahap/facts/*.usage.json)
worker='[]'; reviewer='[]'; fact='[]'
if [ -e "${workers[0]}" ]; then worker=$(jq -s . "${workers[@]}"); fi
if [ -e "${reviewers[0]}" ]; then reviewer=$(jq -s . "${reviewers[@]}"); fi
if [ -e "${facts[0]}" ]; then fact=$(jq -s . "${facts[@]}"); fi
jq -nc --argjson w "$worker" --argjson r "$reviewer" --argjson f "$fact" '
  def sum($a;$key): [$a[] | .[$key]] | add // 0;
  def role($a): {receipts:$a,tokens:(sum($a;"input_tokens")+sum($a;"output_tokens")),input:sum($a;"input_tokens"),cached:sum($a;"cached_input_tokens"),cost:sum($a;"cost_usd"),seconds:sum($a;"seconds")};
  {worker:role($w),reviewer:role($r),fact:role($f)} as $roles |
  ($w+$r+$f) as $all |
  {roles:$roles,receipts:$all,total:{tokens:(sum($all;"input_tokens")+sum($all;"output_tokens")),input:sum($all;"input_tokens"),cached:sum($all;"cached_input_tokens"),cost:sum($all;"cost_usd"),seconds:sum($all;"seconds")}}'
