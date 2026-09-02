#!/bin/bash
# Compare deterministic lifecycle artifacts at the supported parallel boundaries.
set -euo pipefail
root=$(cd "$(dirname "$0")" && pwd)
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-boundary.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
HWAHAP_E2E_MAX_PARALLEL=1 HWAHAP_E2E_RESULT="$tmp/one" bash "$root/e2e.sh" >/dev/null
HWAHAP_E2E_MAX_PARALLEL=4 HWAHAP_E2E_RESULT="$tmp/four" bash "$root/e2e.sh" >/dev/null
cmp "$tmp/one" "$tmp/four"
printf 'boundary max_parallel=1,4 artifacts=identical\n'
