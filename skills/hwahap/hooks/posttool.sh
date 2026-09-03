#!/bin/bash
# Reduce a completed codex exec call to one evidence summary line.
set -euo pipefail
[ "${HWAHAP_DISABLE_HOOKS:-}" = 1 ] && exit 0
payload=$(</dev/stdin); printf '%s' "$payload" | jq -e . >/dev/null 2>&1 || exit 0
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty'); [ -n "$cwd" ] || exit 0
command=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
cd "$cwd" || exit 0; [ -f .hwahap/goal.json ] || exit 0
case "$command" in codex\ exec\ *) ;; *) exit 0 ;; esac
skill=$(cd "$(dirname "$0")/.." && pwd)
workdir=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-C"){print $(i+1); exit}}')
output=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-o"){print $(i+1); exit}}')
model=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-m"){print $(i+1); exit}}')
effort=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-c"&&$(i+1)~/^model_reasoning_effort=/){sub(/^model_reasoning_effort=/,"",$(i+1));print $(i+1);exit}}')
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print "sha256:" $1}'; else shasum -a 256 | awk '{print "sha256:" $1}'; fi; } # MUTATION-IGNORE equivalent digest providers
next_attempt() { local path=$1 n=0; [ ! -f "$path" ] || n=$(<"$path"); n=$((n+1)); printf '%s\n' "$n" >"$path"; printf '%s' "$n"; }
record() { usage_error=; "$skill/hooks/lib/usage.sh" record "$1" "$2" "$3" "$4" "$model" "$effort" 2>/dev/null || usage_error=' usage_error=1'; }
if [ "$workdir" = . ]; then
  case "$output" in
    .hwahap/facts/F*.md)
      fact=${output##*/}; fact=${fact%.md}; record "${output%.md}.events.jsonl" "${output%.md}.usage.json" "$fact" 1
      jq -e --arg path "$output" 'any(.facts[]; .path==$path)' .hwahap/goal.json >/dev/null || { printf '%s fact fail%s\n' "$fact" "$usage_error"; exit 0; }
      [ -f "$output" ] || { printf '%s fact fail%s\n' "$fact" "$usage_error"; exit 0; }
      digest=$(sha <"$output"); tmp=$(mktemp .hwahap/goal.XXXXXX)
      jq --arg path "$output" --arg digest "$digest" '(.facts[] | select(.path==$path) | .sha256)=$digest' .hwahap/goal.json >"$tmp"; mv "$tmp" .hwahap/goal.json
      printf '%s fact pass%s\n' "$fact" "$usage_error" ;;
    .hwahap/out/review/cold.md)
      attempt=$(next_attempt .hwahap/out/review/cold.attempt); record "${output%.md}.events.jsonl" "${output%.md}.usage.$attempt.json" cold "$attempt"
      first=$(head -n 1 "$output" 2>/dev/null || true)
      case "$first" in
        'verdict: pass') digest=$(jq -S -c 'del(.review,.confirm)' .hwahap/goal.json | sha); tmp=$(mktemp .hwahap/goal.XXXXXX); jq --arg digest "$digest" --arg ts "${HWAHAP_NOW:-$(date '+%Y-%m-%dT%H:%M:%S%z')}" '.review.cold={ts:$ts,goal_sha256:$digest,required_user_choices:[],underspecified:[],unmapped_spec_ids:[]}' .hwahap/goal.json >"$tmp"; mv "$tmp" .hwahap/goal.json; printf 'cold review pass%s\n' "$usage_error" ;;
        'verdict: fail') printf 'cold review fail%s\n' "$usage_error" ;;
        *) printf 'cold review fail verdict_invalid=1%s\n' "$usage_error" ;; esac ;;
  esac
  exit 0
fi
case "$workdir" in .hwahap/wt/U*|.hwahap/wt/P*|.hwahap/wt/integration) ;; *) exit 0 ;; esac
unit=${workdir##*/}
case "$command" in *' -s read-only '*)
  attempt=$(next_attempt ".hwahap/out/review/$unit.attempt"); record "${output%.md}.events.jsonl" "${output%.md}.usage.$attempt.json" "$unit" "$attempt"
  first=$(head -n 1 "$output" 2>/dev/null || true)
  case "$first" in 'verdict: pass') status=pass ;; 'verdict: fail') status=fail ;; *) status=fail; invalid=' verdict_invalid=1' ;; esac
  integration=""
  if [ "$status" = pass ]; then
    if [ "$unit" != integration ]; then
      set +e; "$skill/hooks/lib/integrate.sh" >/dev/null; integrate_rc=$?; set -e
      case "$integrate_rc" in 0) integration=' integration=pass' ;; 3) ;; *) integration=' integration=fail' ;; esac
    fi
  fi
  printf '%s review %s%s%s%s\n' "$unit" "$status" "${invalid:-}" "$integration" "$usage_error"; exit 0 ;;
esac
case "$command" in *' -s workspace-write '*) ;; *) exit 0 ;; esac
set +e; status=$("$skill/hooks/lib/capture.sh" "$unit" 2>".hwahap/out/$unit.capture.err"); capture_rc=$?; set -e
[ "$capture_rc" -eq 0 ] || status=fail; usage_error=""; [ "$capture_rc" -ne 2 ] || usage_error=' usage_error=1'
tokens=0 cost=0 cache=0
if [ -f ".hwahap/out/$unit.usage.json" ]; then tokens=$(jq '.input_tokens + .output_tokens' ".hwahap/out/$unit.usage.json"); cost=$(jq -r '.cost_usd' ".hwahap/out/$unit.usage.json"); cache=$(jq -r '.cache_hit_ratio' ".hwahap/out/$unit.usage.json"); fi
used=$("$skill/hooks/lib/usage.sh" metrics | jq '.total.tokens'); budget=$(jq '.budget.tokens' .hwahap/goal.json)
if [ "$budget" -eq 0 ]; then pct=100; else pct=$((used * 100 / budget)); fi
if [ "$pct" -ge 80 ]; then printf '%s%%\n' "$pct" >.hwahap/out/budget.warn; fi
network=""
if [ "$status" = fail ]; then if grep -Eqi 'network|connection|dns' ".hwahap/out/$unit.events.jsonl" ".hwahap/out/$unit.last.md" 2>/dev/null; then network=' network=1'; fi; fi
printf '%s %s tokens=%s cost=%s cache=%s budget=%s%%%s%s\n' "$unit" "$status" "$tokens" "$cost" "$cache" "$pct" "$network" "$usage_error"
