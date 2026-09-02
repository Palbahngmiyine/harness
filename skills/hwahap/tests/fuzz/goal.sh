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
reject parent_path '.units[0].paths=["src/../x"]'
reject empty_alternatives '.choices[0].alternatives=[]'
reject duplicate_value '.choices[0].alternatives[1].value=.choices[0].alternatives[0].value'
reject non_ascii_path '.units[0].paths=["src/한글"]'
reject base_forbidden '.base_branch=""'
reject round_gap '.rounds[0].n=3'
reject checkpoint_missing '.rounds += [{n:2,choice_ids:[],new_choice_ids:[],checkpoint:null},{n:3,choice_ids:[],new_choice_ids:[],checkpoint:null},{n:4,choice_ids:[],new_choice_ids:[],checkpoint:null}]'
reject late_derived '.choices[0].derived_from=["C2"]'
reject missing_scenario '.choices[1].kind="decision"'
reject probe_dependency '.units += [{id:"P1",title:"probe",paths:["src/p"],test:"true",acceptance_ids:[],depends_on:[],probe:true,model:null,effort:null}] | .units[0].depends_on=["P1"]'
reject dependency_cycle '.units += [{id:"U2",title:"two",paths:["src/two"],test:"true",acceptance_ids:["A1"],depends_on:["U1"],probe:false,model:null,effort:null}] | .units[0].depends_on=["U2"]'
# shellcheck disable=SC2016
reject ten_thousand '.units=[range(0;10000) as $n | {id:("U"+($n|tostring)),title:"x",paths:["src/x"+($n|tostring)],test:"true",acceptance_ids:["A1"],depends_on:[],probe:false,model:null,effort:null}]'
printf 'goal fuzz mutations=16\n'
