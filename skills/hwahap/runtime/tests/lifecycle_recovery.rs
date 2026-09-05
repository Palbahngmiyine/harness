#![cfg(unix)]
mod common;
use common::Fixture;
use hwahap::native::{NativeHost, NativeInput};
use hwahap::state::Store;

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
