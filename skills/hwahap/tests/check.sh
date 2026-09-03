#!/bin/bash
# Exercise check.jq with generated mutation fixtures and render determinism.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
valid="$root/tests/fixtures/check/valid/goal.json"
check="$root/jq/check.jq"
render="$root/jq/render.jq"
tmp=$(mktemp -d "${TMPDIR:-/tmp}/hwahap-check.XXXXXX")
trap 'rm -rf "$tmp"' EXIT
count=0

bad() {
  name=$1
  filter=$2
  expected=$3
  jq "$filter" "$valid" >"$tmp/$name.json"
  if jq -e -f "$check" "$tmp/$name.json" >"$tmp/out" 2>"$tmp/err"; then
    printf 'expected failure: %s\n' "$name" >&2
    exit 1
  fi
  error=$(<"$tmp/err")
  case "$error" in
    *"$expected"*) ;;
    *) printf 'wrong error for %s: %s\n' "$name" "$error" >&2; exit 1 ;;
  esac
  count=$((count + 1))
}

jq -e -f "$check" "$valid" >/dev/null
jq -r -f "$render" "$valid" >"$tmp/render-a"
jq -r -f "$render" "$valid" >"$tmp/render-b"
cmp "$tmp/render-a" "$tmp/render-b"
jq '.rounds += [range(2;9) | . as $n | {n:$n,choice_ids:[],new_choice_ids:[],checkpoint:(if $n==4 then {same_as_recommendation:[],answer:{text:"CP1=OK",ts:"now",hash:"sha256:0000000000000000000000000000000000000000000000000000000000000000"}} elif $n==8 then {same_as_recommendation:[],answer:{text:"CP2=OK",ts:"now",hash:"sha256:0000000000000000000000000000000000000000000000000000000000000000"}} else null end)}]' "$valid" >"$tmp/round-eight.json"
jq -e -f "$check" "$tmp/round-eight.json" >/dev/null
jq '(.rounds[]|select(.n==8).checkpoint)=null' "$tmp/round-eight.json" | if jq -e -f "$check" >/dev/null 2>&1; then exit 1; else :; fi

bad schema '.schema="bad"' 'schema must be'
bad goal_id '.goal_id="../bad"' 'unsafe goal_id'
bad protected '.goal_id="main"' 'protected branch'
bad revision '.revision=0' 'revision must be positive'
bad base '.base_branch=""' 'base_branch is required'
bad statement '.goal.statement=""' 'goal statement is required'
bad outcomes '.goal.success=[]' 'goal outcomes are incomplete'
bad missing_surface 'del(.surfaces.not_applicable.S12)' 'surface is unclassified'
bad duplicate_surface '.surfaces.applicable=["S1","S1"]' 'duplicate applicable surface'
bad unknown_surface '.surfaces.not_applicable.S13=.surfaces.not_applicable.S2' 'unknown surface'
bad na_reason '.surfaces.not_applicable.S2.reason=""' 'invalid NA stamp'
bad na_hash '.surfaces.not_applicable.S2.answer.hash="bad"' 'invalid NA stamp'
bad na_text '.surfaces.not_applicable.S2.answer.text="S2=NO"' 'invalid NA stamp'
bad duplicate_fact '.facts=[{"id":"F1","path":".hwahap/facts/F1.md","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"},{"id":"F1","path":".hwahap/facts/F1.md","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}]' 'duplicate fact id'
bad fact_path '.facts=[{"id":"F1","path":"../F1.md","sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}]' 'invalid fact'
bad duplicate_choice '.choices[1].id="C1"' 'duplicate choice id'
bad one_alternative '.choices[0].alternatives=[.choices[0].alternatives[0]]' 'invalid choice'
bad duplicate_value '.choices[0].alternatives[1].value="통과"' 'invalid choice'
bad recommendation '.choices[0].recommendation="ALT9"' 'invalid choice'
bad evidence '.choices[0].evidence=["F9"]' 'invalid choice'
bad answer_text '.choices[0].answer.text="ok"' 'invalid choice answer'
bad answer_digest '.choices[0].answer.choice_sha256="bad"' 'invalid choice answer'
bad missing_decision '.choices[0].kind="term"' 'applicable surface is incomplete'
bad missing_scenario '.choices[1].kind="decision"' 'applicable surface is incomplete'
bad term '.terms=[{"term":"x","definition":"x","choice_id":"C1"}]' 'invalid term'
bad round_number '.rounds[0].n=2' 'round numbers must be contiguous'
bad checkpoint '.rounds += [{"n":2,"choice_ids":[],"new_choice_ids":[],"checkpoint":null},{"n":3,"choice_ids":[],"new_choice_ids":[],"checkpoint":null},{"n":4,"choice_ids":[],"new_choice_ids":[],"checkpoint":null}]' 'invalid checkpoint'
bad frontier '.rounds[-1].new_choice_ids=["C3"]' 'frontier is not empty'
bad round_membership '.rounds += [{"n":2,"choice_ids":["C1"],"new_choice_ids":[],"checkpoint":null}]' 'round mismatch'
bad derived '.choices[1].derived_from=["C1"]' 'derived choice order'
bad duplicate_spec '.specs += [.specs[0]]' 'duplicate contract id'
bad spec_choice '.specs[0].choice_ids=["C9"]' 'invalid spec choice'
bad unmapped_spec '.specs += [{"id":"SP2","statement":"x","choice_ids":["C1"]}]' 'unmapped spec'
bad acceptance_test '.acceptance[0].test=""' 'unmapped acceptance'
bad acceptance_spec '.acceptance[0].spec_ids=["SP9"]' 'unmapped spec'
bad zero_units '.units=[]' 'unmapped acceptance'
bad unit_test '.units[0].test=""' 'invalid unit'
bad unit_path '.units[0].paths=["../bad"]' 'invalid unit'
bad unit_acceptance '.units[0].acceptance_ids=["A9"]' 'unmapped acceptance'
bad dependency '.units[0].depends_on=["U9"]' 'invalid unit'
bad probe_dependency '.units += [{"id":"P1","title":"probe","paths":["src/p"],"test":"true","acceptance_ids":[],"depends_on":[],"probe":true,"model":null,"effort":null}] | .units[0].depends_on=["P1"]' 'invalid unit'
bad cycle '.units += [{"id":"U2","title":"two","paths":["src/two"],"test":"true","acceptance_ids":["A1"],"depends_on":["U1"],"probe":false,"model":null,"effort":null}] | .units[0].depends_on=["U2"]' 'dependency cycle'
bad open_item '.open_items=[{"id":"O1","choice_id":"C1","kind":"prototype","unit_id":"U1","status":"open"}]' 'invalid open item'
bad confirmed_open '.choices[0].answer.text="C1=UNKNOWN" | .open_items=[{"id":"O1","choice_id":"C1","kind":"prototype","unit_id":"U1","status":"open"}] | .confirm={"text":"CONFIRM ALIGN","ts":"2026-09-02T00:00:00Z","revision":1,"goal_sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000","render_sha256":"sha256:0000000000000000000000000000000000000000000000000000000000000000"}' 'open item cannot be confirmed'
bad budget '.budget.tokens=-1' 'invalid budget'
bad parallel '.budget.max_parallel=0' 'invalid budget'
bad review '.final_review="ultra"' 'invalid final review'
bad full_suite '.full_suite=""' 'invalid final review'
bad cold_lists '.review.cold.underspecified=["missing"]' 'cold review is incomplete'
bad unknown_open '.choices[0].answer.text="C1=UNKNOWN"' 'UNKNOWN answer is not open'
bad other_origin '.choices[0].answer.text="C1=OTHER: custom"' 'OTHER answer is not an alternative'
bad unit_id '.units[0].id="P1"' 'invalid unit id'
bad surface_unknown '.surfaces.applicable += ["S99"]' 'invalid applicable surface'
bad surface_overlap '.surfaces.not_applicable.S1={reason:"duplicate",answer:{text:"S1=NA",ts:"now",hash:"sha256:0000000000000000000000000000000000000000000000000000000000000000"}}' 'invalid applicable surface'

test "$count" -ge 30
printf 'check fixtures=%s render=stable\n' "$count"
