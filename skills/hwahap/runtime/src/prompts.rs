//! The prompt sent to each role.
//!
//! Every prompt is a pure function of the plan and the run state, so the same situation produces
//! the same bytes. That is what makes an attempt reproducible and a rework diff meaningful: when a
//! second attempt differs, it differs because the findings differ, not because the brief drifted.
//!
//! Two rules run through all of them. Agents that write are told the exact paths they may touch and
//! the exact command that judges them, because the host resets anything outside that. Agents that
//! report are told the exact JSON their final message must be, because
//! [`crate::agentresult`] will reject anything else.

use crate::agentresult::{ReviewResult, WorkerResult};
use crate::plan::{Plan, Surface, Unit, SURFACES};
use crate::proposal::{DecisionsProposal, StructureProposal};

/// Preamble shared by every role: what Hwahap is and what the agent must not do.
const COMMON: &str = "\
You are one step of a Hwahap run. Hwahap froze a plan with the user and is now executing it \
without asking the user anything further.

Rules that apply to you no matter what you were asked to do:
- The frozen plan is the contract. Do not improve on it, extend it, or reinterpret it.
- If doing your job would require a product or technical decision the plan does not already \
contain, stop and say so. Do not choose on the user's behalf.
- Do not run `git commit`, `git push`, `git checkout`, or any other command that changes branch or \
history. Hwahap owns the repository.
- Your final message is read by a machine, not a person. Follow the result contract exactly.";

/// Asks Economy to establish one repository fact.
pub fn fact_finder(question: &str) -> String {
    format!(
        "{COMMON}

# Your job: establish one fact about this repository

Question: {question}

Read the repository and answer it. Cite every claim with a `path:line-range` you actually opened.
If the repository does not determine the answer, say exactly that instead of guessing — an
unfounded fact is worse than a missing one, because the plan will be built on it.

Answer in plain prose. Lead with the answer in one sentence, then the evidence."
    )
}

/// Asks Economy to read the plan cold and report whether it can be built without new decisions.
pub fn cold_consumer(plan_markdown: &str) -> String {
    format!(
        "{COMMON}

# Your job: read this plan cold and try to build from it

You have not seen the conversation that produced this plan. That is the point. Read it as the only
thing you have, pick any one unit, and write down what you would do.

Then report whether you could do that WITHOUT making a product or technical decision the plan does
not already contain. Anything you would have had to decide yourself is a hole in the plan.

Your final message must be exactly this JSON object and nothing else:
{contract}

Use `verdict: \"pass\"` only when you needed no new decision. Otherwise `verdict: \"fail\"` with one
finding per missing decision, each naming the unit and the exact question the plan leaves open.

# The plan

{plan_markdown}",
        contract = ReviewResult::CONTRACT
    )
}

/// Asks Deep for the next round of decisions.
///
/// `findings` carries what a review raised, so a finding becomes another question for the user
/// rather than something the planner quietly patches in prose.
pub fn decisions(plan: &Plan, findings: &[String]) -> String {
    let answered: Vec<String> = plan
        .decisions
        .iter()
        .filter(|d| d.is_answered().unwrap_or(false))
        .filter_map(|d| {
            d.resolved_value()
                .ok()
                .flatten()
                .map(|value| format!("{}: {} -> {}", d.id, d.question, value))
        })
        .collect();
    let open: Vec<String> = plan
        .decisions
        .iter()
        .filter(|d| !d.is_answered().unwrap_or(false))
        .map(|d| format!("{}: {}", d.id, d.question))
        .collect();
    let next_id = format!("C{}", plan.decisions.len() + 1);

    let review = if findings.is_empty() {
        String::new()
    } else {
        format!(
            "\n## A review raised these, and each one must become a decision\n\n{}\n\n\
             Do not close any of them by rewording the plan. Each is either a question for the \
             user, a fact to establish, or a change to the unit graph.\n",
            bullets(findings)
        )
    };

    format!(
        "{COMMON}

# Your job: put the next round of material decisions to the user

Goal: {goal}

Ask about preferences and trade-offs. Never ask about anything the repository already answers —
those are facts, and facts are established by reading, not by asking.
{review}
## The twelve decision surfaces

Check every one. A surface is a checklist item, not a stage. For each surface that applies, this
plan eventually needs at least one `decision` and at least one `scenario` — a \"what must happen
when …\" question. Propose a surface as `not_applicable` with a reason when it genuinely does not
apply; the user confirms that separately.

{surfaces}

## What is already settled

{answered}

## What is already asked and still unanswered

{open}

## Rules for each decision you propose

- Two or more alternatives that are genuinely different, not a rephrasing of each other.
- A recommendation in one of three modes: `recommended` with a choice, rationale, evidence (fact
  ids), trade-offs, impact and confidence; `no_recommendation` when there is no objective basis;
  `probe_required` when only an experiment can settle it.
- `evidence` may cite only facts that already exist in this plan.
- `depends_on` lists the decisions that must be answered before this one can be.
- Start numbering at {next_id}. Do not reuse an existing id.
- Propose only what can be asked now or soon. A hundred questions is not thoroughness.

Your final message must be exactly this JSON object and nothing else:
{contract}

## The facts you have

{facts}",
        goal = plan.goal.statement,
        surfaces = surface_list(plan),
        answered = bullets(&answered),
        open = bullets(&open),
        facts = fact_list(plan),
        contract = DecisionsProposal::CONTRACT,
    )
}

/// Asks Deep to turn answered decisions into a buildable unit graph.
pub fn structure(plan: &Plan) -> String {
    let answered: Vec<String> = plan
        .decisions
        .iter()
        .filter_map(|d| {
            d.resolved_value()
                .ok()
                .flatten()
                .map(|value| format!("{}: {} -> {}", d.id, d.question, value))
        })
        .collect();

    format!(
        "{COMMON}

# Your job: turn these settled decisions into a graph that can be built

Goal: {goal}

## The decisions

{answered}

## What you must produce

- **Requirements** (`R<n>`): one behaviour each, every one citing the decisions it comes from. Every
  decision above must be cited by at least one requirement — a decision the user made that no
  requirement uses has been dropped on the floor.
- **Acceptance** (`A<n>`): how a requirement is shown to hold, stated as something an observer sees.
- **Units** (`U<n>`): atomic implementation steps. Each declares the repository-relative path
  prefixes it may change — Hwahap discards anything written outside them — and the acceptance
  criteria it delivers. `depends_on` must be acyclic. Set `probe: true` only for a reversible
  experiment that settles a `probe_required` decision.
- **Tests** (`T<n>`): the exact command Hwahap will run, and the unit whose loop runs it. Every
  non-probe unit needs at least one. A test's acceptance ids must be a subset of its unit's.
- **full_suite**: the one command run after every unit is accepted.

Keep units small enough that one session can finish one. Order them so that a unit never needs
something a later unit builds.

Your final message must be exactly this JSON object and nothing else:
{contract}",
        goal = plan.goal.statement,
        answered = bullets(&answered),
        contract = StructureProposal::CONTRACT,
    )
}

/// Asks Critic to attack the plan.
pub fn plan_critic(plan_markdown: &str) -> String {
    format!(
        "{COMMON}

# Your job: attack this plan before it is frozen

Once the user confirms it, this plan is executed autonomously. Every hole becomes either a wrong
implementation or an interruption. Find the holes now.

Work through all of these, and report a finding for each real problem:
- Requirements: is anything the goal implies missing, or stated so loosely that two readers would
  build different things?
- Contracts: are the commands, APIs, files, schemas, types, paths and formats pinned exactly?
- Failure: for every operation that can fail, does the plan say what happens — including partial
  failure, retry, and rollback?
- Security: authorization, secrets, destructive side effects, and anything that crosses a trust
  boundary.
- Compatibility: existing users, existing data, downgrade, migration.
- Testability: does every acceptance criterion name something a command can actually observe? Would
  the listed test really fail if the requirement were violated?
- Recommendations: is any recommendation unsupported by its evidence, or contradicted by a fact?
- Traceability: any decision that no requirement uses, any unit that no test covers.

Do not report style, wording, or preferences. Report only what would produce wrong or blocked work.

Your final message must be exactly this JSON object and nothing else:
{contract}

# The plan

{plan_markdown}",
        contract = ReviewResult::CONTRACT
    )
}

/// Asks Economy to implement one unit.
pub fn implementer(plan: &Plan, unit: &Unit, findings: &[String]) -> String {
    let attempt = if findings.is_empty() {
        String::new()
    } else {
        format!(
            "\n# A previous attempt was rejected\n\nFix exactly these findings. Do not \
             re-architect anything else.\n\n{}\n",
            bullets(findings)
        )
    };

    format!(
        "{COMMON}

# Your job: implement {id} — {title}
{attempt}
## What must become true

{acceptance}

## Where you may write

You may create or change files only under these paths:

{paths}

Hwahap compares the working tree against this list and discards the whole attempt if anything else
changed. That includes files you created as scratch space.

## How you will be judged

Hwahap runs these commands itself and reads their exit status. Your own account of whether they
passed is not evidence, so run them yourself before you finish:

{tests}

Write or update the tests as part of this unit. A unit whose tests do not fail when the behaviour is
removed has not been implemented.

## The frozen decisions you must honour

{decisions}

## Result contract

Your final message must be exactly this JSON object and nothing else:
{contract}

Use `\"plan_conflict\"` — and change no files at all — if building this unit would require a decision
the plan above does not contain. Put the exact conflicting plan detail in `conflict`.",
        id = unit.id,
        title = unit.title,
        acceptance = acceptance_for(plan, unit),
        paths = bullets(&unit.paths),
        tests = bullets(
            &plan
                .tests_for(&unit.id)
                .iter()
                .map(|t| format!("`{}`", t.command))
                .collect::<Vec<_>>()
        ),
        decisions = decisions_for(plan, unit),
        contract = WorkerResult::CONTRACT,
    )
}

/// Asks Critic to review one unit's diff, read-only.
pub fn unit_reviewer(plan: &Plan, unit: &Unit, diff: &str) -> String {
    format!(
        "{COMMON}

# Your job: review the diff for {id} — {title}

You may read anything. You may not change anything: Hwahap verifies the working tree is untouched
after you finish, and a review that edited files is discarded along with its verdict.

Judge the diff against the unit's contract, not against your taste:

## What the unit had to make true

{acceptance}

## The decisions it had to honour

{decisions}

## The paths it was allowed to touch

{paths}

Fail the unit when the diff does any of these:
- fails to satisfy an acceptance criterion,
- contradicts a frozen decision,
- changes behaviour the unit was not asked to change,
- adds a test that would pass even if the behaviour were removed,
- introduces a failure path with no defined behaviour,
- weakens an existing test or deletes one without replacing its coverage.

Do not fail it for style, naming, or an alternative you would have preferred.

Your final message must be exactly this JSON object and nothing else:
{contract}

# The diff

{diff}",
        id = unit.id,
        title = unit.title,
        acceptance = acceptance_for(plan, unit),
        decisions = decisions_for(plan, unit),
        paths = bullets(&unit.paths),
        contract = ReviewResult::CONTRACT,
    )
}

/// Asks Critic why a unit keeps failing.
pub fn failure_diagnosis(unit: &Unit, attempts: u32, evidence: &str) -> String {
    format!(
        "{COMMON}

# Your job: diagnose a repeated failure

Unit {id} — {title} has now failed {attempts} times. Two agents have already tried and been
rejected. Do not try to fix it yourself; work out WHY it keeps failing.

Decide which of these it is, and say so plainly:
- the unit's contract is impossible or contradictory as written,
- the test is wrong,
- the implementation approach is wrong but the contract is fine,
- the failure is environmental and unrelated to the unit.

Your final message must be exactly this JSON object and nothing else:
{contract}

Use `verdict: \"fail\"` when the run should stop, with findings that say why. Use `verdict: \"pass\"`
only when one more attempt has a specific reason to succeed, and put that reason in the findings of
a failing verdict instead if you are unsure.

# What happened

{evidence}",
        id = unit.id,
        title = unit.title,
        contract = ReviewResult::CONTRACT,
    )
}

/// Asks Deep to review the whole branch against the frozen plan.
pub fn final_review(plan_markdown: &str, diff: &str) -> String {
    format!(
        "{COMMON}

# Your job: the final review of the whole branch

Every unit has already been implemented and reviewed on its own. You are looking for what only
shows up when they are read together:

- a requirement that no unit actually delivered, even though every unit passed,
- two units that satisfy their own contracts but contradict each other,
- a decision the user made that the branch quietly does not honour,
- a seam between units with no defined behaviour,
- a secret, credential, or absolute local path that ended up in the diff,
- a change outside everything the plan describes.

You may read anything and change nothing.

Your final message must be exactly this JSON object and nothing else:
{contract}

# The frozen plan

{plan_markdown}

# The complete branch diff

{diff}",
        contract = ReviewResult::CONTRACT
    )
}

/// Asks Deep to work out what a plan conflict costs and what must be re-decided.
pub fn conflict_replan(plan_markdown: &str, unit: &Unit, conflict: &str) -> String {
    format!(
        "{COMMON}

# Your job: work out what this plan conflict changes

While building {id} — {title}, the worker found that the frozen plan cannot hold:

{conflict}

Say exactly which decisions must be put back to the user, which requirements and units are affected,
and which already-accepted units remain valid. Do not answer the decisions yourself; the user does
that.

Your final message must be exactly this JSON object and nothing else:
{contract}

Use `verdict: \"fail\"` with one finding per decision that must be re-asked.

# The frozen plan

{plan_markdown}",
        id = unit.id,
        title = unit.title,
        contract = ReviewResult::CONTRACT,
    )
}

fn acceptance_for(plan: &Plan, unit: &Unit) -> String {
    let items: Vec<String> = unit
        .acceptance_ids
        .iter()
        .filter_map(|id| plan.acceptance.iter().find(|a| &a.id == id))
        .map(|a| format!("{}: {}", a.id, a.observable))
        .collect();
    bullets(&items)
}

fn decisions_for(plan: &Plan, unit: &Unit) -> String {
    // A unit's decisions are the ones reachable through its acceptance criteria and requirements.
    // Sending the whole decision list instead would bury the few that actually constrain the work.
    let requirement_ids: Vec<&String> = unit
        .acceptance_ids
        .iter()
        .filter_map(|id| plan.acceptance.iter().find(|a| &a.id == id))
        .flat_map(|a| a.requirement_ids.iter())
        .collect();
    let mut items: Vec<String> = plan
        .requirements
        .iter()
        .filter(|r| requirement_ids.contains(&&r.id))
        .flat_map(|r| r.decision_ids.iter())
        .filter_map(|id| plan.decision(id))
        .filter_map(|d| {
            d.resolved_value()
                .ok()
                .flatten()
                .map(|value| format!("{}: {} -> {}", d.id, d.question, value))
        })
        .collect();
    items.sort();
    items.dedup();
    bullets(&items)
}

/// The twelve surfaces with their current status, so the planner sees what is still open.
fn surface_list(plan: &Plan) -> String {
    let applicable = plan.applicable_surfaces();
    let items: Vec<String> = SURFACES
        .iter()
        .map(|surface| {
            let status = if applicable.contains(surface) {
                let answered = plan
                    .decisions_on(*surface)
                    .iter()
                    .filter(|d| d.is_answered().unwrap_or(false))
                    .count();
                format!("applicable, {answered} answered")
            } else {
                "not applicable (the user confirmed it)".to_string()
            };
            format!("{} — {} [{status}]", surface.id(), Surface::title(*surface))
        })
        .collect();
    bullets(&items)
}

fn fact_list(plan: &Plan) -> String {
    let items: Vec<String> = plan
        .facts
        .iter()
        .map(|f| {
            format!(
                "{}: {} — {} ({})",
                f.id,
                f.question,
                f.answer,
                f.sources.join(", ")
            )
        })
        .collect();
    bullets(&items)
}

fn bullets<S: AsRef<str>>(items: &[S]) -> String {
    if items.is_empty() {
        return "(none)".to_string();
    }
    items
        .iter()
        .map(|item| format!("- {}", item.as_ref()))
        .collect::<Vec<_>>()
        .join("\n")
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::plan::{
        Acceptance, Alternative, Answer, Confidence, Decision, DecisionKind, Recommendation,
        Requirement, Selection, Surface, Test,
    };

    fn plan_with_one_unit() -> Plan {
        let mut plan = Plan::new("2026-09-04-dry-run", "main", "add a dry-run flag");
        let mut decision = Decision {
            id: "C1".into(),
            surface: Surface::S4,
            kind: DecisionKind::Decision,
            question: "Call the admission webhook during dry-run?".into(),
            alternatives: vec![
                Alternative {
                    id: "ALT1".into(),
                    value: "call it".into(),
                },
                Alternative {
                    id: "ALT2".into(),
                    value: "skip it".into(),
                },
            ],
            recommendation: Recommendation::Recommended {
                choice: "ALT1".into(),
                rationale: vec!["parity with apply".into()],
                evidence: vec!["F7".into()],
                tradeoffs: vec!["webhook failures surface as dry-run failures".into()],
                impact: vec!["api".into()],
                confidence: Confidence::High,
            },
            depends_on: vec![],
            answer: None,
        };
        decision.answer = Some(Answer {
            text: "C1=REC".into(),
            selection: Selection::Recommendation,
            ts: "2026-09-04T00:00:00Z".into(),
            identity: decision.identity_digest().unwrap(),
            recommendation: Some(decision.recommendation_digest().unwrap()),
        });
        plan.decisions.push(decision);
        plan.requirements.push(Requirement {
            id: "R1".into(),
            statement: "dry-run calls the webhook".into(),
            decision_ids: vec!["C1".into()],
        });
        plan.acceptance.push(Acceptance {
            id: "A1".into(),
            requirement_ids: vec!["R1".into()],
            observable: "`kubectl apply --dry-run` reports the webhook's rejection".into(),
        });
        plan.units.push(Unit {
            id: "U1".into(),
            title: "wire the dry-run flag".into(),
            paths: vec!["src/apply/".into()],
            acceptance_ids: vec!["A1".into()],
            depends_on: vec![],
            probe: false,
        });
        plan.tests.push(Test {
            id: "T1".into(),
            command: "cargo test --test dry_run".into(),
            acceptance_ids: vec!["A1".into()],
            unit_id: "U1".into(),
        });
        plan.full_suite = "cargo test".into();
        plan
    }

    #[test]
    fn every_prompt_carries_the_common_rules() {
        let plan = plan_with_one_unit();
        let unit = plan.unit("U1").unwrap();
        let prompts = [
            fact_finder("q"),
            cold_consumer("plan"),
            plan_critic("plan"),
            implementer(&plan, unit, &[]),
            unit_reviewer(&plan, unit, "diff"),
            failure_diagnosis(unit, 3, "evidence"),
            final_review("plan", "diff"),
            conflict_replan("plan", unit, "conflict"),
        ];
        for prompt in &prompts {
            assert!(
                prompt.contains("The frozen plan is the contract"),
                "{prompt}"
            );
            assert!(prompt.contains("Hwahap owns the repository"), "{prompt}");
        }
    }

    #[test]
    fn every_reporting_prompt_quotes_its_exact_result_contract() {
        let plan = plan_with_one_unit();
        let unit = plan.unit("U1").unwrap();
        for prompt in [
            cold_consumer("plan"),
            plan_critic("plan"),
            unit_reviewer(&plan, unit, "diff"),
            failure_diagnosis(unit, 2, "e"),
            final_review("plan", "diff"),
            conflict_replan("plan", unit, "c"),
        ] {
            assert!(
                prompt.contains(ReviewResult::CONTRACT),
                "missing review contract"
            );
        }
        assert!(implementer(&plan, unit, &[]).contains(WorkerResult::CONTRACT));
    }

    #[test]
    fn the_implementer_is_told_its_paths_its_tests_and_its_decisions() {
        let plan = plan_with_one_unit();
        let prompt = implementer(&plan, plan.unit("U1").unwrap(), &[]);
        assert!(prompt.contains("- src/apply/"), "{prompt}");
        assert!(prompt.contains("`cargo test --test dry_run`"), "{prompt}");
        assert!(
            prompt.contains("C1: Call the admission webhook during dry-run? -> call it"),
            "{prompt}"
        );
        assert!(prompt.contains("A1: `kubectl apply --dry-run`"), "{prompt}");
    }

    #[test]
    fn a_first_attempt_has_no_rework_section_and_a_retry_does() {
        let plan = plan_with_one_unit();
        let unit = plan.unit("U1").unwrap();
        assert!(!implementer(&plan, unit, &[]).contains("previous attempt was rejected"));
        let retry = implementer(&plan, unit, &["U1 changed an unlisted path".to_string()]);
        assert!(retry.contains("previous attempt was rejected"), "{retry}");
        assert!(retry.contains("- U1 changed an unlisted path"), "{retry}");
    }

    #[test]
    fn prompts_are_byte_stable_for_the_same_input() {
        let plan = plan_with_one_unit();
        let unit = plan.unit("U1").unwrap();
        assert_eq!(implementer(&plan, unit, &[]), implementer(&plan, unit, &[]));
        assert_eq!(
            unit_reviewer(&plan, unit, "d"),
            unit_reviewer(&plan, unit, "d")
        );
    }

    #[test]
    fn reordering_the_plan_does_not_change_the_implementer_brief() {
        let plan = plan_with_one_unit();
        let mut shuffled = plan.clone();
        shuffled.decisions.reverse();
        shuffled.requirements.reverse();
        shuffled.acceptance.reverse();
        assert_eq!(
            implementer(&plan, plan.unit("U1").unwrap(), &[]),
            implementer(&shuffled, shuffled.unit("U1").unwrap(), &[])
        );
    }

    #[test]
    fn an_unanswered_decision_is_not_presented_as_settled() {
        let mut plan = plan_with_one_unit();
        plan.decision_mut("C1").unwrap().answer = None;
        let prompt = implementer(&plan, plan.unit("U1").unwrap(), &[]);
        assert!(
            !prompt.contains("C1: Call the admission webhook"),
            "{prompt}"
        );
    }

    #[test]
    fn a_unit_with_no_tests_says_none_rather_than_rendering_an_empty_list() {
        let mut plan = plan_with_one_unit();
        plan.tests.clear();
        let prompt = implementer(&plan, plan.unit("U1").unwrap(), &[]);
        assert!(prompt.contains("(none)"), "{prompt}");
    }

    #[test]
    fn bullets_render_one_item_per_line_and_handle_emptiness() {
        assert_eq!(bullets::<String>(&[]), "(none)");
        assert_eq!(bullets(&["a", "b"]), "- a\n- b");
        assert_eq!(bullets(&["단일 항목"]), "- 단일 항목");
    }

    #[test]
    fn the_implementer_is_told_that_only_the_host_judges_the_tests() {
        let plan = plan_with_one_unit();
        let prompt = implementer(&plan, plan.unit("U1").unwrap(), &[]);
        assert!(
            prompt.contains("Your own account of whether they"),
            "{prompt}"
        );
        assert!(prompt.contains("discards the whole attempt"), "{prompt}");
    }

    #[test]
    fn the_reviewer_is_told_it_may_not_write() {
        let plan = plan_with_one_unit();
        let prompt = unit_reviewer(&plan, plan.unit("U1").unwrap(), "diff");
        assert!(prompt.contains("You may not change anything"), "{prompt}");
        assert!(
            prompt.contains("discarded along with its verdict"),
            "{prompt}"
        );
    }

    #[test]
    fn the_worker_is_told_a_plan_conflict_must_leave_no_diff() {
        let plan = plan_with_one_unit();
        let prompt = implementer(&plan, plan.unit("U1").unwrap(), &[]);
        assert!(prompt.contains("change no files at all"), "{prompt}");
    }
}
