#!/bin/bash
# Verify draft delivery, exclusions, failures, and idempotent completion.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-deliver.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
shim="$root/tests/fixtures/bin"

setup_repo() {
  name=$1 id=${2:-deliver-test}
  repo="$tmp/$name" remote="$tmp/$name.git"
  git init -q --bare "$remote"
  mkdir -p "$repo/src" "$repo/.hwahap/out"
  git -C "$repo" init -q -b main
  git -C "$repo" config user.email fixture@example.com
  git -C "$repo" config user.name Fixture
  printf 'base\n' >"$repo/src/check.sh"
  git -C "$repo" add src && git -C "$repo" commit -qm base
  git -C "$repo" remote add origin "$remote"
  git -C "$repo" push -q -u origin main
  git -C "$repo" worktree add -q --detach .hwahap/wt/integration HEAD
  printf 'delivered\n' >"$repo/.hwahap/wt/integration/src/check.sh"
  jq --arg id "$id" '.goal_id=$id | .goal.statement="deliver fixture"' \
    "$root/tests/fixtures/check/valid/goal.json" >"$repo/.hwahap/goal.json"
  jq -n '{deliver:"skipped:pending",pr_url:null}' >"$repo/.hwahap/summary.json"
  printf '# report\n\n인도 대기.\n' >"$repo/.hwahap/report.md"
  current_repo=$repo current_remote=$remote
}
run_deliver() {
  (cd "$current_repo" && PATH="$shim:$PATH" GH_MODE="${1:-success}" GH_LOG="$tmp/gh.log" "$root/hooks/lib/deliver.sh")
}

setup_repo unattended
(cd "$current_repo" && HWAHAP_UNATTENDED=1 "$root/hooks/lib/deliver.sh")
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'skipped:unattended'
test "$(git -C "$current_repo/.hwahap/wt/integration" branch --show-current)" = ''

setup_repo success
run_deliver success
test "$(head -n 1 "$current_repo/.hwahap/out/deliver.txt")" = done
test "$(sed -n '2p' "$current_repo/.hwahap/out/deliver.txt")" = 'https://example.test/new'
jq -e '.deliver=="done" and .pr_url=="https://example.test/new"' "$current_repo/.hwahap/summary.json" >/dev/null
git --git-dir="$current_remote" show-ref --verify --quiet refs/heads/hwahap/deliver-test
case "$(git -C "$current_repo/.hwahap/wt/integration" log -1 --format=%B)" in *'Hwahap-Goal: deliver-test'*'Hwahap-Revision: 1'*) ;; *) exit 1 ;; esac
commits=$(git -C "$current_repo/.hwahap/wt/integration" rev-list --count HEAD)
: >"$tmp/gh.log"; run_deliver create_fail
test ! -s "$tmp/gh.log"
test "$(git -C "$current_repo/.hwahap/wt/integration" rev-list --count HEAD)" -eq "$commits"

setup_repo remote_exists
git -C "$current_repo" push -q origin HEAD:refs/heads/hwahap/deliver-test
run_deliver success
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'skipped:exists'
test "$(git -C "$current_repo/.hwahap/wt/integration" branch --show-current)" = ''

setup_repo pr_exists
run_deliver pr_exists
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'skipped:exists'
test "$(git -C "$current_repo/.hwahap/wt/integration" branch --show-current)" = ''

setup_repo push_reject
printf '#!/bin/sh\nexit 1\n' >"$current_remote/hooks/pre-receive"
chmod +x "$current_remote/hooks/pre-receive"
run_deliver success
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'failed:push'
test "$(git -C "$current_repo/.hwahap/wt/integration" branch --show-current)" = 'hwahap/deliver-test'

setup_repo gh_failure
run_deliver create_fail
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'failed:gh pr create'
git --git-dir="$current_remote" show-ref --verify --quiet refs/heads/hwahap/deliver-test

setup_repo protected main
: >"$tmp/gh.log"; run_deliver success
test "$(<"$current_repo/.hwahap/out/deliver.txt")" = 'failed:protected branch'
test ! -s "$tmp/gh.log"
test "$(git -C "$current_repo/.hwahap/wt/integration" branch --show-current)" = ''
printf 'deliver success duplicate failure unattended idempotent protected\n'
