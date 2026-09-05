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
        step(
            Role::FinalReview,
            Reply::say(r#"{"verdict":"pass","findings":[]}"#),
        ),
    ]);
    let next = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(next.state, "final_verifying", "{}", next.message);
    let done = engine.step_with(&script, None, None).await.unwrap();
    assert_eq!(done.state, "awaiting_adjust_or_ship", "{}", done.message);
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
