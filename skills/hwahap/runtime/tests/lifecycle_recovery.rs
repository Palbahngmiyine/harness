#![cfg(unix)]
mod common;
use common::Fixture;
use hwahap::native::{NativeHost, NativeInput};
use hwahap::state::Store;
#[path = "lifecycle_recovery/plan_fixture.rs"]
mod plan_fixture;

#[tokio::test]
async fn first_plan_call_seals_its_parent_before_a_restart_or_another_dispatch() {
    let f = Fixture::new();
    let store = Store::open(&f.repo).unwrap();
    let host = NativeHost::default();
    host.advance(
        &f.repo,
        NativeInput {
            request: Some("Plan a repository change".into()),
            plan_only: true,
            host_session_id: Some("original-parent".into()),
            ..Default::default()
        },
    )
    .await
    .unwrap();
    tokio::time::timeout(std::time::Duration::from_secs(2), async {
        while store.read_run().unwrap().is_none() {
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap();
    host.shutdown().await;
    let owner = store.artifacts_path().join("native-owner.json");
    let bytes = std::fs::read(&owner).unwrap();
    let saved: serde_json::Value = serde_json::from_slice(&bytes).unwrap();
    assert_eq!(saved["pool_scope"], "original-parent");
    let replacement = NativeHost::default();
    for parent in [None, Some("different-parent".into())] {
        assert!(replacement
            .advance(
                &f.repo,
                NativeInput {
                    host_session_id: parent,
                    ..Default::default()
                }
            )
            .await
            .is_err());
        assert_eq!(std::fs::read(&owner).unwrap(), bytes);
    }
}

#[tokio::test]
async fn interrupted_worktree_is_checked_before_adoption_and_cannot_discard_dirty_files() {
    let f = Fixture::new();
    let ready = plan_fixture::plan_ready(&f).await;
    let branch = format!("hwahap/{}", ready.run_id);
    common::git(
        &f.repo,
        &[
            "worktree",
            "add",
            "-b",
            &branch,
            f.worktree().to_str().unwrap(),
            "HEAD",
        ],
    );
    let path = f.worktree().join("user-owned.txt");
    std::fs::write(&path, "preserve").unwrap();
    let engine = f.engine();
    assert!(engine
        .build_confirmed(ready.plan_digest.as_ref().unwrap())
        .is_err());
    assert_eq!(engine.status().unwrap().state, "plan_ready");
    assert_eq!(std::fs::read_to_string(&path).unwrap(), "preserve");
    std::fs::remove_file(path).unwrap();
    assert_eq!(
        engine
            .build_confirmed(ready.plan_digest.as_ref().unwrap())
            .unwrap()
            .state,
        "coding"
    );
}
