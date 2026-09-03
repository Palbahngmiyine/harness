#!/bin/bash
# Exercise worker capture, retries, scope checks, decisions, and budget boundaries.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-capture.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
repo="$tmp/repo"
mkdir -p "$repo/src" "$repo/.hwahap/out"
git -C "$repo" init -q
git -C "$repo" config user.email fixture@example.com
git -C "$repo" config user.name Fixture
printf 'base\n' >"$repo/src/check.sh"
git -C "$repo" add src/check.sh
git -C "$repo" commit -qm base
git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
jq '.units[0].test="test -f src/check.sh" | .budget.tokens=3600' \
  "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"
cp "$root/tests/fixtures/usage/good/events.jsonl" "$repo/.hwahap/out/U1.events.jsonl"
printf 'brief\n' >"$repo/.hwahap/out/U1.brief.md"
printf 'done\n' >"$repo/.hwahap/out/U1.last.md"
printf 'changed\n' >>"$repo/.hwahap/wt/U1/src/check.sh"
payload='{"cwd":"'"$repo"'","tool_input":{"command":"codex exec -C .hwahap/wt/U1 -s workspace-write --json"}}'

# Exported into the hook subprocess below.
# shellcheck disable=SC2317,SC2329
command() { if [ "${1:-}" = -v ]; then if [ "${2:-}" = sha256sum ]; then return 1; fi; fi; builtin command "$@"; }
export -f command
summary=$(cd "$repo" && HWAHAP_NOW=now HWAHAP_SECONDS=3 "$root/hooks/posttool.sh" <<<"$payload")
unset -f command
case "$summary" in
  'U1 pass tokens=1800 cost=0.000552 cache=0.4 budget=50%') ;;
  *) printf 'unexpected summary: %s\n' "$summary"; cat "$repo/.hwahap/out/U1.capture.err"; exit 1 ;;
esac
test "$(<"$repo/.hwahap/out/U1.attempt")" -eq 1
test "$(tail -n 1 "$repo/.hwahap/out/U1.test.txt")" = 'exit 0'
test -s "$repo/.hwahap/out/U1.patch"
test -s "$repo/.hwahap/out/U1.brief.sha256"
test ! -e "$repo/.hwahap/out/budget.warn"

jq '.budget.tokens=4500' "$repo/.hwahap/goal.json" >"$tmp/goal" && mv "$tmp/goal" "$repo/.hwahap/goal.json"
summary=$(cd "$repo" && HWAHAP_NOW=now "$root/hooks/posttool.sh" <<<"$payload")
case "$summary" in *'budget=80%'*) ;; *) exit 1 ;; esac
test -f "$repo/.hwahap/out/budget.warn"
test "$(<"$repo/.hwahap/out/U1.attempt")" -eq 2
test -f "$repo/.hwahap/out/U1.usage.1.json"
test -f "$repo/.hwahap/out/U1.usage.2.json"

printf 'outside\n' >"$repo/.hwahap/wt/U1/outside.txt"
git -C "$repo/.hwahap/wt/U1" add -N outside.txt
summary=$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")
case "$summary" in 'U1 fail '* ) ;; *) exit 1 ;; esac
case "$(<"$repo/.hwahap/out/U1.test.txt")" in 'path outside unit scope: outside.txt'*'exit 1') ;; *) exit 1 ;; esac
printf 'network connection failed\n' >"$repo/.hwahap/out/U1.last.md"
summary=$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")
case "$summary" in *'fail '*'network=1'*) ;; *) exit 1 ;; esac

printf 'NEEDS_DECISION: choose behavior\n' >"$repo/.hwahap/out/U1.last.md"
summary=$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")
case "$summary" in 'U1 needs_decision '* ) ;; *) exit 1 ;; esac
test ! -e "$repo/.hwahap/out/U1.patch"
test "$(<"$repo/.hwahap/out/U1.needs_decision")" = 'NEEDS_DECISION: choose behavior'

printf '{broken\n' >"$repo/.hwahap/out/U1.events.jsonl"
summary=$(cd "$repo" && "$root/hooks/posttool.sh" <<<"$payload")
case "$summary" in *'fail '*'usage_error=1') ;; *) exit 1 ;; esac
test ! -e "$repo/.hwahap/out/U1.usage.json"
printf 'capture pass retry scope decision budget usage_error\n'
