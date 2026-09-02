#!/bin/bash
# Fuzz large and malformed goal shapes beyond the named contract fixtures.
set -euo pipefail
root=$(cd "$(dirname "$0")/../.." && pwd)
valid="$root/tests/fixtures/check/valid/goal.json" check="$root/jq/check.jq"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-goal-fuzz.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
reject() { jq "$2" "$valid" >"$tmp/$1.json"; if jq -e -f "$check" "$tmp/$1.json" >/dev/null 2>&1; then printf 'accepted mutation: %s\n' "$1" >&2; exit 1; fi; }
jq -e -f "$check" "$valid" >/dev/null
reject missing_goal 'del(.goal)'
reject wrong_type '.units="not-an-array"'
reject duplicate_id '.units += [.units[0]]'
reject absolute_path '.units[0].paths=["/tmp/x"]'
reject non_ascii_path '.units[0].paths=["src/한글"]'
reject round_gap '.rounds[0].n=3'
reject late_derived '.choices[0].derived_from=["C2"]'
# shellcheck disable=SC2016
reject ten_thousand '.units=[range(0;10000) as $n | {id:("U"+($n|tostring)),title:"x",paths:["src/x"+($n|tostring)],test:"true",acceptance_ids:["A1"],depends_on:[],probe:false,model:null,effort:null}]'
printf 'goal fuzz mutations=8\n'
