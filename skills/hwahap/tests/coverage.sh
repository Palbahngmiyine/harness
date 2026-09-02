#!/bin/bash
# Collect merged kcov data for hook scripts and require complete executable-line coverage.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
command -v kcov >/dev/null || { printf 'kcov is required\n' >&2; exit 1; }
out=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-kcov.XXXXXX")
trap 'rm -rf "$out"' EXIT
tests=(brief-usage capture-posttool deliver e2e gate integrate pretool-posttool prompt)
inputs=()
for name in "${tests[@]}"; do
  kcov --include-path="$root/hooks" "$out/$name" "$root/tests/$name.sh" >/dev/null
  inputs+=("$out/$name")
done
kcov --merge "$out/merged" "${inputs[@]}" >/dev/null
json=$(find "$out/merged" -name coverage.json -print | head -n 1)
[ -n "$json" ] || { printf 'kcov coverage.json is missing\n' >&2; exit 1; }
percent=$(jq -r '.percent_covered' "$json")
[ "$percent" = 100 ] || { printf 'kcov executable-line coverage is %s, expected 100\n' "$percent" >&2; exit 1; }
printf 'kcov executable-line coverage=100\n'
