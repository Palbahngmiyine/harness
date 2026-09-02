#!/bin/bash
# Commit the integration worktree and open one draft pull request.
set -euo pipefail
goal=.hwahap/goal.json
summary=.hwahap/summary.json
report=.hwahap/report.md
out=.hwahap/out/deliver.txt
[ -f "$goal" ] || { printf 'hwahap deliver: goal.json is missing\n' >&2; exit 1; }
finish() {
  state=$1 url=${2:-}
  printf '%s\n' "$state" >"$out"
  [ -z "$url" ] || printf '%s\n' "$url" >>"$out"
  tmp=$(mktemp .hwahap/summary.XXXXXX)
  jq --arg state "$state" --arg url "$url" '.deliver=$state | .pr_url=(if $url=="" then null else $url end)' "$summary" >"$tmp"
  mv "$tmp" "$summary"
  tmp=$(mktemp .hwahap/report.XXXXXX)
  awk -v result="${url:-$state}" '{gsub(/인도 대기\./,"인도: " result "."); print}' "$report" >"$tmp"
  mv "$tmp" "$report"
}
if [ -f "$out" ]; then
  if [ "$(head -n 1 "$out")" = done ]; then finish done "$(sed -n '2p' "$out")"; exit 0; fi
fi
if [ "${HWAHAP_UNATTENDED:-}" = 1 ]; then finish 'skipped:unattended'; exit 0; fi
goal_id=$(jq -r '.goal_id' "$goal"); base=$(jq -r '.base_branch' "$goal"); head="hwahap/$goal_id"
case "$goal_id" in main|master|develop|release/*) finish 'failed:protected branch'; exit 0 ;; esac
case "$head" in "$base"|main|master|develop|release/*) finish 'failed:protected branch'; exit 0 ;; esac
set +e
remote=$(git ls-remote --exit-code --heads origin "$head" 2>"$out.stderr"); remote_rc=$?
set -e
if [ "$remote_rc" -eq 0 ]; then finish 'skipped:exists'; exit 0; fi
if [ "$remote_rc" -ne 2 ]; then finish 'failed:git ls-remote'; exit 0; fi
set +e
open_pr=$(gh pr list --head "$head" --state open --json url --jq '.[0].url // empty' 2>"$out.stderr"); gh_rc=$?
set -e
if [ "$gh_rc" -ne 0 ]; then finish 'failed:gh pr list'; exit 0; fi
if [ -n "$open_pr" ]; then finish 'skipped:exists'; exit 0; fi
wt=.hwahap/wt/integration
current=$(git -C "$wt" branch --show-current)
if [ "$current" != "$head" ]; then
  if ! git -C "$wt" switch -c "$head" >>"$out.stderr" 2>&1; then finish 'failed:git switch'; exit 0; fi
fi
paths=()
while IFS= read -r path; do paths+=("$path"); done < <(jq -r '[.units[] | select(.probe|not) | .paths[]] | unique[]' "$goal")
if ! git -C "$wt" log -1 --format=%B | grep -Fq "Hwahap-Goal: $goal_id"; then
  if ! git -C "$wt" add -- "${paths[@]}"; then finish 'failed:git add'; exit 0; fi
  statement=$(jq -r '.goal.statement' "$goal"); revision=$(jq -r '.revision' "$goal")
  passed=$(jq -r '[.units[] | select(.probe|not) | .id] | join(", ")' "$goal")
  if ! git -C "$wt" commit -m "hwahap: $statement" -m "Passed units: $passed" -m "Hwahap-Goal: $goal_id" -m "Hwahap-Revision: $revision" >>"$out.stderr" 2>&1; then finish 'failed:git commit'; exit 0; fi
fi
if ! git -C "$wt" push -u origin "$head" >>"$out.stderr" 2>&1; then finish 'failed:push'; exit 0; fi
title="hwahap: $(jq -r '.goal.statement' "$goal")"
set +e
url=$(gh pr create --draft --base "$base" --head "$head" --title "$title" --body-file "$report" 2>>"$out.stderr"); gh_rc=$?
set -e
if [ "$gh_rc" -ne 0 ]; then finish 'failed:gh pr create'; exit 0; fi
finish done "$url"
