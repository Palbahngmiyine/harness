#!/bin/bash
# Verify kcov's decimal-string coverage field is enforced numerically.
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-coverage-contract.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
PATH="$root/fixtures/bin:$PATH" KCOV_PERCENT=100.00 "$root/coverage.sh" >/dev/null
if PATH="$root/fixtures/bin:$PATH" KCOV_PERCENT=99.99 "$root/coverage.sh" >"$tmp/out" 2>"$tmp/err"; then exit 1; fi
grep -Fq '99.99, expected 100' "$tmp/err"
printf 'coverage parser decimal=pass incomplete=reject\n'
