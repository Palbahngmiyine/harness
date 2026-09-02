# Validate the complete hwahap/v2 goal contract without changing it.
def req($ok; $message): if $ok then . else error($message) end;
def unique_ids($items): ($items | length) == ($items | unique | length);
def stamped: type == "object" and (.text | type == "string") and (.ts | type == "string");
def digest: type == "string" and test("^sha256:[0-9a-f]{64}$");
def safe_path: type == "string" and length > 0 and (startswith("/") | not)
  and (test("(^|/)\\.\\.(/|$)") | not) and (startswith(".hwahap/") | not)
  and test("^[A-Za-z0-9._/-]+$");
def fact_path: type == "string" and test("^\\.hwahap/facts/F[0-9]+\\.md$");
def cyclic($g; $id; $seen):
  if ($seen | index($id)) != null then true
  else [$g.units[] | select(.id == $id) | .depends_on[]? |
    cyclic($g; .; $seen + [$id])] | any
  end;

. as $g
| ["S1","S2","S3","S4","S5","S6","S7","S8","S9","S10","S11","S12"] as $surfaces
| req(.schema == "hwahap/v2"; "schema must be hwahap/v2")
| req((.goal_id | type == "string") and (.goal_id | test("^[a-z0-9][a-z0-9._-]*$")); "unsafe goal_id")
| req((["main","master","develop"] | index($g.goal_id)) == null; "goal_id is a protected branch")
| req((.revision | type == "number") and .revision >= 1; "revision must be positive")
| req((.base_branch | type == "string") and (.base_branch | length > 0); "base_branch is required")
| req((.goal.statement | type == "string") and (.goal.statement | length > 0); "goal statement is required")
| req((.goal.success | length) > 0 and (.goal.non_goals | length) > 0; "goal outcomes are incomplete")
| req(unique_ids(.surfaces.applicable); "duplicate applicable surface")
| req(all($surfaces[]; . as $s | (($g.surfaces.applicable | index($s)) != null) or ($g.surfaces.not_applicable[$s] != null)); "surface is unclassified")
| req(all(.surfaces.not_applicable | keys[]; . as $s | $surfaces | index($s) != null); "unknown surface")
| req(all(.surfaces.not_applicable | to_entries[]; .key as $id |
    (.value.reason | length) > 0 and (.value.answer | stamped) and (.value.answer.hash | digest)
    and .value.answer.text == ($id + "=NA")); "invalid NA stamp")
| req(unique_ids([.facts[].id]); "duplicate fact id")
| req(all(.facts[]; (.path | fact_path) and (.sha256 | digest)); "invalid fact")
| req(unique_ids([.choices[].id]); "duplicate choice id")
| req(all(.choices[]; . as $c | (.alternatives | length) >= 2
    and unique_ids([.alternatives[].id]) and unique_ids([.alternatives[].value])
    and (["decision","scenario","term"] | index($c.kind) != null)
    and any(.alternatives[]; .id == $c.recommendation)
    and all(.evidence[]?; . as $f | any($g.facts[]; .id == $f))); "invalid choice")
| req(all(.choices[] | select(.answer != null); . as $c | (.answer | stamped)
    and (.answer.choice_sha256 | digest) and (.answer.text | startswith($c.id + "="))
    and (.answer.text | test("=(ALT[0-9]+|UNKNOWN|OTHER: .+)$"))); "invalid choice answer")
| req(all(.surfaces.applicable[]; . as $s |
    any($g.choices[]; .surface == $s and .kind == "decision" and .answer != null)
    and any($g.choices[]; .surface == $s and .kind == "scenario" and .answer != null)); "applicable surface is incomplete")
| req(all(.terms[]; . as $t | any($g.choices[]; .id == $t.choice_id and .kind == "term" and .answer != null)); "invalid term")
| req([.rounds[].n] == [range(1; (.rounds | length) + 1)]; "round numbers must be contiguous")
| req(all(.rounds[]; if (.n % 4) == 0 then (.checkpoint.answer | stamped)
    and .checkpoint.answer.text == ("CP" + ((.n / 4) | tostring) + "=OK") else .checkpoint == null end); "invalid checkpoint")
| req((.rounds | length) > 0 and (.rounds[-1].new_choice_ids | length) == 0; "frontier is not empty")
| req(all(.choices[] | select(.answer != null); . as $c |
    ([$g.rounds[] | select(.choice_ids | index($c.id) != null)] | length) == 1); "answered choice round mismatch")
| req(all(.choices[]; . as $c | all(.derived_from[]?; . as $d |
    ([$g.rounds[] | select(.choice_ids | index($d) != null) | .n][0]) <
    ([$g.rounds[] | select(.choice_ids | index($c.id) != null) | .n][0]))); "derived choice order is invalid")
| req(unique_ids([.specs[].id]) and unique_ids([.acceptance[].id]) and unique_ids([.units[].id]); "duplicate contract id")
| req(all(.specs[]; all(.choice_ids[]; . as $c | any($g.choices[]; .id == $c and .answer != null))); "invalid spec choice")
| req(all(.specs[]; . as $s | any($g.acceptance[]; .spec_ids | index($s.id) != null)); "unmapped spec")
| req(all(.acceptance[]; . as $a | (.test | length) > 0
    and all(.spec_ids[]; . as $s | any($g.specs[]; .id == $s))
    and any($g.units[]; (.probe | not) and (.acceptance_ids | index($a.id) != null))); "unmapped acceptance")
| req((.units | length) > 0 and (.units | length) < 10000; "invalid unit count")
| req(all(.units[]; . as $u | (.test | length) > 0 and (.paths | length) > 0 and all(.paths[]; safe_path)
    and all(.acceptance_ids[]; . as $a | any($g.acceptance[]; .id == $a))
    and all(.depends_on[]?; . as $d | any($g.units[]; .id == $d and (.probe | not)))); "invalid unit")
| req(all(.units[]; cyclic($g; .id; []) | not); "unit dependency cycle")
| req(all(.open_items[] | select(.status == "open"); .choice_id as $c |
    any($g.choices[]; .id == $c and .answer.text == (.id + "=UNKNOWN"))); "invalid open item")
| req(if any(.open_items[]; .status == "open") then .confirm == null else true end; "open item cannot be confirmed")
| req((.review.cold | type == "object") and (.review.cold.ts | type == "string") and (.review.cold.goal_sha256 | digest)
    and ([.review.cold.required_user_choices,.review.cold.underspecified,.review.cold.unmapped_spec_ids] | all(type == "array" and length == 0)); "cold review is incomplete")
| req(if .confirm == null then true else (.confirm.goal_sha256 | digest)
    and (.confirm.render_sha256 | digest) and .confirm.revision == .revision end; "invalid confirmation")
| req((.budget.tokens | type == "number") and .budget.tokens >= 0 and (.budget.max_parallel | type == "number") and .budget.max_parallel >= 1; "invalid budget")
| req((.final_review == "terra" or .final_review == "sol") and (.full_suite | length) > 0; "invalid final review")
