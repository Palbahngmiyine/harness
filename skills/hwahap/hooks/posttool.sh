#!/bin/bash
# Reduce a completed codex exec worker call to one evidence summary line.
set -euo pipefail
[ "${HWAHAP_DISABLE_HOOKS:-}" = 1 ] && exit 0
payload=$(</dev/stdin)
printf '%s' "$payload" | jq -e . >/dev/null 2>&1 || exit 0
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
command=$(printf '%s' "$payload" | jq -r '.tool_input.command // empty')
[ -n "$cwd" ] || exit 0
cd "$cwd" || exit 0
[ -f .hwahap/goal.json ] || exit 0
case "$command" in codex\ exec\ *) ;; *) exit 0 ;; esac
workdir=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-C"){print $(i+1); exit}}')
skill=$(cd "$(dirname "$0")/.." && pwd)
output=$(printf '%s\n' "$command" | awk '{for(i=1;i<=NF;i++) if($i=="-o"){print $(i+1); exit}}')
sha() { if command -v sha256sum >/dev/null 2>&1; then sha256sum | awk '{print "sha256:" $1}'; else shasum -a 256 | awk '{print "sha256:" $1}'; fi; }
if [ "$workdir" = . ]; then
  case "$output" in
    .hwahap/facts/F*.md)
      fact=${output##*/}; fact=${fact%.md}
      jq -e --arg path "$output" 'any(.facts[]; .path==$path)' .hwahap/goal.json >/dev/null || { printf '%s fact fail\n' "$fact"; exit 0; }
      digest=$(sha <"$output")
      tmp=$(mktemp .hwahap/goal.XXXXXX)
      jq --arg path "$output" --arg digest "$digest" '(.facts[] | select(.path==$path) | .sha256)=$digest' .hwahap/goal.json >"$tmp"
      mv "$tmp" .hwahap/goal.json
      printf '%s fact pass\n' "$fact"
      ;;
    .hwahap/out/review/cold.md)
      first=$(head -n 1 "$output" 2>/dev/null || true)
      case "$first" in 'verdict: pass') printf 'cold review pass\n' ;; 'verdict: fail') printf 'cold review fail\n' ;; *) printf 'cold review fail verdict_invalid=1\n' ;; esac
      ;;
  esac
  exit 0
fi
case "$workdir" in .hwahap/wt/U*|.hwahap/wt/integration) ;; *) exit 0 ;; esac
unit=${workdir##*/}
case "$command" in *' -s read-only '*)
  attempt_file=".hwahap/out/review/$unit.attempt"
  attempts=0; [ ! -f "$attempt_file" ] || attempts=$(<"$attempt_file"); printf '%s\n' "$((attempts + 1))" >"$attempt_file"
  first=$(head -n 1 "$output" 2>/dev/null || true)
  case "$first" in 'verdict: pass') status=pass ;; 'verdict: fail') status=fail ;; *) status=fail; invalid=' verdict_invalid=1' ;; esac
  printf '%s review %s%s\n' "$unit" "$status" "${invalid:-}"
  exit 0
  ;; esac
case "$command" in *' -s workspace-write '*) ;; *) exit 0 ;; esac
set +e
status=$($skill/hooks/lib/capture.sh "$unit" 2>".hwahap/out/$unit.capture.err")
capture_rc=$?
set -e
[ "$capture_rc" -eq 0 ] || status=fail
usage_error=""
if [ "$capture_rc" -eq 2 ]; then usage_error=' usage_error=1'; fi
tokens=0 cost=0 cache=0
if [ -f ".hwahap/out/$unit.usage.json" ]; then
  tokens=$(jq '.input_tokens + .output_tokens' ".hwahap/out/$unit.usage.json")
  cost=$(jq -r '.cost_usd' ".hwahap/out/$unit.usage.json")
  cache=$(jq -r '.cache_hit_ratio' ".hwahap/out/$unit.usage.json")
fi
used=0
usage_files=(.hwahap/out/*.usage.[0-9]*.json)
if [ -e "${usage_files[0]}" ]; then used=$(jq -s '[.[] | .input_tokens + .output_tokens] | add // 0' "${usage_files[@]}"); fi
budget=$(jq '.budget.tokens' .hwahap/goal.json)
if [ "$budget" -eq 0 ]; then pct=100; else pct=$((used * 100 / budget)); fi
if [ "$pct" -ge 80 ]; then printf '%s%%\n' "$pct" >.hwahap/out/budget.warn; fi
network=""
if [ "$status" = fail ]; then
  if grep -Eqi 'network|connection|dns' ".hwahap/out/$unit.events.jsonl" ".hwahap/out/$unit.last.md" 2>/dev/null; then network=' network=1'; fi
fi
printf '%s %s tokens=%s cost=%s cache=%s budget=%s%%%s%s\n' "$unit" "$status" "$tokens" "$cost" "$cache" "$pct" "$network" "$usage_error"
