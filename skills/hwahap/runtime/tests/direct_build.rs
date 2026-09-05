#![cfg(unix)]
mod common;

use common::{git, step, Fixture, Reply, Script};
use hwahap::engine::{BuildRequest, BuildUnit};
use hwahap::profile::Role;
use hwahap::state::Store;

fn request() -> BuildRequest {
    BuildRequest {
        user_instruction: "기획 제외하고 구현해 줘".into(),
        objective: "Create a checked feature".into(),
        base_branch: "main".into(),
        branch: "codex/direct-build".into(),
        full_suite: "test -f feature.txt".into(),
        units: vec![BuildUnit {
            title: "Create feature".into(),
            acceptance: "feature.txt contains ready".into(),
            paths: vec!["feature.txt".into()],
            test_command: "test \"$(cat feature.txt)\" = ready".into(),
        }],
    }
}

#[test]
fn review_policy_requires_two_astra_lanes_and_keeps_authorship_separate() {
    use hwahap::native::NativeLane;
    use hwahap::profile::Profiles;
    Profiles::defaults().require_astra_reviewers().unwrap();
    assert_eq!(NativeLane::for_role(Role::UnitReviewer), NativeLane::Critic);
    assert_eq!(NativeLane::for_role(Role::FinalReview), NativeLane::Auditor);
    assert_eq!(NativeLane::for_role(Role::Rework), NativeLane::Coordinator);
    let custom = "[profiles.economy]\nmodel='gpt-5.6-luna'\neffort='medium'\n[profiles.critic]\nmodel='gpt-5.6-terra'\neffort='high'\n[profiles.deep]\nmodel='gpt-6-astra'\neffort='high'";
    assert!(Profiles::from_toml(custom)
        .unwrap()
        .require_astra_reviewers()
        .is_err());
}

#[tokio::test]
async fn direct_build_reaches_a_real_commit_and_draft_without_planning() {
    let fixture = Fixture::new();
    git(
        &fixture.repo,
        &["update-ref", "refs/remotes/origin/main", "HEAD"],
    );
    let input = request();
    let engine = fixture.engine();
    let outcome = engine.start_build(&input).unwrap();
    assert_eq!(
        (outcome.phase.as_str(), outcome.state.as_str()),
        ("build", "coding")
    );
    assert!(engine.start_build(&input).is_err());
    let store = Store::open(&fixture.repo).unwrap();
    let plan = store.read_plan().unwrap().unwrap();
    assert_eq!(
        plan.frozen.as_ref().unwrap().answer_text,
        input.user_instruction
    );
    assert!(plan.decisions.is_empty() && plan.reviews.critic.is_none());
    let script = Script::new(vec![
        step(
            Role::Implementer,
            Reply::write(
                &[("feature.txt", "ready")],
                r#"{"status":"completed","summary":"Created feature","conflict":null}"#,
            ),
        ),
        step(
            Role::UnitReviewer,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    let next = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(next.state, "final_verifying", "{}", next.message);
    let done = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(done.state, "pr_review", "{}", done.message);
    assert_eq!(done.next, "continue");
    let progress = hwahap::pr_review::ReviewProgress::load(&store)
        .unwrap()
        .unwrap();
    assert_eq!(
        progress.binding.head,
        git(&fixture.worktree(), &["rev-parse", "HEAD"])
    );
    assert_eq!(progress.binding.contract_digest, plan.digest().unwrap());
    assert_eq!(progress.stage, hwahap::pr_review::ReviewStage::Attack);
    assert!(engine.ship("SHIP anything").is_err());
    let binding = progress.binding;
    let reviews = Script::new(vec![
        step(Role::UnitReviewer, Reply::say(serde_json::json!({"binding":binding,"findings":[],"evidence":["checked published feature"]}).to_string())),
        step(Role::FinalReview, Reply::say(serde_json::json!({"binding":binding,"assessments":[],"additional_findings":[],"evidence":["independently checked published feature"]}).to_string())),
    ]);
    let reviewed = engine.step_with(&reviews, None, None).await.unwrap();
    assert_eq!(
        reviewed.state, "awaiting_adjust_or_ship",
        "{}",
        reviewed.message
    );
    assert_eq!(reviews.remaining(), 0);
    assert_eq!(
        hwahap::pr_review::ReviewProgress::load(&store)
            .unwrap()
            .unwrap()
            .stage,
        hwahap::pr_review::ReviewStage::Complete
    );
    assert_eq!(script.remaining(), 0);
    assert!(git(&fixture.worktree(), &["log", "-1", "--format=%s"]).contains("U1"));
    assert!(done.pr_url.is_some());
}

#[test]
fn invalid_build_cannot_create_a_worktree_or_execute_commands() {
    let fixture = Fixture::new();
    git(
        &fixture.repo,
        &["update-ref", "refs/remotes/origin/main", "HEAD"],
    );
    let mut input = request();
    input.units[0].paths = vec!["../escape".into()];
    assert!(fixture.engine().start_build(&input).is_err());
    assert!(!fixture.worktree().exists());
    assert!(Store::open(&fixture.repo)
        .unwrap()
        .read_run()
        .unwrap()
        .is_none());
}

#[tokio::test]
async fn native_direct_build_dispatches_authorship_to_the_parent_astra() {
    let fixture = Fixture::new();
    git(
        &fixture.repo,
        &["update-ref", "refs/remotes/origin/main", "HEAD"],
    );
    fixture.engine().start_build(&request()).unwrap();
    let store = Store::open(&fixture.repo).unwrap();
    let config = hwahap::config::Config::for_run(&store).unwrap();
    for role in [Role::Implementer, Role::UnitReviewer, Role::FinalReview] {
        assert_eq!(config.profiles.for_role(role).model, "gpt-6-astra");
    }
    let host = hwahap::native::NativeHost::default();
    let root = fixture.repo.canonicalize().unwrap();
    let dispatch = tokio::time::timeout(std::time::Duration::from_secs(5), async {
        loop {
            let progress = host
                .advance(
                    &root,
                    hwahap::native::NativeInput {
                        host_session_id: Some("direct-owner".into()),
                        ..Default::default()
                    },
                )
                .await
                .unwrap();
            if let Some(dispatch) = progress.dispatch {
                break dispatch;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    assert!(dispatch.coordinator_allowed);
    assert_eq!(dispatch.lane, hwahap::native::NativeLane::Coordinator);
    assert_eq!(dispatch.model, "gpt-6-astra");
    assert!(dispatch.reuse_agent_id.is_none());
    host.shutdown().await;
}
