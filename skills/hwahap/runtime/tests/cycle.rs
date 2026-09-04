//! The whole cycle, driven by a scripted agent against a real repository.
//!
//! Every test here asserts something Hwahap promises the user: that the plan is confirmed before
//! anything is built, that nothing is asked after the freeze, that an agent's claim of success is
//! not evidence, and that shipping is refused unless what was reviewed is still what is there.
//!
//! Unix only, and deliberately not papered over: the harness runs a POSIX `sh` stub for `gh`, and
//! the engine itself runs a plan's test commands through `sh -c`. Both are real constraints on
//! where Hwahap works today rather than test-only shortcuts, and PLATFORM.md records the gap.
#![cfg(unix)]

mod common;

use common::{git, step, Fixture, Reply, Script, NOW};
use hwahap::engine::StepOutcome;
use hwahap::profile::Role;

// ---------------------------------------------------------------- the fixture plan

const REQUEST: &str = "Add a generated file and document it";

fn facts() -> String {
    serde_json::json!({
        "facts": [{
            "id": "F1",
            "question": "what does the repository already contain?",
            "answer": "one seed file under src/",
            "sources": ["src/existing.txt:1"]
        }]
    })
    .to_string()
}

fn decisions() -> String {
    let not_applicable: Vec<serde_json::Value> = (2..=12)
        .map(|n| {
            serde_json::json!({
                "surface": format!("S{n}"),
                "reason": "this change has no surface here"
            })
        })
        .collect();
    serde_json::json!({
        "decisions": [
            {
                "id": "C1",
                "surface": "S1",
                "kind": "decision",
                "question": "Should the generated file be appended to or replaced?",
                "alternatives": [
                    {"id": "ALT1", "value": "replace it every run"},
                    {"id": "ALT2", "value": "append to it"}
                ],
                "recommendation": {
                    "mode": "recommended",
                    "choice": "ALT1",
                    "rationale": ["a replaced file is reproducible"],
                    "evidence": ["F1"],
                    "tradeoffs": ["history is lost"],
                    "impact": ["files"],
                    "confidence": "high"
                },
                "depends_on": []
            },
            {
                "id": "C2",
                "surface": "S1",
                "kind": "scenario",
                "question": "What must happen when the documentation directory does not exist?",
                "alternatives": [
                    {"id": "ALT1", "value": "create it"},
                    {"id": "ALT2", "value": "fail with a typed error"}
                ],
                "recommendation": {
                    "mode": "no_recommendation",
                    "rationale": ["both are defensible and the user must choose"]
                },
                "depends_on": []
            }
        ],
        "not_applicable": not_applicable
    })
    .to_string()
}

/// The answers that settle the whole plan in one message.
fn all_answers() -> String {
    let mut lines = vec!["C1=REC".to_string(), "C2=ALT1".to_string()];
    lines.extend((2..=12).map(|n| format!("S{n}=NA")));
    lines.join("\n")
}

fn structure() -> String {
    serde_json::json!({
        "requirements": [
            {"id": "R1", "statement": "a generated file exists", "decision_ids": ["C1"]},
            {"id": "R2", "statement": "the documentation directory is created", "decision_ids": ["C2"]}
        ],
        "acceptance": [
            {"id": "A1", "requirement_ids": ["R1"], "observable": "src/added.txt exists"},
            {"id": "A2", "requirement_ids": ["R2"], "observable": "docs/added.md exists"}
        ],
        "units": [
            {"id": "U1", "title": "generate the file", "paths": ["src/"],
             "acceptance_ids": ["A1"], "depends_on": [], "probe": false},
            {"id": "U2", "title": "document it", "paths": ["docs/"],
             "acceptance_ids": ["A2"], "depends_on": ["U1"], "probe": false}
        ],
        "tests": [
            {"id": "T1", "command": "test -f src/added.txt", "acceptance_ids": ["A1"], "unit_id": "U1"},
            {"id": "T2", "command": "test -f docs/added.md", "acceptance_ids": ["A2"], "unit_id": "U2"}
        ],
        "full_suite": "test -f src/added.txt && test -f docs/added.md"
    })
    .to_string()
}

const PASS: &str = r#"{"verdict":"pass","findings":[]}"#;
const DONE: &str = r#"{"status":"completed","summary":"did the unit"}"#;

fn build_u1() -> Reply {
    Reply::write(&[("src/added.txt", "generated\n")], DONE)
}

fn build_u2() -> Reply {
    Reply::write(&[("docs/added.md", "# added\n")], DONE)
}

/// The sessions a clean run asks for, from the request to the draft pull request.
fn happy_path_steps() -> Vec<common::Step> {
    vec![
        step(Role::FactFinder, Reply::say(facts())),
        step(Role::Recommender, Reply::say(decisions())),
        step(Role::PlanSynthesis, Reply::say(structure())),
        step(Role::ColdConsumer, Reply::say(PASS)),
        step(Role::PlanCritic, Reply::say(PASS)),
        step(Role::Implementer, build_u1()),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(Role::Implementer, build_u2()),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(Role::FinalReview, Reply::say(PASS)),
    ]
}

// ------------------------------------------------------------------- small helpers

/// The challenge Hwahap printed in a message, e.g. from `CONFIRM PLAN 7F3A91C2`.
fn challenge_in(message: &str, keyword: &str) -> String {
    let start = message
        .find(keyword)
        .unwrap_or_else(|| panic!("{keyword:?} does not appear in:\n{message}"))
        + keyword.len();
    message[start..]
        .trim_start()
        .chars()
        .take(8)
        .collect::<String>()
}

/// Runs PLAN up to the confirmation prompt and returns the challenge.
async fn plan_to_confirmation(fixture: &Fixture, script: &Script) -> String {
    let engine = fixture.engine();

    let started = engine.step_with(script, Some(REQUEST), None).await.unwrap();
    assert_eq!(started.next, "continue");
    assert_eq!(started.state, "inspecting");

    let asked = engine.step_with(script, None, None).await.unwrap();
    assert_eq!(asked.next, "await_user");
    assert_eq!(asked.state, "deciding");

    let answered = engine
        .step_with(script, None, Some(&all_answers()))
        .await
        .unwrap();
    assert_eq!(answered.next, "continue", "{}", answered.message);
    assert_eq!(answered.state, "proving");

    let proved = engine.step_with(script, None, None).await.unwrap();
    assert_eq!(proved.next, "await_user", "{}", proved.message);
    assert_eq!(proved.state, "awaiting_confirmation", "{}", proved.message);
    challenge_in(&proved.message, "CONFIRM PLAN ")
}

/// Runs the whole cycle and returns every outcome from the confirmation onwards.
async fn run_to_draft_pr(fixture: &Fixture, script: &Script) -> Vec<StepOutcome> {
    let challenge = plan_to_confirmation(fixture, script).await;
    let engine = fixture.engine();
    let mut outcomes = Vec::new();

    outcomes.push(
        engine
            .step_with(script, None, Some(&format!("CONFIRM PLAN {challenge}")))
            .await
            .unwrap(),
    );
    while outcomes.last().expect("at least one").next == "continue" {
        outcomes.push(engine.step_with(script, None, None).await.unwrap());
    }
    outcomes
}

// ------------------------------------------------------------------------- the tests

#[tokio::test]
async fn a_clean_run_reaches_a_draft_pull_request() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let last = outcomes.last().expect("at least one outcome");

    assert_eq!(last.state, "awaiting_adjust_or_ship", "{}", last.message);
    assert_eq!(last.next, "await_user");
    assert_eq!(
        last.pr_url.as_deref(),
        Some("https://github.com/example/repo/pull/1")
    );
    assert!(last.plan_digest.is_some());
    assert_eq!(script.remaining(), 0, "the script has unused sessions left");
}

#[tokio::test]
async fn the_user_is_asked_nothing_between_the_freeze_and_the_pull_request() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let (last, autonomous) = outcomes.split_last().expect("at least one outcome");

    for outcome in autonomous {
        assert_eq!(
            outcome.next, "continue",
            "the cycle stopped for the user at {}: {}",
            outcome.state, outcome.message
        );
    }
    assert_eq!(last.state, "awaiting_adjust_or_ship");
}

#[tokio::test]
async fn each_role_runs_on_its_own_fixed_profile_and_the_writers_run_in_the_worktree() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;

    assert_eq!(
        script.roles(),
        vec![
            Role::FactFinder,
            Role::Recommender,
            Role::PlanSynthesis,
            Role::ColdConsumer,
            Role::PlanCritic,
            Role::Implementer,
            Role::UnitReviewer,
            Role::Implementer,
            Role::UnitReviewer,
            Role::FinalReview,
        ]
    );
    for call in script.calls() {
        if matches!(call.role, Role::Implementer | Role::Rework) {
            assert_eq!(
                call.cwd,
                fixture.worktree(),
                "a writer ran outside the worktree"
            );
        }
    }
}

#[tokio::test]
async fn an_accepted_unit_leaves_a_checkpoint_commit_naming_the_unit_and_the_plan_digest() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let digest = outcomes
        .last()
        .expect("outcome")
        .plan_digest
        .clone()
        .expect("a frozen plan has a digest");

    let worktree = fixture.worktree();
    let subjects = fixture.log_subjects(&worktree);
    assert_eq!(
        subjects.iter().filter(|s| s.starts_with("hwahap(")).count(),
        2,
        "expected one checkpoint per unit, got {subjects:?}"
    );

    for unit in ["U1", "U2"] {
        let body = fixture.commit_body(&worktree, &format!("hwahap({unit})"));
        assert!(body.contains(&format!("unit: {unit}")), "{body}");
        assert!(body.contains(&format!("plan-digest: {digest}")), "{body}");
    }
}

#[tokio::test]
async fn a_plain_language_confirmation_never_freezes_the_plan() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();

    for attempt in [
        "ok",
        "yes",
        "looks good",
        "confirm plan",
        "CONFIRM PLAN",
        "추천대로",
    ] {
        let outcome = engine
            .step_with(&script, None, Some(attempt))
            .await
            .unwrap();
        assert_eq!(
            outcome.state, "awaiting_confirmation",
            "{attempt:?} froze the plan: {}",
            outcome.message
        );
        assert_eq!(outcome.next, "await_user");
    }
    assert!(
        !fixture.worktree().exists(),
        "a branch was created without a confirmation"
    );
}

#[tokio::test]
async fn a_challenge_from_a_different_plan_is_refused() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();

    let outcome = engine
        .step_with(&script, None, Some("CONFIRM PLAN DEADBEEF"))
        .await
        .unwrap();
    assert_eq!(outcome.state, "awaiting_confirmation");
    assert!(outcome.message.contains("DEADBEEF"), "{}", outcome.message);
    assert!(!fixture.worktree().exists());
}

#[tokio::test]
async fn changing_an_answer_at_the_confirmation_prompt_invalidates_the_challenge() {
    let fixture = Fixture::new();
    // Planning sessions only: this run never gets as far as building anything.
    let mut steps = happy_path_steps();
    steps.truncate(5);
    // Re-proving runs the two plan reviews again, because a review binds to what it reviewed.
    steps.push(step(Role::ColdConsumer, Reply::say(PASS)));
    steps.push(step(Role::PlanCritic, Reply::say(PASS)));
    let script = Script::new(steps);

    let challenge = plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();

    let changed = engine
        .step_with(&script, None, Some("C1=ALT2"))
        .await
        .unwrap();
    assert_eq!(changed.state, "deciding", "{}", changed.message);

    let mut reproved = engine.step_with(&script, None, None).await.unwrap();
    while reproved.next == "continue" {
        reproved = engine.step_with(&script, None, None).await.unwrap();
    }
    assert_eq!(
        reproved.state, "awaiting_confirmation",
        "{}",
        reproved.message
    );
    assert_ne!(
        challenge_in(&reproved.message, "CONFIRM PLAN "),
        challenge,
        "the challenge did not move when an answer did"
    );
}

#[tokio::test]
async fn a_unit_that_writes_outside_its_declared_paths_is_discarded_and_reworked() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    // U1 may only touch src/. Have it also write outside, then behave on the retry.
    steps[5] = step(
        Role::Implementer,
        Reply::write(
            &[
                ("src/added.txt", "generated\n"),
                ("elsewhere.txt", "oops\n"),
            ],
            DONE,
        ),
    );
    steps.insert(6, step(Role::Rework, build_u1()));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship"
    );

    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1, "expected exactly one rework");
    assert!(rework[0].contains("elsewhere.txt"), "{}", rework[0]);
    assert!(rework[0].contains("outside"), "{}", rework[0]);

    // The discarded file is not in the branch, and no checkpoint recorded it.
    assert!(!fixture.worktree().join("elsewhere.txt").exists());
    let tracked = git(&fixture.worktree(), &["ls-files"]);
    assert!(!tracked.contains("elsewhere.txt"), "{tracked}");
}

#[tokio::test]
async fn a_unit_whose_test_fails_is_reworked_with_the_failure_quoted() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    // Claim success while writing a file the unit's test does not accept.
    steps[5] = step(
        Role::Implementer,
        Reply::write(&[("src/wrong.txt", "not what T1 checks\n")], DONE),
    );
    steps.insert(6, step(Role::Rework, build_u1()));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship"
    );

    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1);
    assert!(
        rework[0].contains("test -f src/added.txt"),
        "the rework prompt does not quote the failing command:\n{}",
        rework[0]
    );
}

#[tokio::test]
async fn a_unit_rejected_by_the_reviewer_is_reworked_with_the_findings() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps[6] = step(
        Role::UnitReviewer,
        Reply::say(r#"{"verdict":"fail","findings":["the file has no trailing newline"]}"#),
    );
    steps.insert(7, step(Role::Rework, build_u1()));
    steps.insert(8, step(Role::UnitReviewer, Reply::say(PASS)));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship"
    );

    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1);
    assert!(
        rework[0].contains("the file has no trailing newline"),
        "{}",
        rework[0]
    );
}

#[tokio::test]
async fn a_review_session_that_changes_the_working_tree_has_its_verdict_discarded() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps[6] = step(
        Role::UnitReviewer,
        Reply::write(&[("src/sneaky.txt", "the reviewer wrote this\n")], PASS),
    );
    steps.insert(7, step(Role::Rework, build_u1()));
    steps.insert(8, step(Role::UnitReviewer, Reply::say(PASS)));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship"
    );

    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1, "the passing verdict was accepted");
    assert!(
        rework[0].contains("changed the working tree"),
        "{}",
        rework[0]
    );
    assert!(!fixture.worktree().join("src/sneaky.txt").exists());
}

#[tokio::test]
async fn a_worker_whose_final_message_is_not_the_contract_is_reworked() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps[5] = step(
        Role::Implementer,
        Reply::write(
            &[("src/added.txt", "generated\n")],
            "Done! I added the file. Everything passes.",
        ),
    );
    steps.insert(6, step(Role::Rework, build_u1()));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship"
    );

    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1);
    assert!(
        rework[0].contains("did not start with a JSON object"),
        "{}",
        rework[0]
    );
}

#[tokio::test]
async fn a_plan_conflict_that_also_wrote_code_is_rejected_as_a_rework() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps[5] = step(
        Role::Implementer,
        Reply::write(
            &[("src/added.txt", "generated\n")],
            r#"{"status":"plan_conflict","summary":"cannot","conflict":"C1 is impossible"}"#,
        ),
    );
    steps.insert(6, step(Role::Rework, build_u1()));
    let script = Script::new(steps);

    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(
        outcomes.last().expect("outcome").state,
        "awaiting_adjust_or_ship",
        "a dirty plan conflict was accepted"
    );
    let rework = script.prompts_for(Role::Rework);
    assert_eq!(rework.len(), 1);
    assert!(
        rework[0].contains("must leave the working tree untouched"),
        "{}",
        rework[0]
    );
}

#[tokio::test]
async fn a_clean_plan_conflict_stops_the_run_without_committing_anything() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps.truncate(5);
    steps.push(step(
        Role::Implementer,
        Reply::say(
            r#"{"status":"plan_conflict","summary":"cannot","conflict":"C1 assumes a sync API"}"#,
        ),
    ));
    let script = Script::new(steps);

    let challenge = plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();
    engine
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    let outcome = engine.step_with(&script, None, None).await.unwrap();

    assert_eq!(outcome.state, "plan_conflict", "{}", outcome.message);
    assert_eq!(outcome.next, "await_user");
    assert!(
        outcome.message.contains("C1 assumes a sync API"),
        "{}",
        outcome.message
    );

    let subjects = fixture.log_subjects(&fixture.worktree());
    assert!(
        !subjects.iter().any(|s| s.starts_with("hwahap(")),
        "a conflicting run left a checkpoint: {subjects:?}"
    );
}

#[tokio::test]
async fn accepted_checkpoints_survive_a_restart_and_only_the_current_unit_re_runs() {
    let fixture = Fixture::new();
    // Stop after U1 is accepted by having U2's implementer fail the session outright.
    let mut steps = happy_path_steps();
    steps.truncate(7);
    steps.push(step(
        Role::Implementer,
        Reply::Fail("the adapter died".into()),
    ));
    let script = Script::new(steps);

    let challenge = plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();
    engine
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    let crashed = engine.step_with(&script, None, None).await;
    assert!(crashed.is_err(), "the dropped session should have surfaced");
    drop(engine);

    let worktree = fixture.worktree();
    let after_crash = fixture.log_subjects(&worktree);
    assert!(
        after_crash.iter().any(|s| s.contains("hwahap(U1)")),
        "U1's checkpoint did not survive: {after_crash:?}"
    );

    // A fresh engine resumes from the last checkpoint and asks only for what is left.
    let resumed = Script::new(vec![
        step(Role::Implementer, build_u2()),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(Role::FinalReview, Reply::say(PASS)),
    ]);
    let engine = fixture.engine();
    let mut outcome = engine.step_with(&resumed, None, None).await.unwrap();
    while outcome.next == "continue" {
        outcome = engine.step_with(&resumed, None, None).await.unwrap();
    }

    assert_eq!(
        outcome.state, "awaiting_adjust_or_ship",
        "{}",
        outcome.message
    );
    assert_eq!(
        resumed
            .calls()
            .iter()
            .filter(|c| c.unit.as_deref() == Some("U1"))
            .count(),
        0,
        "an already accepted unit was rebuilt"
    );
    let subjects = fixture.log_subjects(&worktree);
    assert_eq!(
        subjects.iter().filter(|s| s.starts_with("hwahap(")).count(),
        2,
        "{subjects:?}"
    );
}

#[tokio::test]
async fn a_second_request_is_refused_while_a_run_is_active() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let engine = fixture.engine();

    engine
        .step_with(&script, Some(REQUEST), None)
        .await
        .unwrap();
    let err = engine
        .step_with(&script, Some("something else"), None)
        .await
        .unwrap_err();
    let message = err.to_string();
    assert!(message.contains("already active"), "{message}");
    assert!(
        message.contains("one active run per repository"),
        "{message}"
    );
}

#[tokio::test]
async fn status_reports_the_run_without_changing_a_byte_of_it() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let engine = fixture.engine();

    engine
        .step_with(&script, Some(REQUEST), None)
        .await
        .unwrap();
    let run_path = fixture.repo.join(".hwahap/run.json");
    let journal_path = fixture.repo.join(".hwahap/events.jsonl");

    let before = (
        std::fs::read(&run_path).unwrap(),
        std::fs::read(&journal_path).unwrap(),
    );
    let reported = engine.status().unwrap();
    let after = (
        std::fs::read(&run_path).unwrap(),
        std::fs::read(&journal_path).unwrap(),
    );

    assert_eq!(before, after, "status wrote to the run");
    assert_eq!(reported.state, "inspecting");
    assert_eq!(reported.next, "continue");
}

#[tokio::test]
async fn status_on_a_repository_with_no_run_says_so_rather_than_failing() {
    let fixture = Fixture::new();
    let reported = fixture.engine().status().unwrap();
    assert_eq!(reported.state, "no_run");
    assert_eq!(reported.next, "await_user");
    assert!(reported.pr_url.is_none());
}

#[tokio::test]
async fn ship_marks_the_pull_request_ready_only_on_the_exact_challenge() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let summary = &outcomes.last().expect("outcome").message;
    let challenge = challenge_in(summary, "SHIP ");
    let engine = fixture.engine();

    for wrong in ["ok", "ship it", "SHIP DEADBEEF", "SHIP"] {
        let err = engine.ship(wrong).unwrap_err().to_string();
        assert!(!err.is_empty(), "{wrong:?} was accepted");
        assert!(
            !fixture.was_marked_ready(),
            "{wrong:?} shipped the pull request"
        );
    }

    let shipped = engine.ship(&format!("SHIP {challenge}")).unwrap();
    assert_eq!(shipped.state, "shipped");
    assert_eq!(shipped.next, "completed");
    assert!(fixture.was_marked_ready());
}

#[tokio::test]
async fn ship_is_refused_when_the_pull_request_head_has_moved() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let challenge = challenge_in(&outcomes.last().expect("outcome").message, "SHIP ");

    fixture.move_pr_head("0000000000000000000000000000000000000000");
    let err = fixture
        .engine()
        .ship(&format!("SHIP {challenge}"))
        .unwrap_err()
        .to_string();

    assert!(err.contains("head is now"), "{err}");
    assert!(!fixture.was_marked_ready());
}

#[tokio::test]
async fn ship_is_refused_when_a_required_check_has_not_succeeded() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let challenge = challenge_in(&outcomes.last().expect("outcome").message, "SHIP ");

    fixture.fail_checks();
    let err = fixture
        .engine()
        .ship(&format!("SHIP {challenge}"))
        .unwrap_err()
        .to_string();

    assert!(err.contains("checks"), "{err}");
    assert!(!fixture.was_marked_ready());
}

#[tokio::test]
async fn ship_is_refused_before_there_is_a_pull_request() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    plan_to_confirmation(&fixture, &script).await;

    let err = fixture
        .engine()
        .ship("SHIP ABCD1234")
        .unwrap_err()
        .to_string();
    assert!(err.contains("nothing to ship"), "{err}");
}

#[tokio::test]
async fn a_session_whose_applied_model_differs_from_the_requested_one_stops_the_run() {
    let fixture = Fixture::new();
    let script = Script::new(vec![step(
        Role::FactFinder,
        Reply::SayWithSkewedReceipt(facts()),
    )]);
    let engine = fixture.engine();

    engine
        .step_with(&script, Some(REQUEST), None)
        .await
        .unwrap();
    let err = engine.step_with(&script, None, None).await.unwrap_err();
    let message = err.to_string();
    assert!(message.starts_with("unsupported_profile: "), "{message}");
    assert!(message.contains("gpt-5.4-mini"), "{message}");
}

#[tokio::test]
async fn the_run_is_recorded_in_a_journal_that_verifies() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;

    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    store.verify_chain().unwrap();
    let events = store.read_events().unwrap();
    assert!(
        events.len() >= 6,
        "only {} transitions were recorded",
        events.len()
    );
    assert_eq!(events.first().expect("first").seq, 1);
    assert_eq!(
        events.last().expect("last").seq,
        events.len() as u64,
        "the journal skipped a sequence number"
    );
    assert!(events.iter().all(|e| e.ts == NOW));
}

#[tokio::test]
async fn the_plan_and_its_rendering_are_written_where_the_user_is_told_to_look() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let challenge = plan_to_confirmation(&fixture, &script).await;

    let markdown = std::fs::read_to_string(fixture.repo.join(".hwahap/plan.md")).unwrap();
    assert!(markdown.contains(&challenge), "plan.md omits the challenge");
    assert!(markdown.contains("C1"), "plan.md omits the decisions");
    assert!(markdown.contains("U1"), "plan.md omits the units");

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(plan["schema"], "hwahap/v3");
}

#[tokio::test]
async fn feedback_on_the_pull_request_reopens_planning_at_the_next_revision() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;
    let engine = fixture.engine();

    let adjusted = engine
        .step_with(
            &script,
            None,
            Some("the documentation should mention the flag"),
        )
        .await
        .unwrap();

    assert_eq!(adjusted.state, "deciding", "{}", adjusted.message);
    assert_eq!(adjusted.next, "await_user");
    assert!(
        adjusted
            .message
            .contains("the documentation should mention the flag"),
        "the adjustment was not echoed back: {}",
        adjusted.message
    );

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(plan["revision"], 2, "the revision did not advance");
    assert!(plan["frozen"].is_null(), "the plan is still frozen");

    // The branch is untouched: an adjustment adds corrections, it does not rewind history.
    let subjects = fixture.log_subjects(&fixture.worktree());
    assert_eq!(
        subjects.iter().filter(|s| s.starts_with("hwahap(")).count(),
        2,
        "an adjustment discarded accepted work: {subjects:?}"
    );
}

#[tokio::test]
async fn an_empty_adjustment_changes_nothing() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;
    let engine = fixture.engine();

    let before = std::fs::read(fixture.repo.join(".hwahap/plan.json")).unwrap();
    let outcome = engine.step_with(&script, None, Some("   ")).await.unwrap();
    let after = std::fs::read(fixture.repo.join(".hwahap/plan.json")).unwrap();

    assert_eq!(outcome.state, "awaiting_adjust_or_ship");
    assert_eq!(before, after, "whitespace reopened the plan");
}

#[tokio::test]
async fn a_finished_run_is_archived_before_the_next_one_starts() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let challenge = challenge_in(&outcomes.last().expect("outcome").message, "SHIP ");
    let engine = fixture.engine();
    engine.ship(&format!("SHIP {challenge}")).unwrap();

    let next = Script::new(vec![step(Role::FactFinder, Reply::say(facts()))]);
    let started = engine
        .step_with(&next, Some("a different request"), None)
        .await
        .unwrap();

    assert_eq!(started.state, "inspecting");
    assert!(
        fixture
            .repo
            .join(".hwahap/archive")
            .read_dir()
            .expect("archive")
            .count()
            > 0,
        "the finished run was overwritten rather than archived"
    );
}

#[tokio::test]
async fn advancing_with_no_run_and_no_request_says_what_is_missing() {
    let fixture = Fixture::new();
    let script = Script::new(vec![]);
    let err = fixture
        .engine()
        .step_with(&script, None, None)
        .await
        .unwrap_err()
        .to_string();
    assert!(err.contains("no active Hwahap run"), "{err}");
    assert!(err.contains("request"), "{err}");
}

#[tokio::test]
async fn an_empty_request_is_refused() {
    let fixture = Fixture::new();
    let script = Script::new(vec![]);
    for empty in ["", "   ", "\n\t"] {
        let err = fixture
            .engine()
            .step_with(&script, Some(empty), None)
            .await
            .unwrap_err()
            .to_string();
        assert!(err.contains("request is empty"), "{empty:?} -> {err}");
    }
}
