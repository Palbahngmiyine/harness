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
