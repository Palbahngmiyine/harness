#!/bin/bash
# Exercise every U9a signal, threshold, cadence, configuration, and delivery boundary.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-improve-gate.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
setup_case() {
  name=$1; case_root=$tmp/$name; repo=$case_root/repo; codex=$case_root/codex; harness=$case_root/harness
  mkdir -p "$repo/.hwahap" "$codex/hwahap/repo-id/runs" "$harness"
  git -C "$harness" init -q
  jq -n '{goal_id:"current",cost_per_passed_unit:5,first_try_pass:1,units_passed:1,cache_hit_ratio:0.5,deliver:"done",improve:{}}' >"$repo/.hwahap/summary.json"
  : >"$repo/.hwahap/report.md"
  jq -n --arg harness "$harness" '{harness_repo:$harness,improve:{auto:true,budget_tokens:1000}}' >"$codex/hwahap/config.json"
}
benchmarks() {
  i=0
  for cost in "$@"; do i=$((i+1)); dir=$codex/hwahap/repo-id/runs/past-$i; mkdir -p "$dir"; jq -n --arg id "past-$i" --argjson cost "$cost" '{goal_id:$id,cost_per_passed_unit:$cost}' >"$dir/summary.json"; done
}
evaluate() { (cd "$repo" && CODEX_HOME="$codex" HWAHAP_NOW=2026-09-10T00:00:00Z "$root/hooks/lib/improve-gate.sh" repo-id); }
expect() {
  jq -e --arg signal "$1" --arg reason "$2" --argjson count "$3" '.improve.signal==$signal and .improve.reason==$reason and .improve.started==false and .improve.benchmark_count==$count' "$repo/.hwahap/summary.json" >/dev/null
  grep -Fq "signal=$1 reason=$2" "$repo/.hwahap/report.md"
}
setup_case no_signal; benchmarks 10 11 12 13 14; evaluate; expect none 'no improve signal' 5
setup_case cost; benchmarks 1 2 3 4 5; mkdir -p "$codex/hwahap/repo-id/runs/current-copy"; jq -n '{goal_id:"current",cost_per_passed_unit:1000}' >"$codex/hwahap/repo-id/runs/current-copy/summary.json"; jq '.cost_per_passed_unit=4|.first_try_pass=0|.cache_hit_ratio=0.1' "$repo/.hwahap/summary.json" >"$case_root/s"; mv "$case_root/s" "$repo/.hwahap/summary.json"; evaluate; expect cost_above_median 'runner pending (U9b)' 5
setup_case retry; benchmarks 10 11 12 13 14; jq '.first_try_pass=0|.cache_hit_ratio=0.1' "$repo/.hwahap/summary.json" >"$case_root/s"; mv "$case_root/s" "$repo/.hwahap/summary.json"; evaluate; expect retry_seen 'runner pending (U9b)' 5
setup_case cache; benchmarks 10 11 12 13 14; jq '.cache_hit_ratio=0.49' "$repo/.hwahap/summary.json" >"$case_root/s"; mv "$case_root/s" "$repo/.hwahap/summary.json"; evaluate; expect cache_miss 'runner pending (U9b)' 5
setup_case benchmark4; benchmarks 1 2 3 4; jq '.cost_per_passed_unit=4' "$repo/.hwahap/summary.json" >"$case_root/s"; mv "$case_root/s" "$repo/.hwahap/summary.json"; evaluate; expect cost_above_median 'fewer than 5 benchmarks' 4
setup_case cadence_before; benchmarks 1 2 3 4 5; mkdir -p "$codex/hwahap/repo-id"; jq -n '{last_auto:"2026-09-03T00:00:01Z"}' >"$codex/hwahap/repo-id/improve.state.json"; evaluate; expect cost_above_median 'last auto improve is within 7 days' 5
setup_case cadence_exact; benchmarks 1 2 3 4 5; mkdir -p "$codex/hwahap/repo-id"; jq -n '{last_auto:"2026-09-03T00:00:00Z"}' >"$codex/hwahap/repo-id/improve.state.json"; evaluate; expect cost_above_median 'runner pending (U9b)' 5
setup_case auto; jq '.improve.auto=false' "$codex/hwahap/config.json" >"$case_root/c"; mv "$case_root/c" "$codex/hwahap/config.json"; evaluate; expect none 'auto disabled' 0
setup_case budget; jq 'del(.improve.budget_tokens)' "$codex/hwahap/config.json" >"$case_root/c"; mv "$case_root/c" "$codex/hwahap/config.json"; evaluate; expect none 'budget_tokens missing' 0
setup_case nongit; mkdir "$case_root/plain"; jq --arg path "$case_root/plain" '.harness_repo=$path' "$codex/hwahap/config.json" >"$case_root/c"; mv "$case_root/c" "$codex/hwahap/config.json"; evaluate; expect none 'harness_repo is not a git repository' 0
setup_case deliver; benchmarks 1 2 3 4 5; jq '.deliver="failed:test"' "$repo/.hwahap/summary.json" >"$case_root/s"; mv "$case_root/s" "$repo/.hwahap/summary.json"; evaluate; expect cost_above_median 'deliver is not done' 5
test ! -e "$root/hooks/lib/improve.sh"
printf 'improve gate signals=3 benchmarks=4,5 cadence=boundary configuration=guarded delivery=guarded\n'
