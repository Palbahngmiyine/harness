#!/bin/bash
# Fuzz answer spelling and require exact grammar before ledger writes.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-answer-fuzz.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/.hwahap/out"
git -C "$repo" init -q
cp "$root/tests/fixtures/check/valid/goal.json" "$repo/.hwahap/goal.json"
run() { jq -nc --arg cwd "$repo" --arg prompt "$1" '{cwd:$cwd,prompt:$prompt}' | CODEX_HOME="$tmp/codex" "$root/hooks/prompt.sh" 2>/dev/null; }
lines() { if [ -f "$repo/.hwahap/answers.jsonl" ]; then wc -l <"$repo/.hwahap/answers.jsonl"; else printf 0; fi; }
for invalid in 'C1 = ALT1' 'c1=ALT1' 'C1=ALT9' 'C1=OTHER:' 'S1=NAtext' 'CP1=ok' 'CONFIRM ALIGN now' 'C1=ALT1oops'; do
  before=$(lines); run "$invalid"; test "$(lines)" -eq "$before"
done
run 'C1=ALT1 C2=UNKNOWN S2=NA'
test "$(lines)" -eq 3
run 'C1=OTHER: exact user value'
test "$(tail -n 1 "$repo/.hwahap/answers.jsonl" | jq -r '.text')" = 'C1=OTHER: exact user value'
printf 'answer fuzz invalid=8 valid=4\n'
