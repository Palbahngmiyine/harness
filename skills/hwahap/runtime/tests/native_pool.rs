//! A controlled host never releases its three child slots; all later work must reuse them.
#![cfg(unix)]
mod common;

use std::collections::{BTreeMap, BTreeSet};
use std::sync::Arc;

use common::Fixture;
use hwahap::native::{
    NativeCompletion, NativeDispatch, NativeLane, NativeRegistration, NativeSessions,
};
use hwahap::profile::{Profiles, Role};
use hwahap::session::SessionSpec;
use hwahap::state::Store;

async fn pending(broker: &NativeSessions) -> NativeDispatch {
    tokio::time::timeout(std::time::Duration::from_secs(5), async {
        loop {
            if let Some(dispatch) = broker.dispatch().unwrap() {
                break dispatch;
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap()
}

#[tokio::test]
async fn three_occupied_child_slots_complete_three_hundred_jobs_without_replacement_spawns() {
    let fixture = Fixture::new();
    fixture
        .engine()
        .step(Some("Inspect this repository"), None)
        .await
        .unwrap();
    let mut occupied = BTreeMap::new();
    let mut dispatch_ids = BTreeSet::new();
    let (mut spawns, mut followups) = (0, 0);
    let mut pool_scope = None;
    for unit in 1..=100 {
        for (role, lane, label, model) in [
            (
                Role::FactFinder,
                NativeLane::Worker,
                "worker",
                "gpt-5.6-luna",
            ),
            (
                Role::UnitReviewer,
                NativeLane::Critic,
                "critic",
                "gpt-5.6-terra",
            ),
            (
                Role::FinalReview,
                NativeLane::Auditor,
                "auditor",
                "gpt-6-astra",
            ),
        ] {
            // Recreate the broker for every job so in-memory reuse cannot satisfy this test.
            let broker = Arc::new(
                NativeSessions::new(
                    Store::open(&fixture.repo).unwrap(),
                    Profiles::defaults(),
                    1000,
                    30,
                )
                .with_host_session_id("controlled-parent-task".to_string()),
            );
            let spec = SessionSpec {
                cwd: fixture.repo.clone(),
                role,
                unit: Some(format!("U{unit}")),
                prompt: format!("Perform {label} job for U{unit}"),
            };
            let worker = broker.clone();
            let task = tokio::spawn(async move { worker.execute(&spec).await });
            let request = pending(&broker).await;
            assert!(dispatch_ids.insert(request.dispatch_id.clone()));
            assert_eq!(request.lane, lane);
            assert_eq!(request.model, model);
            assert!(!request.pool_scope.is_empty());
            assert_eq!(
                pool_scope.get_or_insert(request.pool_scope.clone()),
                &request.pool_scope
            );
            assert!(
                request.agent_id.is_none(),
                "each job needs explicit registration"
            );
            let agent_id = match &request.reuse_agent_id {
                Some(id) => {
                    assert_eq!(occupied.get(label), Some(id));
                    followups += 1;
                    id.clone()
                }
                None => {
                    assert!(
                        occupied.len() < 3,
                        "controlled host has no fourth thread slot"
                    );
                    assert!(!occupied.contains_key(label));
                    let id = format!("controlled-{label}");
                    occupied.insert(label, id.clone());
                    spawns += 1;
                    id
                }
            };
            broker
                .register(&NativeRegistration {
                    dispatch_id: request.dispatch_id.clone(),
                    agent_id: agent_id.clone(),
                })
                .unwrap();
            let result = serde_json::json!({"unit":unit,"role":label,"verdict":"pass"});
            let final_message = if request.reuse_agent_id.is_some() {
                serde_json::json!({"dispatch_id":request.dispatch_id,"result":result}).to_string()
            } else {
                result.to_string() // Fresh children retain compatibility with the original wire format.
            };
            broker
                .complete(NativeCompletion {
                    dispatch_id: request.dispatch_id,
                    agent_id,
                    final_message,
                    agent_stopped: true,
                    reported_usage: None,
                })
                .unwrap();
            let outcome = task.await.unwrap().unwrap();
            assert_eq!(
                outcome.final_message,
                result.to_string(),
                "the envelope must be unwrapped exactly"
            );
            broker.finish().unwrap();
        }
    }
    assert_eq!(occupied.len(), 3);
    assert_eq!(spawns, 3);
    assert_eq!(followups, 297);
    assert_eq!(dispatch_ids.len(), 300);
    assert_eq!(occupied.values().collect::<BTreeSet<_>>().len(), 3);
    let artifacts = Store::open(&fixture.repo).unwrap().artifacts_path();
    let count = artifacts
        .read_dir()
        .unwrap()
        .filter(|e| {
            e.as_ref()
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("native-completion-")
        })
        .count();
    assert_eq!(
        count, 300,
        "every job must have durable completion evidence"
    );
}
