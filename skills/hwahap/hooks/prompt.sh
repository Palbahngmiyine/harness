#!/bin/bash
# Record only user-authored hwahap answers in a bound hash-chain ledger.
set -euo pipefail
[ "${HWAHAP_DISABLE_HOOKS:-}" = 1 ] && exit 0
payload=$(</dev/stdin)
if ! printf '%s' "$payload" | jq -e . >/dev/null 2>&1; then
  printf 'hwahap prompt: invalid hook payload\n' >&2
  exit 0
fi
cwd=$(printf '%s' "$payload" | jq -r '.cwd // empty')
prompt=$(printf '%s' "$payload" | jq -r '.prompt // empty')
[ -n "$cwd" ] || exit 0
cd "$cwd" || exit 0
goal=.hwahap/goal.json
[ -f "$goal" ] || exit 0
[ "${HWAHAP_UNATTENDED:-}" = 1 ] && exit 0
now=${HWAHAP_NOW:-$(date '+%Y-%m-%dT%H:%M:%S%z')}
mkdir -p .hwahap/out
printf '%s\n' "$now" >.hwahap/human.turn

sha() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | awk '{print "sha256:" $1}'
  else
    shasum -a 256 | awk '{print "sha256:" $1}'
  fi
}
append_answer() {
  text=$1 key=$2 bound=$3 render=${4:-}
  prev=""
  [ ! -s .hwahap/answers.jsonl ] || prev=$(tail -n 1 .hwahap/answers.jsonl | jq -r '.hash')
  line=$(jq -nc --arg ts "$now" --arg text "$text" --arg key "$key" --arg bound "$bound" --arg prev "$prev" --arg render "$render" '{ts:$ts,text:$text,key:$key,bound_sha256:$bound,prev:(if $prev=="" then null else $prev end)} + (if $render=="" then {} else {render_sha256:$render} end)')
  hash=$(printf '%s' "$line" | jq -S -c . | sha)
  line=$(printf '%s' "$line" | jq -c --arg hash "$hash" '. + {hash:$hash}')
  repo=$(git rev-parse --show-toplevel)
  repo_id=$(printf '%s' "$repo" | sha | cut -c8-23)
  outside="${CODEX_HOME:-$HOME/.codex}/hwahap/$repo_id/answers.jsonl"
  mkdir -p "$(dirname "$outside")"
  printf '%s\n' "$line" >>.hwahap/answers.jsonl
  printf '%s\n' "$line" >>"$outside"
}

if [[ "$prompt" =~ ^skip\ U[0-9]+$ ]]; then
  unit=${prompt#skip }
  : >".hwahap/out/$unit.skipped"
  exit 0
fi
if [ "$prompt" = "CONFIRM ALIGN" ]; then
  if [ ! -f .hwahap/align.md ]; then
    printf 'hwahap prompt: align.md is missing\n' >&2
    exit 0
  fi
  bound=$(jq -S -c 'del(.review,.confirm)' "$goal" | sha)
  render=$(sha <.hwahap/align.md)
  append_answer "$prompt" CONFIRM "$bound" "$render"
  exit 0
fi

printf '%s\n' "$prompt" | grep -Eo 'C[0-9]+=OTHER: .*$|C[0-9]+=(ALT[0-9]+|UNKNOWN)|S[0-9]+=NA|CP[0-9]+=OK' | while IFS= read -r token; do
  key=${token%%=*}
  case "$key" in
    CP*) round=$((${key#CP} * 4)); bound=$(jq -e -S -c --argjson n "$round" '.rounds[] | select(.n==$n) | .checkpoint.same_as_recommendation' "$goal") || { printf 'hwahap prompt: unknown checkpoint %s\n' "$key" >&2; continue; } ;;
    C*)
      alt=${token#*=}
      if [[ "$alt" =~ ^ALT[0-9]+$ ]]; then
        jq -e --arg id "$key" --arg alt "$alt" 'any(.choices[]; .id==$id and any(.alternatives[]; .id==$alt))' "$goal" >/dev/null || { printf 'hwahap prompt: unknown alternative %s\n' "$token" >&2; continue; }
      fi
      bound=$(jq -e -S -c --arg id "$key" '.choices[] | select(.id==$id) | {id,question,alternatives}' "$goal") || { printf 'hwahap prompt: unknown choice %s\n' "$key" >&2; continue; }
      ;;
    S*) bound=$(jq -e -S -c --arg id "$key" '.surfaces.not_applicable[$id] | select(. != null) | {id:$id,reason}' "$goal") || { printf 'hwahap prompt: unknown surface %s\n' "$key" >&2; continue; } ;;
    *) continue ;;
  esac
  append_answer "$token" "$key" "$(printf '%s' "$bound" | sha)"
done || true
