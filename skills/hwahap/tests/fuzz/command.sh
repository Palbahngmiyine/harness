#!/bin/bash
# Fuzz fixed command flags, ordering, worktree paths, and cache bypass.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-command-fuzz.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/src" "$repo/.hwahap/out/review"
git -C "$repo" init -q
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"; git -C "$repo" add src; git -C "$repo" commit -qm base
git -C "$repo" worktree add -q --detach .hwahap/wt/P1 HEAD
jq '.units[0].id="P1" | .units[0].probe=true' "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"
jq -r --rawfile head "$root/data/brief.head.md" --arg mode worker --arg unit P1 --arg patch '' --arg question '' -f "$root/jq/brief.jq" "$repo/.hwahap/goal.json" >"$repo/.hwahap/out/P1.brief.md"
base='codex exec -C .hwahap/wt/P1 -s workspace-write --ignore-user-config -m gpt-5.6-luna -c model_reasoning_effort=high -c model_verbosity=low -c model_reasoning_summary=none -c web_search=disabled -c tool_output_token_limit=4000 --ephemeral --json -o .hwahap/out/P1.last.md'
run() { jq -nc --arg cwd "$repo" --arg command "$1" '{cwd:$cwd,tool_input:{command:$command}}' | "$root/hooks/pretool.sh" 2>/dev/null; }
deny() { run "$1" | jq -e '.hookSpecificOutput.permissionDecision=="deny"' >/dev/null; }
test -z "$(run "$base")"
reordered='codex exec --ephemeral -m gpt-5.6-luna -C .hwahap/wt/P1 -c web_search=disabled -s workspace-write -o .hwahap/out/P1.last.md -c model_reasoning_summary=none --json --ignore-user-config -c tool_output_token_limit=4000 -c model_verbosity=low -c model_reasoning_effort=high'
test -z "$(run "$reordered")"
deny "${base/ --ignore-user-config/}"
deny "${base/.hwahap\/wt\/P1/.hwahap\/wt\/..\/src}"
deny "${base/workspace-write/danger-full-access}"
printf 'patch\n' >"$repo/.hwahap/out/P1.patch"; printf 'exit 0\n' >"$repo/.hwahap/out/P1.test.txt"; printf 'verdict: pass\n' >"$repo/.hwahap/out/review/P1.md"
shasum -a 256 "$repo/.hwahap/out/P1.brief.md" | awk '{print "sha256:" $1}' >"$repo/.hwahap/out/P1.brief.sha256"
deny "$base"
test -z "$(HWAHAP_NO_CACHE=1 run "$base")"
printf 'command fuzz reorder=allow invalid=3 cache_bypass=allow\n'
