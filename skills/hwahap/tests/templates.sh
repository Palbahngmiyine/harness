#!/bin/bash
# Keep the three documented codex exec templates bound to settings.json.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
commands=$(grep '^codex exec ' "$root/SKILL.md")
test "$(printf '%s\n' "$commands" | wc -l | tr -d ' ')" -eq 3
worker=$(printf '%s\n' "$commands" | grep 'workspace-write')
reviewer=$(printf '%s\n' "$commands" | grep 'out/review')
fact=$(printf '%s\n' "$commands" | grep 'facts/F1')
value() { printf '%s\n' "$1" | awk -v key="$2" '{for(i=1;i<=NF;i++) if($i==key){print $(i+1); exit}}'; }
config() { printf '%s\n' "$1" | awk -v key="$2" '{for(i=1;i<=NF;i++) if($i=="-c" && $(i+1)~("^"key"=")){sub("^"key"=","",$(i+1)); print $(i+1); exit}}'; }
test "$(value "$worker" -m)" = "$(jq -r '.worker.model' "$root/data/settings.json")"
test "$(config "$worker" model_reasoning_effort)" = "$(jq -r '.worker.effort' "$root/data/settings.json")"
test "$(config "$worker" tool_output_token_limit)" -eq "$(jq '.worker.tool_output_token_limit' "$root/data/settings.json")"
test "$(value "$reviewer" -m)" = "$(jq -r '.reviewer.model' "$root/data/settings.json")"
test "$(config "$reviewer" model_reasoning_effort)" = "$(jq -r '.reviewer.effort' "$root/data/settings.json")"
test "$(value "$fact" -m)" = "$(jq -r '.fact.model' "$root/data/settings.json")"
test "$(config "$fact" model_reasoning_effort)" = "$(jq -r '.fact.effort' "$root/data/settings.json")"
printf 'templates match settings\n'
