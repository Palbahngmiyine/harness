#!/bin/bash
# Verify prompt.sh records only bound user answers and preserves its hash chain.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
hook="$root/hooks/prompt.sh"
fixture="$root/tests/fixtures/check/valid/goal.json"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-prompt.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
workspace="$tmp/repo"
mkdir -p "$workspace/.hwahap/out" "$tmp/codex"
git -C "$workspace" init -q
cp "$fixture" "$workspace/.hwahap/goal.json"
jq '.rounds += [{"n":2,"choice_ids":[],"new_choice_ids":[],"checkpoint":null},{"n":3,"choice_ids":[],"new_choice_ids":[],"checkpoint":null},{"n":4,"choice_ids":[],"new_choice_ids":[],"checkpoint":{"same_as_recommendation":["C1"],"answer":null}}]' "$workspace/.hwahap/goal.json" >"$tmp/goal"
mv "$tmp/goal" "$workspace/.hwahap/goal.json"

run_prompt() {
  text=$1
  jq -nc --arg cwd "$workspace" --arg prompt "$text" '{cwd:$cwd,prompt:$prompt}' |
    CODEX_HOME="$tmp/codex" HWAHAP_NOW=2026-09-02T00:00:00Z "$hook" 2>"$tmp/err"
}
lines() { test -f "$workspace/.hwahap/answers.jsonl" && wc -l <"$workspace/.hwahap/answers.jsonl" || printf '0\n'; }
digest() { shasum -a 256 | awk '{print "sha256:" $1}'; }

printf 'not-json' | CODEX_HOME="$tmp/codex" "$hook" 2>"$tmp/invalid"
case "$(<"$tmp/invalid")" in *'invalid hook payload'*) ;; *) exit 1 ;; esac
before=$(lines)
run_prompt 'ok'
test "$(lines)" -eq "$before"
run_prompt 'C1=ALT9'
test "$(lines)" -eq "$before"
case "$(<"$tmp/err")" in *'unknown alternative'*) ;; *) exit 1 ;; esac

# Exported into the hook subprocess below.
# shellcheck disable=SC2329
command() { if [ "${1:-}" = -v ]; then if [ "${2:-}" = sha256sum ]; then return 1; fi; fi; builtin command "$@"; }
export -f command
run_prompt 'C1=ALT1 S2=NA'
unset -f command
test "$(lines)" -eq 2
run_prompt 'C2=UNKNOWN'
test "$(lines)" -eq 3
run_prompt 'C1=OTHER: 사용자 지정 값'
test "$(lines)" -eq 4
test "$(jq -r '.choices[]|select(.id=="C1")|.alternatives[-1]|select(.origin=="user")|.value' "$workspace/.hwahap/goal.json")" = '사용자 지정 값'
choice=$(jq -S -c '.choices[]|select(.id=="C1")|{id,question,alternatives}' "$workspace/.hwahap/goal.json")
test "$(tail -n 1 "$workspace/.hwahap/answers.jsonl" | jq -r '.bound_sha256')" = "$(printf '%s' "$choice" | digest)"
run_prompt 'CP1=OK'
test "$(lines)" -eq 5
test "$(jq -r 'select(.key=="C1") | .text' "$workspace/.hwahap/answers.jsonl" | tail -n 1)" = 'C1=OTHER: 사용자 지정 값'
test "$(jq -r 'select(.key=="CP1") | .text' "$workspace/.hwahap/answers.jsonl")" = 'CP1=OK'

run_prompt 'CONFIRM ALIGN'
test "$(lines)" -eq 5
case "$(<"$tmp/err")" in *'align.md is missing'*) ;; *) exit 1 ;; esac
jq -r -f "$root/jq/render.jq" "$workspace/.hwahap/goal.json" >"$workspace/.hwahap/align.md"
run_prompt 'CONFIRM ALIGN'
test "$(lines)" -eq 6
test "$(tail -n 1 "$workspace/.hwahap/answers.jsonl" | jq -r '.key')" = CONFIRM
test "$(tail -n 1 "$workspace/.hwahap/answers.jsonl" | jq -r '.render_sha256')" = "$(digest <"$workspace/.hwahap/align.md")"

run_prompt 'skip U1'
test -f "$workspace/.hwahap/out/U1.skipped"
test "$(<"$workspace/.hwahap/human.turn")" = 2026-09-02T00:00:00Z
repo=$(git -C "$workspace" rev-parse --show-toplevel)
repo_id=$(printf '%s' "$repo" | digest | cut -c8-23)
cmp "$workspace/.hwahap/answers.jsonl" "$tmp/codex/hwahap/$repo_id/answers.jsonl"

prev=""
while IFS= read -r line; do
  if [ -z "$prev" ]; then
    test "$(printf '%s' "$line" | jq -r '.prev')" = null
  else
    test "$(printf '%s' "$line" | jq -r '.prev')" = "$prev"
  fi
  stored=$(printf '%s' "$line" | jq -r '.hash')
  actual=$(printf '%s' "$line" | jq -S -c 'del(.hash)' | digest)
  test "$stored" = "$actual"
  prev=$stored
done <"$workspace/.hwahap/answers.jsonl"

count=$(lines)
jq -nc --arg cwd "$workspace" --arg prompt 'C1=ALT1' '{cwd:$cwd,prompt:$prompt}' |
  CODEX_HOME="$tmp/codex" HWAHAP_UNATTENDED=1 "$hook"
test "$(lines)" -eq "$count"
printf 'prompt answers=%s chain=valid\n' "$count"
