# Build byte-stable worker, reviewer, cold-review, and fact briefs.
def section($title; $body): "## " + $title + "\n" + $body;
def items($xs): $xs | map("- " + .) | join("\n");
def selected_unit($id): first(.units[] | select(.id == $id)) // error("unknown unit " + $id);
def agent_paths($paths): ["AGENTS.md"] + [$paths[] | split("/")[0:-1] | join("/") |
  select(length > 0) | . + "/AGENTS.md"] | unique;
def contract($g; $u):
  [$g.acceptance[] | select(.id as $id | $u.acceptance_ids | index($id) != null)] as $acceptance
  | [$g.specs[] | select(.id as $id | any($acceptance[]; .spec_ids | index($id) != null))] as $specs
  | [$g.terms[] | select(.choice_id as $id | any($specs[]; .choice_ids | index($id) != null))] as $terms
  | section("Unit"; "\($u.id) · \($u.title)") + "\n\n"
  + section("Paths"; items($u.paths)) + "\n\n"
  + section("Test"; $u.test) + "\n\n"
  + section("Specs"; ($specs | map("\(.id): \(.statement)") | items(.))) + "\n\n"
  + section("Acceptance"; ($acceptance | map("\(.id): \(.test)") | items(.))) + "\n\n"
  + section("Terms"; ($terms | map("\(.term): \(.definition)") | items(.))) + "\n\n"
  + section("AGENTS paths"; items(agent_paths($u.paths))) + "\n\n"
  + section("Dependency patches"; ($u.depends_on | map("../../out/\(.).patch") | items(.)));
def worker($g; $id):
  selected_unit($id) as $u
  | $head + "\n" + contract($g; $u) + "\n\n"
  + section("Failure evidence"; "../../out/\($id).test.txt (read only if present)") + "\n\n"
  + "Implement only this unit. Run no tests yourself; the hook runs the named test. "
  + "If a decision exceeds the reversible boundary, change nothing and make the first line NEEDS_DECISION: <question>.";
def review($g; $id):
  (if $id == "integration" then
    section("Integration contract"; ($g.specs | map("\(.id): \(.statement)") | items(.)))
   else contract($g; selected_unit($id)) end) + "\n\n"
  + section("Patch"; $patch) + "\n\n"
  + "First line must be verdict: pass or verdict: fail. Findings use - [paths|intent|test] description. "
  + "Inspect only this patch and the listed paths.";
def cold($g):
  section("Goal"; $g.goal.statement) + "\n\n"
  + section("Choices"; ($g.choices | map("\(.id): \(.question) => \(.answer.text // "UNANSWERED")") | items(.))) + "\n\n"
  + section("Specs"; ($g.specs | map("\(.id): \(.statement)") | items(.))) + "\n\n"
  + "First line must be verdict: pass or verdict: fail. Then list required_user_choices, underspecified, and unmapped_spec_ids.";
def fact:
  $head + "\n" + section("Fact question"; $question) + "\n\n"
  + "Read only. Return observed evidence in at most three lines. Use UNKNOWN when unverified.";
($mode // "worker") as $m
| if $m == "worker" then worker(.; $unit)
  elif $m == "review" then review(.; $unit)
  elif $m == "cold" then cold(.)
  elif $m == "fact" then fact
  else error("unknown brief mode " + $m)
  end
