#![cfg(unix)]
mod common;

use common::{git, step, Fixture, Reply, Script};
use hwahap::{
    approval::{ApprovedPlanRequest, PlanApproval},
    canonical::Digest,
    engine::{BuildRequest, BuildUnit},
    profile::Role,
    state::Store,
};

fn request(f: &Fixture) -> ApprovedPlanRequest {
    git(&f.repo, &["update-ref", "refs/remotes/origin/main", "HEAD"]);
    let markdown = "# Plan\nCreate feature.txt containing ready. Preserve all other files.";
    let instruction = format!("PLEASE IMPLEMENT THIS PLAN:\n{markdown}");
    ApprovedPlanRequest {
        approval: PlanApproval {
            markdown: markdown.into(),
            markdown_digest: Digest::of_bytes(markdown.as_bytes()).to_string(),
            implementation_request: instruction.clone(),
            source_head: git(&f.repo, &["rev-parse", "HEAD"]),
        },
        contract: BuildRequest {
            user_instruction: instruction,
            objective: "Create feature".into(),
            base_branch: "main".into(),
            branch: "codex/approved-plan".into(),
            full_suite: "test -f feature.txt".into(),
            units: vec![BuildUnit {
                title: "Create feature".into(),
                acceptance: "feature.txt contains ready; other files unchanged".into(),
                paths: vec!["feature.txt".into()],
                test_command: "test \"$(cat feature.txt)\" = ready".into(),
            }],
        },
        replaces_plan_digest: None,
    }
}

#[tokio::test]
async fn approved_plan_replaces_only_the_named_draft_then_builds_without_reapproval() {
    let f = Fixture::new();
    let mut input = request(&f);
    let engine = f.engine();
    engine
        .start_planning("Unfinished interview", false)
        .unwrap();
    let store = Store::open(&f.repo).unwrap();
    let draft = store.read_plan().unwrap().unwrap();
    assert!(engine.register_approved_plan(&input).is_err());
    assert_eq!(store.read_plan().unwrap().unwrap(), draft);
    input.replaces_plan_digest = Some(draft.digest().unwrap().to_string());
    assert_eq!(
        engine.register_approved_plan(&input).unwrap().state,
        "proving"
    );
    let events = store.read_events().unwrap().len();
    engine.register_approved_plan(&input).unwrap();
    assert_eq!(store.read_events().unwrap().len(), events);
    assert!(!f.worktree().exists());
    let script = Script::new(vec![
        step(
            Role::ColdConsumer,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
        step(
            Role::PlanCritic,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    assert_eq!(
        engine.step_with(&script, None, None).await.unwrap().state,
        "coding"
    );
    assert_eq!(script.roles(), vec![Role::ColdConsumer, Role::PlanCritic]);
    let plan = store.read_plan().unwrap().unwrap();
    assert_eq!(
        plan.frozen.unwrap().answer_text,
        input.approval.implementation_request
    );
    assert!(plan.decisions.is_empty());
    assert_eq!(
        git(&f.worktree(), &["branch", "--show-current"]),
        input.contract.branch
    );
    engine.register_approved_plan(&input).unwrap();
    let history = store.read_events().unwrap();
    assert!(history
        .iter()
        .any(|e| e.data["previous_plan"] == serde_json::json!(draft)));
    assert!(engine.ship("SHIP anything").is_err());
}

#[tokio::test]
async fn rejected_translation_retains_approval_without_creating_a_worktree() {
    let f = Fixture::new();
    let input = request(&f);
    let engine = f.engine();
    engine.register_approved_plan(&input).unwrap();
    let script = Script::new(vec![
        step(
            Role::ColdConsumer,
            Reply::say(
                r#"{"verdict":"fail","findings":["A missing condition needs contract repair"]}"#,
            ),
        ),
        step(
            Role::PlanCritic,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    let result = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(result.state, "plan_conflict");
    let plan = Store::open(&f.repo).unwrap().read_plan().unwrap().unwrap();
    assert_eq!(plan.approved_plan.as_ref(), Some(&input.approval));
    assert!(plan.frozen.is_none());
    assert!(!f.worktree().exists());
}

#[tokio::test]
async fn import_parent_survives_missing_owner_and_run_snapshots() {
    use hwahap::native::{NativeHost, NativeInput};
    let f = Fixture::new();
    let input = request(&f);
    f.engine()
        .register_approved_plan_for_parent(&input, Some("original-parent"))
        .unwrap();
    let store = Store::open(&f.repo).unwrap();
    // Crash after journaling approval but before the run/owner snapshots are written.
    std::fs::remove_file(f.repo.join(".hwahap/run.json")).unwrap();
    let host = NativeHost::default();
    let error = host
        .advance(
            &f.repo,
            NativeInput {
                host_session_id: Some("different-parent".into()),
                approved_plan: Some(input.clone()),
                ..Default::default()
            },
        )
        .await
        .err()
        .unwrap();
    assert!(error.to_string().contains("another parent"), "{error}");
    assert!(!store.artifacts_path().join("native-owner.json").exists());
    let result = host
        .advance(
            &f.repo,
            NativeInput {
                host_session_id: Some("original-parent".into()),
                approved_plan: Some(input),
                ..Default::default()
            },
        )
        .await
        .unwrap();
    assert_eq!(result.outcome.state, "proving");
    assert!(!f.worktree().exists());
}

#[tokio::test]
async fn translation_repair_keeps_approval_and_exposes_all_execution_fields_to_review() {
    let f = Fixture::new();
    let mut input = request(&f);
    let engine = f.engine();
    engine.register_approved_plan(&input).unwrap();
    let script = Script::new(vec![
        step(
            Role::ColdConsumer,
            Reply::say(r#"{"verdict":"fail","findings":["Test must reject incorrect content"]}"#),
        ),
        step(
            Role::PlanCritic,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    engine.step_with(&script, None, None).await.unwrap();
    for call in script.calls() {
        assert!(call.prompt.contains(&format!(
            "\"full_suite\": \"{}\"",
            input.contract.full_suite
        )));
        assert!(call.prompt.contains("\"base_commit\":"));
        assert!(call
            .prompt
            .contains("\"execution_branch\": \"codex/approved-plan\""));
    }
    let store = Store::open(&f.repo).unwrap();
    let before = store.read_plan().unwrap().unwrap();
    assert!(engine
        .step_with(&script, None, Some("fix the translation"))
        .await
        .is_err());
    assert_eq!(store.read_plan().unwrap().unwrap(), before);
    input.replaces_plan_digest = Some(before.digest().unwrap().to_string());
    input.contract.full_suite = input.contract.units[0].test_command.clone();
    engine.register_approved_plan(&input).unwrap();
    let repaired = store.read_plan().unwrap().unwrap();
    assert_eq!(repaired.approved_plan, before.approved_plan);
    assert!(repaired.reviews.cold_consumer.is_none());
    assert_eq!(repaired.revision, before.revision + 1);
}

#[tokio::test]
async fn interrupted_build_start_resumes_without_another_approval_or_duplicate_review() {
    let f = Fixture::new();
    let input = request(&f);
    let engine = f.engine();
    let gh = std::fs::read(&f.gh).unwrap();
    std::fs::write(&f.gh, "#!/bin/sh\nexit 1\n").unwrap();
    engine.register_approved_plan(&input).unwrap();
    let script = Script::new(vec![
        step(
            Role::ColdConsumer,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
        step(
            Role::PlanCritic,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    assert!(engine.step_with(&script, None, None).await.is_err());
    let status = engine.status().unwrap();
    assert_eq!(status.state, "plan_ready");
    assert_eq!(status.next, "continue");
    assert!(!status.message.contains("Request BUILD"));
    assert!(!f.worktree().exists());
    std::fs::write(&f.gh, gh).unwrap();
    let resumed = f.engine().step_with(&script, None, None).await.unwrap();
    assert_eq!(resumed.state, "coding");
    assert_eq!(script.calls().len(), 2);
    assert_eq!(
        engine.register_approved_plan(&input).unwrap().state,
        "coding"
    );
}
