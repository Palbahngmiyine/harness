#!/bin/bash
# Verify dependency baselines produce non-overlapping patches and ordered integration.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-integrate.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/src" "$repo/.hwahap/out/review"
git -C "$repo" init -q
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"
printf 'base\n' >"$repo/src/other.sh"
git -C "$repo" add src && git -C "$repo" commit -qm base
git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
git -C "$repo" worktree add -q --detach .hwahap/wt/U2 HEAD
jq '.units[0].test="grep -q unit1 src/check.sh" |
  .units += [{id:"U2",title:"dependent",paths:["src/other.sh"],test:"grep -q unit2 src/other.sh",acceptance_ids:[],depends_on:["U1"],probe:true,model:null,effort:null}] |
  .full_suite="grep -q unit1 src/check.sh && grep -q unit2 src/other.sh"' \
  "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"
printf 'unit1\n' >"$repo/.hwahap/wt/U1/src/check.sh"
git -C "$repo/.hwahap/wt/U1" diff HEAD >"$repo/.hwahap/out/U1.patch"
printf 'exit 0\n' >"$repo/.hwahap/out/U1.test.txt"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U1.md"
jq -r --rawfile head "$root/data/brief.head.md" --arg mode worker --arg unit U2 --arg patch '' --arg question '' \
  -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/U2.brief.md"
worker='codex exec -C .hwahap/wt/U2 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled --ephemeral --json -o .hwahap/out/U2.last.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$worker" '{cwd:$cwd,tool_input:{command:$command}}')
test -z "$(cd "$repo" && "$root/hooks/pretool.sh" <<<"$payload")"
test "$(<"$repo/.hwahap/wt/U2/src/check.sh")" = unit1
test -s "$repo/.hwahap/out/U2.base-tree"
printf 'unit2\n' >"$repo/.hwahap/wt/U2/src/other.sh"
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/out/U2.events.jsonl"
printf 'done\n' >"$repo/.hwahap/out/U2.last.md"
(cd "$repo" && HWAHAP_NOW=now "$root/hooks/lib/capture.sh" U2) >/dev/null
case "$(<"$repo/.hwahap/out/U2.patch")" in *'src/check.sh'*) exit 1 ;; *) ;; esac
jq '(.units[] | select(.id=="U2") | .probe)=false |
  .units += [{id:"U3",title:"excluded probe",paths:["src/probe.sh"],test:"false",acceptance_ids:[],depends_on:[],probe:true,model:null,effort:null}]' \
  "$repo/.hwahap/goal.json" >"$tmp/goal"
mv "$tmp/goal" "$repo/.hwahap/goal.json"
printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U2.md"
review='codex exec -C .hwahap/wt/U2 -s read-only --ignore-user-config -m gpt-5.6-terra -c model_reasoning_effort=high --ephemeral -o .hwahap/out/review/U2.md'
payload=$(jq -nc --arg cwd "$repo" --arg command "$review" '{cwd:$cwd,tool_input:{command:$command}}')
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'U2 review pass integration=pass'
before=$(shasum -a 256 "$repo/.hwahap/out/integration.test.txt")
test "$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")" = 'U2 review pass'
test "$(shasum -a 256 "$repo/.hwahap/out/integration.test.txt")" = "$before"
test "$(<"$repo/.hwahap/wt/integration/src/check.sh")" = unit1
test "$(<"$repo/.hwahap/wt/integration/src/other.sh")" = unit2
test "$(tail -n 1 "$repo/.hwahap/out/integration.test.txt")" = 'exit 0'
printf 'integrate dependency baseline order pass\n'
