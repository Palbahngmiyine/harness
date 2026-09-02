#!/bin/bash
# Fix integration behavior for empty, binary, CRLF, and one-megabyte patches.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-patch-fuzz.XXXXXX")
trap 'rm -rf "$tmp"' EXIT

run_case() {
  name=$1 path=$2
  repo="$tmp/$name"
  mkdir -p "$repo/$(dirname "$path")" "$repo/.hwahap/out/review"
  git -C "$repo" init -q
  git -C "$repo" config user.email fixture@example.com
  git -C "$repo" config user.name Fixture
  case "$name" in
    binary) printf '\0base\0' >"$repo/$path" ;;
    crlf) printf 'base\r\n' >"$repo/$path" ;;
    large) dd if=/dev/zero bs=1024 count=1024 2>/dev/null | tr '\0' a >"$repo/$path" ;;
    empty) printf 'base\n' >"$repo/$path" ;;
  esac
  git -C "$repo" add "$path"; git -C "$repo" commit -qm base
  git -C "$repo" worktree add -q --detach .hwahap/wt/U1 HEAD
  case "$name" in
    binary) printf '\0changed\0' >"$repo/.hwahap/wt/U1/$path" ;;
    crlf) printf 'changed\r\n' >"$repo/.hwahap/wt/U1/$path" ;;
    large) dd if=/dev/zero bs=1024 count=1024 2>/dev/null | tr '\0' b >"$repo/.hwahap/wt/U1/$path" ;;
    empty) ;;
  esac
  git -C "$repo/.hwahap/wt/U1" diff --binary HEAD >"$repo/.hwahap/out/U1.patch"
  jq --arg path "$path" '.units[0].paths=[$path] | .units[0].test="true" | .full_suite="true"' \
    "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"
  printf 'exit 0\n' >"$repo/.hwahap/out/U1.test.txt"
  printf 'verdict: pass\n' >"$repo/.hwahap/out/review/U1.md"
  (cd "$repo" && "$root/hooks/lib/integrate.sh")
  test "$(tail -n 1 "$repo/.hwahap/out/integration.test.txt")" = 'exit 0'
}
run_case empty src/empty.txt
run_case binary src/blob.bin
run_case crlf src/crlf.txt
run_case large src/large.txt
printf 'patch fuzz empty binary crlf megabyte\n'
