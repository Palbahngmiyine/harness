#!/bin/bash
# Capture one worker's patch, scoped test, usage, and retry evidence.
set -euo pipefail
unit=${1:?unit is required}
skill=$(cd "$(dirname "$0")/../.." && pwd)
goal=.hwahap/goal.json
out=.hwahap/out/$unit
wt=.hwahap/wt/$unit
[ -f "$goal" ] || { printf 'hwahap capture: goal.json is missing\n' >&2; exit 1; }
[ -d "$wt" ] || { printf 'hwahap capture: worktree %s is missing\n' "$unit" >&2; exit 1; }
attempt=0
[ ! -f "$out.attempt" ] || attempt=$(<"$out.attempt")
attempt=$((attempt + 1))
printf '%s\n' "$attempt" >"$out.attempt"
rm -f "$out.cached"
first=""
[ ! -f "$out.last.md" ] || first=$(head -n 1 "$out.last.md")
if [[ "$first" == NEEDS_DECISION:* ]]; then
  printf '%s\n' "$first" >"$out.needs_decision"
  rm -f "$out.patch" "$out.test.txt"
  status=needs_decision
else
  base_index="$(pwd)/$out.base-index"
  diff_base() { if [ -f "$base_index" ]; then GIT_INDEX_FILE="$base_index" git -C "$wt" diff "$@"; else git -C "$wt" diff "$@" HEAD; fi; }
  diff_base --binary >"$out.patch"
  : >"$out.test.txt"
  while IFS= read -r changed; do
    allowed=$(jq -r --arg unit "$unit" --arg path "$changed" 'any(.units[] | select(.id==$unit) | .paths[]; . as $allowed | $path==$allowed or ($path | startswith($allowed + "/")))' "$goal")
    if [ "$allowed" != true ]; then
      printf 'path outside unit scope: %s\nexit 1\n' "$changed" >"$out.test.txt"
      status=fail
      break; fi; done < <(diff_base --name-only)
  if [ ! -s "$out.test.txt" ]; then
    test_command=$(jq -er --arg unit "$unit" '.units[] | select(.id==$unit) | .test' "$goal")
    set +e
    (cd "$wt" && /bin/bash -lc "$test_command") >"$out.test.txt" 2>&1
    rc=$?
    set -e
    printf 'exit %s\n' "$rc" >>"$out.test.txt"
    if [ "$rc" -eq 0 ]; then status=pass; else status=fail; fi
  fi
fi
model=$(jq -r --arg unit "$unit" --slurpfile s "$skill/data/settings.json" '.units[] | select(.id==$unit) | .model // $s[0].worker.model' "$goal")
effort=$(jq -r --arg unit "$unit" --slurpfile s "$skill/data/settings.json" '.units[] | select(.id==$unit) | .effort // $s[0].worker.effort' "$goal")
now=${HWAHAP_NOW:-$(date '+%Y-%m-%dT%H:%M:%S%z')}
receipt="$out.usage.$attempt.json"
if ! jq -s --slurpfile prices "$skill/data/prices.json" --arg unit "$unit" --arg attempt "$attempt" --arg model "$model" --arg effort "$effort" --arg started "$now" --arg ended "$now" --arg seconds "${HWAHAP_SECONDS:-0}" -f "$skill/jq/usage.jq" "$out.events.jsonl" >"$receipt"; then
  rm -f "$receipt"
  rm -f "$out.usage.json"
  printf 'usage_error\n'
  exit 2
fi
cp "$receipt" "$out.usage.json"
if command -v sha256sum >/dev/null 2>&1; then # MUTATION-IGNORE equivalent digest providers
  sha256sum "$out.brief.md" | awk '{print "sha256:" $1}' >"$out.brief.sha256"
else
  shasum -a 256 "$out.brief.md" | awk '{print "sha256:" $1}' >"$out.brief.sha256"
fi
printf '%s\n' "$status"
