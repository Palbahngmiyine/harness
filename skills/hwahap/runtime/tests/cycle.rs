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

#[tokio::test]
async fn repeated_failure_gets_one_astra_repair_and_no_separate_diagnosis() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps()[..5].to_vec();
    let failed = r#"{"status":"failed","summary":"reproducible failure"}"#;
    steps.push(step(Role::Implementer, Reply::say(failed)));
    steps.push(step(Role::Rework, Reply::say(failed)));
    let script = Script::new(steps);
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(outcomes.last().unwrap().state, "blocked");
    assert!(outcomes.last().unwrap().message.contains("2 attempts"));
    assert_eq!(
        script
            .roles()
            .iter()
            .filter(|r| **r == Role::Rework)
            .count(),
        1
    );
    assert!(!script.roles().contains(&Role::FailureDiagnosis));
    assert_eq!(
        hwahap::profile::Profiles::defaults()
            .for_role(Role::Rework)
            .model,
        "gpt-6-astra"
    );
    assert_eq!(script.remaining(), 0);
}

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
async fn probe_output_is_discarded_without_entering_git_history() {
    let fixture = Fixture::new();
    let mut proposed: serde_json::Value = serde_json::from_str(&structure()).unwrap();
    proposed["units"]
        .as_array_mut()
        .unwrap()
        .push(serde_json::json!({
            "id": "U3", "title": "temporary experiment", "paths": ["probe/"],
            "acceptance_ids": [], "depends_on": ["U2"], "probe": true
        }));
    let mut steps = happy_path_steps();
    steps[2] = step(Role::PlanSynthesis, Reply::say(proposed.to_string()));
    steps.insert(
        9,
        step(
            Role::Implementer,
            Reply::write(&[("probe/throwaway.txt", "temporary experiment\n")], DONE),
        ),
    );
    steps.insert(10, step(Role::UnitReviewer, Reply::say(PASS)));
    let script = Script::new(steps);
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    assert_eq!(outcomes.last().unwrap().state, "awaiting_adjust_or_ship");
    let worktree = fixture.worktree();
    assert!(!worktree.join("probe/throwaway.txt").exists());
    assert_eq!(git(&worktree, &["status", "--porcelain"]), "");
    assert_eq!(
        git(
            &worktree,
            &["ls-tree", "-r", "--name-only", "HEAD", "--", "probe/"]
        ),
        ""
    );
    assert_eq!(
        git(&worktree, &["log", "--all", "--format=%H", "--", "probe/"]),
        ""
    );
    assert!(!fixture
        .log_subjects(&worktree)
        .iter()
        .any(|s| s.contains("hwahap(U3)")));
    assert_eq!(
        script
            .calls()
            .iter()
            .filter(|c| c.role == Role::UnitReviewer && c.unit.as_deref() == Some("U3"))
            .count(),
        1
    );
    assert_eq!(script.remaining(), 0);
}

#[tokio::test]
async fn conflicting_or_malformed_answers_cannot_be_hidden_by_confirmation() {
    for invalid in ["C1=ALT1\nC1=ALT2", "C1=ALT", "C1=OTHER:"] {
        let fixture = Fixture::new();
        let script = Script::new(happy_path_steps());
        let challenge = plan_to_confirmation(&fixture, &script).await;
        let store = hwahap::state::Store::open(&fixture.repo).unwrap();
        let before = store.read_plan().unwrap().unwrap();
        let outcome = fixture
            .engine()
            .step_with(
                &script,
                None,
                Some(&format!("{invalid}\nCONFIRM PLAN {challenge}")),
            )
            .await
            .unwrap();
        assert_eq!(
            outcome.state, "awaiting_confirmation",
            "{invalid}: {}",
            outcome.message
        );
        assert_eq!(outcome.next, "await_user");
        let after = store.read_plan().unwrap().unwrap();
        assert!(!after.is_frozen().unwrap());
        assert_eq!(after.digest().unwrap(), before.digest().unwrap());
        assert!(!fixture.worktree().exists());
        assert_eq!(git(&fixture.repo, &["branch", "--list", "hwahap/*"]), "");
        assert!(!script.roles().contains(&Role::Implementer));
    }
}

#[tokio::test]
async fn a_plan_changed_after_preview_requires_fresh_reviews_and_confirmation() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps()[..5].to_vec();
    steps.push(step(Role::ColdConsumer, Reply::say(PASS)));
    steps.push(step(Role::PlanCritic, Reply::say(PASS)));
    let script = Script::new(steps);
    let old_challenge = plan_to_confirmation(&fixture, &script).await;
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let mut plan = store.read_plan().unwrap().unwrap();
    plan.tests[0].command = "test -s src/added.txt".into();
    let current_challenge = plan.digest().unwrap().challenge();
    assert_ne!(current_challenge, old_challenge);
    store.write_plan(&plan).unwrap();
    let engine = fixture.engine();
    let rejected = engine
        .step_with(
            &script,
            None,
            Some(&format!("CONFIRM PLAN {old_challenge}")),
        )
        .await
        .unwrap();
    assert_eq!(rejected.state, "proving", "{}", rejected.message);
    assert!(!store.read_plan().unwrap().unwrap().is_frozen().unwrap());
    assert!(!fixture.worktree().exists());
    let preview = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(
        preview.state, "awaiting_confirmation",
        "{}",
        preview.message
    );
    let current_challenge = store
        .read_plan()
        .unwrap()
        .unwrap()
        .digest()
        .unwrap()
        .challenge();
    assert_ne!(current_challenge, old_challenge);
    assert_eq!(
        challenge_in(&preview.message, "CONFIRM PLAN "),
        current_challenge
    );
    assert_eq!(
        script
            .roles()
            .iter()
            .filter(|r| **r == Role::ColdConsumer)
            .count(),
        2
    );
    assert_eq!(
        script
            .roles()
            .iter()
            .filter(|r| **r == Role::PlanCritic)
            .count(),
        2
    );
    let stale = engine
        .step_with(
            &script,
            None,
            Some(&format!("CONFIRM PLAN {old_challenge}")),
        )
        .await
        .unwrap();
    assert_eq!(stale.state, "awaiting_confirmation");
    assert!(!fixture.worktree().exists());
    let frozen = engine
        .step_with(
            &script,
            None,
            Some(&format!("CONFIRM PLAN {current_challenge}")),
        )
        .await
        .unwrap();
    assert_eq!(frozen.state, "coding", "{}", frozen.message);
    assert!(fixture.worktree().is_dir());
    assert!(store.read_plan().unwrap().unwrap().is_frozen().unwrap());
    assert_eq!(script.remaining(), 0);
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
    // Changed answers require newly derived structure and reviews bound to that structure.
    steps.push(step(Role::PlanSynthesis, Reply::say(structure())));
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

    // The run stops, and stopping is written down: an error that merely escaped as a protocol
    // failure would leave the host with no `next` and the run resumable into the same impossibility.
    let outcome = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(outcome.next, "blocked", "{}", outcome.message);
    assert_eq!(outcome.state, "blocked");
    assert!(
        outcome.message.starts_with("unsupported_profile: "),
        "{}",
        outcome.message
    );
    assert!(
        outcome.message.contains("gpt-5.4-mini"),
        "{}",
        outcome.message
    );

    // And it survives a restart rather than being re-attempted.
    assert_eq!(fixture.engine().status().unwrap().state, "blocked");
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

    // Planning is re-entered at Inspecting, not Deciding: the adjustment has to reach the
    // Recommender, and Deciding would find a full frontier and ask nothing new.
    assert_eq!(adjusted.state, "inspecting", "{}", adjusted.message);
    assert_eq!(adjusted.next, "continue");
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
async fn identical_requests_on_one_day_build_three_distinct_runs_and_keep_archives() {
    let fixture = Fixture::new();
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let mut ids = Vec::new();
    let mut branches = std::collections::BTreeSet::new();
    for index in 0..3 {
        let script = Script::new(happy_path_steps());
        let outcomes = run_to_draft_pr(&fixture, &script).await;
        let draft = outcomes.last().unwrap();
        assert_eq!(draft.state, "awaiting_adjust_or_ship", "{}", draft.message);
        let run = store.read_run().unwrap().unwrap();
        assert!(!ids.contains(&run.run_id));
        ids.push(run.run_id);
        assert!(branches.insert(run.branch.clone()));
        let worktree = fixture.worktree();
        assert!(worktree.is_dir());
        assert_eq!(git(&worktree, &["branch", "--show-current"]), run.branch);
        assert_eq!(git(&worktree, &["show", "HEAD:src/added.txt"]), "generated");
        assert_eq!(git(&worktree, &["show", "HEAD:docs/added.md"]), "# added");
        assert_eq!(script.remaining(), 0);
        if index < 2 {
            let challenge = challenge_in(&draft.message, "SHIP ");
            fixture.engine().ship(&format!("SHIP {challenge}")).unwrap();
        }
    }
    let mut archived_ids = Vec::new();
    for entry in fixture.repo.join(".hwahap/archive").read_dir().unwrap() {
        let path = entry.unwrap().path();
        let run: hwahap::state::Run =
            serde_json::from_slice(&std::fs::read(path.join("run.json")).unwrap()).unwrap();
        archived_ids.push(run.run_id);
        for name in ["events.jsonl", "plan.json", "report.md"] {
            assert!(std::fs::metadata(path.join(name)).unwrap().len() > 0);
        }
        assert!(path.join("artifacts").read_dir().unwrap().next().is_some());
    }
    archived_ids.sort();
    ids.truncate(2);
    ids.sort();
    assert_eq!(archived_ids, ids);
}

#[tokio::test]
async fn a_new_adjustment_requirement_is_synthesized_and_only_its_unit_is_built() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let first = run_to_draft_pr(&fixture, &script).await;
    let old_head = fixture.head_sha(&fixture.worktree());
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let before = store.read_run().unwrap().unwrap();
    let old: serde_json::Value = serde_json::from_str(&decisions()).unwrap();
    let mut decision = old["decisions"][0].clone();
    decision["id"] = serde_json::json!("C3");
    decision["question"] = serde_json::json!("What extra file should be generated?");
    decision["alternatives"][0]["value"] = serde_json::json!("src/extra.txt");
    let mut proposed: serde_json::Value = serde_json::from_str(&structure()).unwrap();
    for (collection, value) in [
        (
            "requirements",
            serde_json::json!({"id":"R3", "statement":"an extra file exists", "decision_ids":["C3"]}),
        ),
        (
            "acceptance",
            serde_json::json!({"id":"A3", "requirement_ids":["R3"], "observable":"src/extra.txt exists"}),
        ),
        (
            "units",
            serde_json::json!({"id":"U3", "title":"generate extra file", "paths":["src/extra.txt"], "acceptance_ids":["A3"], "depends_on":["U2"], "probe":false}),
        ),
        (
            "tests",
            serde_json::json!({"id":"T3", "command":"test -s src/extra.txt", "acceptance_ids":["A3"], "unit_id":"U3"}),
        ),
    ] {
        proposed[collection].as_array_mut().unwrap().push(value);
    }
    proposed["full_suite"] = serde_json::json!(
        "test -f src/added.txt && test -f docs/added.md && test -s src/extra.txt"
    );
    script.extend(vec![
        step(
            Role::Recommender,
            Reply::say(
                serde_json::json!({"decisions":[decision], "not_applicable":[]}).to_string(),
            ),
        ),
        step(Role::PlanSynthesis, Reply::say(proposed.to_string())),
        step(Role::ColdConsumer, Reply::say(PASS)),
        step(Role::PlanCritic, Reply::say(PASS)),
        step(
            Role::Implementer,
            Reply::write(&[("src/extra.txt", "extra\n")], DONE),
        ),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(Role::FinalReview, Reply::say(PASS)),
    ]);
    let engine = fixture.engine();
    assert_eq!(
        engine
            .step_with(&script, None, Some("Also generate src/extra.txt"))
            .await
            .unwrap()
            .state,
        "inspecting"
    );
    assert_eq!(
        engine.step_with(&script, None, None).await.unwrap().state,
        "deciding"
    );
    assert_eq!(
        engine
            .step_with(&script, None, Some("C3=REC"))
            .await
            .unwrap()
            .state,
        "proving"
    );
    let preview = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(
        preview.state, "awaiting_confirmation",
        "{}",
        preview.message
    );
    let challenge = challenge_in(&preview.message, "CONFIRM PLAN ");
    let mut outcome = engine
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    assert_eq!(outcome.state, "coding");
    let frozen = store.read_run().unwrap().unwrap();
    assert_eq!(frozen.accepted_units, before.accepted_units);
    assert_eq!(frozen.accepted_fingerprints, before.accepted_fingerprints);
    while outcome.next == "continue" {
        outcome = engine.step_with(&script, None, None).await.unwrap();
    }
    assert_eq!(
        outcome.state, "awaiting_adjust_or_ship",
        "{}",
        outcome.message
    );
    assert_eq!(outcome.pr_url, first.last().unwrap().pr_url);
    for log in ["pr-created", "pr-edited"] {
        let calls = std::fs::read_to_string(fixture.dir.path().join(log)).unwrap();
        assert_eq!(calls.lines().count(), 1, "unexpected {log} calls: {calls}");
    }
    let after = store.read_run().unwrap().unwrap();
    assert_eq!(after.branch, before.branch);
    assert_eq!(after.revision, 2);
    assert_eq!(after.accepted_units, vec!["U1", "U2", "U3"]);
    assert_eq!(
        after.reviewed_head.as_deref(),
        Some(fixture.head_sha(&fixture.worktree()).as_str())
    );
    assert_eq!(
        git(
            &fixture.worktree(),
            &["rev-list", "--count", &format!("{old_head}..HEAD")]
        ),
        "1"
    );
    assert_eq!(
        git(&fixture.worktree(), &["show", "HEAD:src/extra.txt"]),
        "extra"
    );
    assert_eq!(
        script
            .roles()
            .iter()
            .filter(|r| **r == Role::PlanSynthesis)
            .count(),
        2
    );
    assert_eq!(
        script
            .calls()
            .iter()
            .filter(|c| c.role == Role::Implementer)
            .map(|c| c.unit.clone().unwrap())
            .collect::<Vec<_>>(),
        vec!["U1", "U2", "U3"]
    );
    assert_eq!(script.remaining(), 0);
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
async fn identical_requests_blocked_before_freeze_still_have_distinct_run_ids() {
    let fixture = Fixture::new();
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let mut ids = std::collections::BTreeSet::new();
    for _ in 0..3 {
        let script = Script::new(vec![step(
            Role::FactFinder,
            Reply::SayWithSkewedReceipt(facts()),
        )]);
        let engine = fixture.engine();
        engine
            .step_with(&script, Some(REQUEST), None)
            .await
            .unwrap();
        let blocked = engine.step_with(&script, None, None).await.unwrap();
        assert_eq!(blocked.state, "blocked");
        assert!(blocked.message.contains("unsupported_profile"));
        assert!(!fixture.worktree().exists());
        assert_eq!(git(&fixture.repo, &["branch", "--list", "hwahap/*"]), "");
        assert!(ids.insert(store.read_run().unwrap().unwrap().run_id));
        assert_eq!(script.remaining(), 0);
    }
    let mut archived = std::collections::BTreeSet::new();
    for entry in fixture.repo.join(".hwahap/archive").read_dir().unwrap() {
        let path = entry.unwrap().path();
        let run: hwahap::state::Run =
            serde_json::from_slice(&std::fs::read(path.join("run.json")).unwrap()).unwrap();
        assert!(run.state.is_terminal());
        assert!(archived.insert(run.run_id));
        assert!(std::fs::metadata(path.join("events.jsonl")).unwrap().len() > 0);
    }
    assert_eq!(archived.len(), 2);
    assert!(archived.is_subset(&ids));
    assert!(!archived.contains(&store.read_run().unwrap().unwrap().run_id));
}

#[tokio::test]
async fn a_draft_made_ready_externally_refuses_adjustment_before_pushing() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let mut run = store.read_run().unwrap().unwrap();
    let remote = git(&fixture.repo, &["ls-remote", "origin", &run.branch]);
    let worktree = fixture.worktree();
    // Resume at final verification with an accepted local adjustment checkpoint.
    std::fs::write(worktree.join("src/added.txt"), "adjusted\n").unwrap();
    git(&worktree, &["add", "src/added.txt"]);
    git(&worktree, &["commit", "-m", "accepted adjustment"]);
    let local_head = fixture.head_sha(&worktree);
    run.state = hwahap::state::RunState::FinalVerifying;
    store
        .write_run(&hwahap::clock::FixedClock::new(NOW), &run)
        .unwrap();
    std::fs::write(fixture.dir.path().join("pr-ready"), "1").unwrap();
    script.extend(vec![step(Role::FinalReview, Reply::say(PASS))]);
    match fixture.engine().step_with(&script, None, None).await {
        Err(error) => assert!(error.to_string().contains("ready"), "{error}"),
        Ok(outcome) => assert_eq!(outcome.state, "blocked", "{}", outcome.message),
    }
    assert_eq!(
        git(&fixture.repo, &["ls-remote", "origin", &run.branch]),
        remote
    );
    assert_eq!(fixture.head_sha(&worktree), local_head);
    assert_eq!(git(&worktree, &["show", "HEAD:src/added.txt"]), "adjusted");
    assert_eq!(git(&worktree, &["status", "--porcelain"]), "");
}

async fn assert_frozen_plan_tampering_is_refused(phase: &str) {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let challenge = plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();
    let mut outcome = engine
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    if phase != "coding" {
        outcome = engine.step_with(&script, None, None).await.unwrap();
        assert_eq!(outcome.state, "final_verifying");
    }
    if phase == "ship" {
        outcome = engine.step_with(&script, None, None).await.unwrap();
        assert_eq!(outcome.state, "awaiting_adjust_or_ship");
    }
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    let mut plan = store.read_plan().unwrap().unwrap();
    let seal = plan.frozen.clone();
    let marker = "printf tampered > src/seal-tamper-marker";
    plan.tests[0].command = marker.into();
    plan.full_suite = marker.into();
    store.write_plan(&plan).unwrap();
    assert_eq!(store.read_plan().unwrap().unwrap().frozen, seal);
    assert!(!plan.is_frozen().unwrap());
    let worktree = fixture.worktree();
    let head = fixture.head_sha(&worktree);
    let calls = script.calls().len();
    let publications = fixture.dir.path().join("pr-created");
    let published = std::fs::read(&publications).unwrap_or_default();
    if phase == "ship" {
        let ship = challenge_in(&outcome.message, "SHIP ");
        assert!(engine.ship(&format!("SHIP {ship}")).is_err());
        assert!(!fixture.was_marked_ready());
    } else {
        let rejected = engine.step_with(&script, None, None).await.unwrap();
        assert_eq!(rejected.state, "blocked", "{}", rejected.message);
    }
    assert!(
        !worktree.join("src/seal-tamper-marker").exists(),
        "tampered command ran"
    );
    assert_eq!(
        script.calls().len(),
        calls,
        "an agent ran against an unsealed plan"
    );
    assert_eq!(fixture.head_sha(&worktree), head);
    assert_eq!(std::fs::read(&publications).unwrap_or_default(), published);
}

#[tokio::test]
async fn frozen_plan_tampering_is_refused_before_coding() {
    assert_frozen_plan_tampering_is_refused("coding").await;
}

#[tokio::test]
async fn frozen_plan_tampering_is_refused_before_final_verification() {
    assert_frozen_plan_tampering_is_refused("final").await;
}

#[tokio::test]
async fn frozen_plan_tampering_is_refused_before_ship() {
    assert_frozen_plan_tampering_is_refused("ship").await;
}

#[tokio::test]
async fn changing_an_accepted_unit_rebuilds_its_unchanged_dependents() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;
    let old_head = fixture.head_sha(&fixture.worktree());
    let mut proposed: serde_json::Value = serde_json::from_str(&structure()).unwrap();
    proposed["requirements"][0]["statement"] =
        serde_json::json!("the generated file has revised contents");
    script.extend(vec![
        step(
            Role::Recommender,
            Reply::say(r#"{"decisions":[],"not_applicable":[]}"#),
        ),
        step(Role::PlanSynthesis, Reply::say(proposed.to_string())),
        step(Role::ColdConsumer, Reply::say(PASS)),
        step(Role::PlanCritic, Reply::say(PASS)),
        step(
            Role::Implementer,
            Reply::write(&[("src/added.txt", "revised\n")], DONE),
        ),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(
            Role::Implementer,
            Reply::write(&[("docs/added.md", "# revised\n")], DONE),
        ),
        step(Role::UnitReviewer, Reply::say(PASS)),
        step(Role::FinalReview, Reply::say(PASS)),
    ]);
    let engine = fixture.engine();
    engine
        .step_with(&script, None, Some("C1=ALT2"))
        .await
        .unwrap();
    assert_eq!(
        engine.step_with(&script, None, None).await.unwrap().state,
        "deciding"
    );
    assert_eq!(
        engine.step_with(&script, None, None).await.unwrap().state,
        "proving"
    );
    let preview = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(
        preview.state, "awaiting_confirmation",
        "{}",
        preview.message
    );
    let challenge = challenge_in(&preview.message, "CONFIRM PLAN ");
    let mut outcome = engine
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    let store = hwahap::state::Store::open(&fixture.repo).unwrap();
    assert!(
        store.read_run().unwrap().unwrap().accepted_units.is_empty(),
        "U2 depends on changed U1 and must lose acceptance"
    );
    while outcome.next == "continue" {
        outcome = engine.step_with(&script, None, None).await.unwrap();
    }
    assert_eq!(
        outcome.state, "awaiting_adjust_or_ship",
        "{}",
        outcome.message
    );
    assert_eq!(
        git(&fixture.worktree(), &["show", "HEAD:src/added.txt"]),
        "revised"
    );
    assert_eq!(
        git(&fixture.worktree(), &["show", "HEAD:docs/added.md"]),
        "# revised"
    );
    assert_eq!(
        git(
            &fixture.worktree(),
            &["rev-list", "--count", &format!("{old_head}..HEAD")]
        ),
        "2"
    );
    assert_eq!(
        script
            .calls()
            .iter()
            .filter(|c| c.role == Role::Implementer)
            .map(|c| c.unit.clone().unwrap())
            .collect::<Vec<_>>(),
        vec!["U1", "U2", "U1", "U2"]
    );
    assert_eq!(script.remaining(), 0);
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

// ------------------------------------------------- regressions from the adversarial review
//
// Each of these was proven by an independent reviewer as a test that failed on the code as
// shipped, and upheld by a second agent whose job was to refute it. They are grouped here so the
// defect each one guards stays visible.

#[tokio::test]
async fn a_reviewer_that_rewrites_a_file_it_reviewed_has_its_verdict_discarded() {
    // The guard used to compare the set of changed path *names*. A reviewer rewriting a file the
    // implementer already changed leaves that set identical, so its verdict was kept and its text
    // was committed as the unit's work.
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps[6] = step(
        Role::UnitReviewer,
        Reply::write(&[("src/added.txt", "the reviewer wrote this\n")], PASS),
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
    assert_eq!(rework.len(), 1, "the tree-changing reviewer was believed");
    assert!(
        rework[0].contains("changed the working tree"),
        "{}",
        rework[0]
    );

    let committed = git(&fixture.worktree(), &["show", "HEAD~1:src/added.txt"]);
    assert_eq!(
        committed, "generated",
        "the reviewer's edit was committed as the unit's work"
    );
}

#[tokio::test]
async fn an_adjustment_is_written_into_the_plan_and_reaches_the_next_planner() {
    // It used to be echoed back and dropped: no agent ever saw it, nothing was rebuilt, and the
    // next cycle offered the identical pull request to ship.
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;
    let engine = fixture.engine();

    engine
        .step_with(
            &script,
            None,
            Some("the documentation must mention --dry-run"),
        )
        .await
        .unwrap();

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    let adjustments = plan["adjustments"].as_array().expect("adjustments");
    assert_eq!(adjustments.len(), 1, "{plan:#}");
    assert_eq!(
        adjustments[0]["text"], "the documentation must mention --dry-run",
        "the feedback was not recorded"
    );
    assert_eq!(adjustments[0]["revision"], 2);

    // And the planner is handed it on the next round.
    script.extend(vec![step(Role::Recommender, Reply::say(decisions()))]);
    let _ = engine.step_with(&script, None, None).await;
    let asked = script.prompts_for(Role::Recommender);
    assert!(
        asked.iter().any(|p| p.contains("--dry-run")),
        "no Recommender prompt carried the adjustment: {asked:#?}"
    );
}

#[tokio::test]
async fn an_answer_given_at_the_ship_gate_is_recorded_rather_than_treated_as_prose() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;

    fixture
        .engine()
        .step_with(&script, None, Some("C1=ALT2\nand say why in the docs"))
        .await
        .unwrap();

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(plan["decisions"][0]["answer"]["text"], "C1=ALT2");
    assert_eq!(
        plan["adjustments"][0]["text"], "and say why in the docs",
        "the prose beside the answer was lost"
    );
}

#[tokio::test]
async fn a_plan_conflict_can_be_answered_instead_of_stranding_the_run() {
    // PlanConflict used to have no transition out of it at all: answers were ignored, a new
    // request was refused, and the only exit was deleting .hwahap by hand.
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
    let conflicted = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(conflicted.state, "plan_conflict");

    let answered = engine
        .step_with(&script, None, Some("C1=ALT2\nthe API is async"))
        .await
        .unwrap();
    assert_eq!(answered.state, "inspecting", "{}", answered.message);

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(plan["decisions"][0]["answer"]["text"], "C1=ALT2");
    assert_eq!(plan["revision"], 2);
    assert!(
        plan["frozen"].is_null(),
        "the conflicting plan is still frozen"
    );
}

#[tokio::test]
async fn a_second_run_in_the_same_repository_can_be_frozen() {
    // Nothing ever removed the run worktree, so `add_worktree` refused the path and every retry of
    // the second run failed identically.
    let fixture = Fixture::new();
    let first = Script::new(happy_path_steps());
    let outcomes = run_to_draft_pr(&fixture, &first).await;
    let challenge = challenge_in(&outcomes.last().expect("outcome").message, "SHIP ");
    fixture.engine().ship(&format!("SHIP {challenge}")).unwrap();

    let second = Script::new(happy_path_steps());
    let engine = fixture.engine();
    engine
        .step_with(&second, Some("Rename the widget module"), None)
        .await
        .unwrap();
    engine.step_with(&second, None, None).await.unwrap();
    engine
        .step_with(&second, None, Some(&all_answers()))
        .await
        .unwrap();
    let proved = engine.step_with(&second, None, None).await.unwrap();
    let challenge = challenge_in(&proved.message, "CONFIRM PLAN ");

    let frozen = engine
        .step_with(&second, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .expect("the second run must be freezable");
    assert_eq!(frozen.state, "coding", "{}", frozen.message);
}

#[tokio::test]
async fn an_answer_sent_with_a_confirmation_wins_and_the_confirmation_is_refused() {
    // Both arrive in one message when a user changes their mind and confirms in one breath. The
    // challenge describes the plan as it was a moment ago, so honouring it would freeze the very
    // content the user just replaced.
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps.truncate(5);
    steps.push(step(Role::ColdConsumer, Reply::say(PASS)));
    steps.push(step(Role::PlanCritic, Reply::say(PASS)));
    let script = Script::new(steps);

    let challenge = plan_to_confirmation(&fixture, &script).await;
    let engine = fixture.engine();
    let outcome = engine
        .step_with(
            &script,
            None,
            Some(&format!("C1=ALT2\nCONFIRM PLAN {challenge}")),
        )
        .await
        .unwrap();

    assert_eq!(outcome.state, "deciding", "{}", outcome.message);
    assert!(!fixture.worktree().exists(), "the plan was frozen anyway");

    let plan: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string(fixture.repo.join(".hwahap/plan.json")).unwrap(),
    )
    .unwrap();
    assert_eq!(plan["decisions"][0]["answer"]["text"], "C1=ALT2");
    assert!(plan["frozen"].is_null());
}

#[tokio::test]
async fn rec_is_refused_on_a_decision_that_recommends_nothing() {
    // C2 carries `no_recommendation`. Recorded blindly, `C2=REC` counted as answered, resolved to
    // nothing, and froze a plan whose unit briefs never mentioned the decision.
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps.truncate(2);
    let script = Script::new(steps);
    let engine = fixture.engine();

    engine
        .step_with(&script, Some(REQUEST), None)
        .await
        .unwrap();
    engine.step_with(&script, None, None).await.unwrap();

    let err = engine
        .step_with(&script, None, Some("C2=REC"))
        .await
        .unwrap_err()
        .to_string();
    assert!(err.contains("no recommendation to take"), "{err}");
    assert!(err.contains("C2=OTHER"), "{err}");
}

#[tokio::test]
async fn a_subdirectory_addresses_the_same_run_rather_than_starting_a_second_one() {
    // The store used to be rooted at whatever path the caller passed, so a host whose user sat in
    // a package directory silently started a second run in one repository.
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    fixture
        .engine()
        .step_with(&script, Some(REQUEST), None)
        .await
        .unwrap();

    let nested = hwahap::engine::Engine::open(&fixture.repo.join("src"))
        .unwrap()
        .with_parts(
            Box::new(hwahap::clock::FixedClock::new(NOW)),
            hwahap::forge::Forge::with_program(fixture.gh.to_str().unwrap()),
        );
    assert_eq!(nested.status().unwrap().state, "inspecting");
    assert!(!fixture.repo.join("src/.hwahap").exists());
}

#[tokio::test]
async fn status_on_an_untouched_repository_writes_nothing_at_all() {
    // The tool is annotated read-only and its description says it changes nothing.
    let fixture = Fixture::new();
    let before = git(
        &fixture.repo,
        &["status", "--porcelain", "--untracked-files=all"],
    );
    assert_eq!(fixture.engine().status().unwrap().state, "no_run");
    assert!(
        !fixture.repo.join(".hwahap").exists(),
        ".hwahap was created"
    );
    assert_eq!(
        git(
            &fixture.repo,
            &["status", "--porcelain", "--untracked-files=all"]
        ),
        before
    );
}

#[tokio::test]
async fn every_session_leaves_its_own_receipt() {
    // Receipts used to be named from the role and the clock, so two sessions of one role inside a
    // second overwrote each other and the profile evidence for the run was incomplete.
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    run_to_draft_pr(&fixture, &script).await;

    let receipts = std::fs::read_dir(fixture.repo.join(".hwahap/artifacts"))
        .unwrap()
        .filter_map(|e| e.ok())
        .map(|e| e.file_name().to_string_lossy().to_string())
        .filter(|name| name.starts_with("receipt-"))
        .count();
    assert_eq!(
        receipts,
        script.calls().len(),
        "one receipt per session, and there were {} sessions",
        script.calls().len()
    );
}

#[tokio::test]
async fn a_final_reviewer_that_writes_cannot_create_a_draft_pr() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    steps.last_mut().unwrap().reply =
        Reply::write(&[("src/added.txt", "reviewer changed this\n")], PASS);
    let script = Script::new(steps);
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let outcome = outcomes.last().unwrap();
    assert_eq!(outcome.state, "blocked");
    assert!(outcome.message.contains("final_review"));
    assert!(outcome.pr_url.is_none());
}

#[tokio::test]
async fn receipts_survive_a_new_engine_for_every_mcp_step() {
    let fixture = Fixture::new();
    let script = Script::new(happy_path_steps());
    let challenge = plan_to_confirmation(&fixture, &script).await;
    let mut outcome = fixture
        .engine()
        .step_with(&script, None, Some(&format!("CONFIRM PLAN {challenge}")))
        .await
        .unwrap();
    while outcome.next == "continue" {
        outcome = fixture
            .engine()
            .step_with(&script, None, None)
            .await
            .unwrap();
    }
    let receipts = std::fs::read_dir(fixture.repo.join(".hwahap/artifacts"))
        .unwrap()
        .filter_map(|e| e.ok())
        .filter(|e| e.file_name().to_string_lossy().starts_with("receipt-"))
        .count();
    assert_eq!(receipts, script.calls().len());
}

#[tokio::test]
async fn a_successful_full_suite_that_mutates_files_cannot_publish() {
    let fixture = Fixture::new();
    let mut steps = happy_path_steps();
    let mut proposal: serde_json::Value = serde_json::from_str(&structure()).unwrap();
    proposal["full_suite"] = "printf changed > src/added.txt".into();
    steps[2].reply = Reply::say(proposal.to_string());
    let script = Script::new(steps);
    let outcomes = run_to_draft_pr(&fixture, &script).await;
    let outcome = outcomes.last().unwrap();
    assert_eq!(outcome.state, "blocked");
    assert!(outcome.message.contains("full suite changed"));
    assert!(outcome.pr_url.is_none());
    assert!(!script.roles().contains(&Role::FinalReview));
}
