#!/bin/bash
# Verify every brief mode is deterministic and JSONL usage is priced correctly.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-brief.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
goal="$tmp/goal.json"
jq '.terms=[{"term":"검증","definition":"fixture","choice_id":"C1"}]
  | .specs += [{"id":"SP2","statement":"다른 unit","choice_ids":["C1"]}]
  | .acceptance += [{"id":"A2","spec_ids":["SP2"],"test":"./other.sh"}]
  | .units += [{"id":"U2","title":"다른 변경","paths":["src/other.sh"],"test":"./other.sh","acceptance_ids":["A2"],"depends_on":["U1"],"probe":false,"model":null,"effort":null}]' \
  "$root/tests/fixtures/check/valid/goal.json" >"$goal"

brief() {
  mode=$1 unit=$2 patch=$3 question=$4 output=$5
  jq -r --rawfile head "$root/data/brief.head.md" --arg mode "$mode" --arg unit "$unit" \
    --arg patch "$patch" --arg question "$question" -f "$root/jq/brief.jq" "$goal" >"$output"
}

brief worker U1 '' '' "$tmp/worker-a"
brief worker U1 '' '' "$tmp/worker-b"
cmp "$tmp/worker-a" "$tmp/worker-b"
case "$(<"$tmp/worker-a")" in *'SP1: 검증 계약'*'../../out/U1.test.txt'*) ;; *) exit 1 ;; esac
case "$(<"$tmp/worker-a")" in *'SP2: 다른 unit'*) exit 1 ;; *) ;; esac
case "$(<"$tmp/worker-a")" in *'commit, stage, stash, push'*) ;; *) exit 1 ;; esac

patch='diff --git a/src/check.sh b/src/check.sh'
brief review U1 "$patch" '' "$tmp/review"
test "$(rg -c -F "$patch" "$tmp/review")" -eq 1
case "$(<"$tmp/review")" in *'verdict: pass or verdict: fail'*) ;; *) exit 1 ;; esac
brief review integration "$patch" '' "$tmp/integration"
case "$(<"$tmp/integration")" in *'SP1: 검증 계약'*'SP2: 다른 unit'*) ;; *) exit 1 ;; esac
brief cold '' '' '' "$tmp/cold"
case "$(<"$tmp/cold")" in *required_user_choices*underspecified*unmapped_spec_ids*) ;; *) exit 1 ;; esac
brief fact '' '' '현재 정책은?' "$tmp/fact"
case "$(<"$tmp/fact")" in *'현재 정책은?'*UNKNOWN*) ;; *) exit 1 ;; esac

if jq -r --rawfile head "$root/data/brief.head.md" --arg mode bad --arg unit '' --arg patch '' --arg question '' -f "$root/jq/brief.jq" "$goal" >"$tmp/out" 2>"$tmp/err"; then
  exit 1
fi
case "$(<"$tmp/err")" in *'unknown brief mode'*) ;; *) exit 1 ;; esac

jq -s --slurpfile prices "$root/data/prices.json" --arg unit U1 --arg attempt 2 \
  --arg model gpt-5.6-luna --arg effort high --arg started start --arg ended end \
  --arg seconds 7 -f "$root/jq/usage.jq" "$root/tests/fixtures/usage/good/events.jsonl" >"$tmp/usage"
jq -e '.unit=="U1" and .attempt==2 and .input_tokens==1500 and
  .cached_input_tokens==600 and .output_tokens==300 and .reasoning_output_tokens==100 and
  .cache_hit_ratio==0.4 and .cost_usd==0.000552 and .seconds==7' "$tmp/usage" >/dev/null

printf '%s\n' '{"type":"turn.started"}' >"$tmp/missing.jsonl"
if jq -s --slurpfile prices "$root/data/prices.json" --arg unit U1 --arg attempt 1 \
  --arg model gpt-5.6-luna --arg effort high --arg started s --arg ended e --arg seconds 0 \
  -f "$root/jq/usage.jq" "$tmp/missing.jsonl" >"$tmp/out" 2>"$tmp/err"; then exit 1; fi
case "$(<"$tmp/err")" in *'turn.completed usage is missing'*) ;; *) exit 1 ;; esac
printf '%s\n' '{broken' >"$tmp/broken.jsonl"
if jq -s . "$tmp/broken.jsonl" >/dev/null 2>"$tmp/err"; then exit 1; fi
printf 'brief modes=4 usage=priced\n'
