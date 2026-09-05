//! Real Git and durable storage with a controlled host; no model access is implied.
#![cfg(unix)]

use std::sync::Arc;
use std::time::Duration;

use hwahap::engine::Engine;
use hwahap::native::{
    acknowledge_stopped, orphan, NativeCompletion, NativeDispatch, NativeRegistration,
    NativeSessions, NativeStopped,
};
use hwahap::profile::{Profiles, Role};
use hwahap::session::SessionSpec;
use hwahap::state::Store;

async fn fixture(
    max_calls: u64,
    timeout: u64,
) -> (tempfile::TempDir, Arc<NativeSessions>, SessionSpec) {
    let temp = tempfile::tempdir().unwrap();
    for args in [
        vec!["init", "-b", "main"],
        vec!["config", "user.email", "test@example.invalid"],
        vec!["config", "user.name", "Native Test"],
        vec!["commit", "--allow-empty", "-m", "seed"],
    ] {
        let output = std::process::Command::new("git")
            .args(args)
            .current_dir(temp.path())
            .output()
            .unwrap();
        assert!(
            output.status.success(),
            "{}",
            String::from_utf8_lossy(&output.stderr)
        );
    }
    Engine::open(temp.path())
        .unwrap()
        .step(Some("Inspect this repository"), None)
        .await
        .unwrap();
    let broker = Arc::new(NativeSessions::new(
        Store::open(temp.path()).unwrap(),
        Profiles::defaults(),
        max_calls,
        timeout,
    ));
    let spec = SessionSpec {
        cwd: temp.path().into(),
        role: Role::FactFinder,
        unit: None,
        prompt: "Return facts".into(),
    };
    (temp, broker, spec)
}

async fn dispatch(broker: &NativeSessions) -> NativeDispatch {
    tokio::time::timeout(Duration::from_secs(5), async {
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
async fn registered_result_is_durable_bound_and_consumed_once() {
    let (temp, broker, spec) = fixture(1, 30).await;
    let worker = broker.clone();
    let task = tokio::spawn(async move { worker.execute(&spec).await });
    let request = dispatch(&broker).await;
    let store = Store::open(temp.path()).unwrap();
    assert!(orphan(&store).unwrap().unwrap().stop_required);
    assert!(request
        .brief
        .contains("without inherited conversation history"));
    assert!(!request.base_head.is_empty());
    let mut completion = NativeCompletion {
        dispatch_id: request.dispatch_id.clone(),
        agent_id: "child-1".into(),
        final_message: "facts".into(),
        agent_stopped: true,
        reported_usage: None,
    };
    assert!(
        broker.complete(completion.clone()).is_err(),
        "unregistered agent accepted"
    );
    broker
        .register(&NativeRegistration {
            dispatch_id: request.dispatch_id.clone(),
            agent_id: "child-1".into(),
        })
        .unwrap();
    completion.agent_id = "other-child".into();
    assert!(broker.complete(completion.clone()).is_err());
    completion.agent_id = "child-1".into();
    broker.complete(completion.clone()).unwrap();
    broker.complete(completion.clone()).unwrap();
    completion.final_message = "changed".into();
    assert!(broker.complete(completion).is_err());
    let outcome = task.await.unwrap().unwrap();
    assert_eq!(outcome.final_message, "facts");
    assert!(store
        .artifacts_path()
        .join(format!("native-completion-{}.json", request.dispatch_id))
        .exists());
    broker.finish().unwrap();
    assert!(orphan(&store).unwrap().is_none());
    let spec = SessionSpec {
        cwd: temp.path().into(),
        role: Role::FactFinder,
        unit: None,
        prompt: "again".into(),
    };
    assert!(broker
        .execute(&spec)
        .await
        .unwrap_err()
        .to_string()
        .contains("budget"));
}

#[tokio::test]
async fn restart_requires_exact_stop_acknowledgment_before_recovery() {
    let (temp, broker, spec) = fixture(5, 30).await;
    let worker = broker.clone();
    let task = tokio::spawn(async move { worker.execute(&spec).await });
    let request = dispatch(&broker).await;
    broker
        .register(&NativeRegistration {
            dispatch_id: request.dispatch_id.clone(),
            agent_id: "child-1".into(),
        })
        .unwrap();
    task.abort();
    let _ = task.await;
    let store = Store::open(temp.path()).unwrap();
    let orphan = orphan(&store).unwrap().unwrap();
    assert_eq!(orphan.agent_id.as_deref(), Some("child-1"));
    let mut ack = NativeStopped {
        dispatch_id: request.dispatch_id,
        agent_id: None,
        all_work_stopped: true,
    };
    assert!(acknowledge_stopped(&store, &ack).is_err());
    ack.agent_id = Some("child-1".into());
    ack.all_work_stopped = false;
    assert!(acknowledge_stopped(&store, &ack).is_err());
    ack.all_work_stopped = true;
    acknowledge_stopped(&store, &ack).unwrap();
    assert!(hwahap::native::orphan(&store).unwrap().is_none());
}

#[tokio::test]
async fn deadline_does_not_claim_the_child_was_stopped() {
    let (temp, broker, spec) = fixture(5, 0).await;
    assert!(broker
        .execute(&spec)
        .await
        .unwrap_err()
        .to_string()
        .contains("deadline"));
    assert!(broker.dispatch().unwrap().unwrap().stop_required);
    assert!(broker.finish().is_err());
    assert!(orphan(&Store::open(temp.path()).unwrap())
        .unwrap()
        .is_some());
}

#[tokio::test]
async fn coordinator_is_limited_to_astra_planning_roles() {
    let (_temp, broker, mut spec) = fixture(5, 30).await;
    spec.role = Role::Recommender;
    let worker = broker.clone();
    let task = tokio::spawn(async move { worker.execute(&spec).await });
    let request = dispatch(&broker).await;
    assert!(request.coordinator_allowed);
    broker
        .register(&NativeRegistration {
            dispatch_id: request.dispatch_id.clone(),
            agent_id: "coordinator".into(),
        })
        .unwrap();
    broker
        .complete(NativeCompletion {
            dispatch_id: request.dispatch_id,
            agent_id: "coordinator".into(),
            final_message: "recommendations".into(),
            agent_stopped: true,
            reported_usage: None,
        })
        .unwrap();
    assert_eq!(
        task.await.unwrap().unwrap().final_message,
        "recommendations"
    );
    broker.finish().unwrap();
    let (_temp, broker, spec) = fixture(5, 30).await;
    let worker = broker.clone();
    let task = tokio::spawn(async move { worker.execute(&spec).await });
    let request = dispatch(&broker).await;
    assert!(!request.coordinator_allowed);
    assert!(broker
        .register(&NativeRegistration {
            dispatch_id: request.dispatch_id,
            agent_id: "coordinator".into()
        })
        .is_err());
    task.abort();
    let _ = task.await;
}

async fn host_dispatch(host: &hwahap::native::NativeHost, root: &std::path::Path) -> NativeDispatch {
    tokio::time::timeout(Duration::from_secs(5), async {
        loop {
            let result = host.advance(root, hwahap::native::NativeInput::default()).await.unwrap();
            if let Some(dispatch) = result.dispatch { break dispatch; }
            tokio::task::yield_now().await;
        }
    }).await.unwrap()
}

#[tokio::test]
async fn host_polling_preserves_one_dispatch_and_excludes_a_second_server() {
    use hwahap::native::{NativeHost, NativeInput};
    let (temp, _broker, _spec) = fixture(5, 30).await;
    let host = NativeHost::default();
    let request = host_dispatch(&host, temp.path()).await;
    let again = host.advance(temp.path(), NativeInput::default()).await.unwrap().dispatch.unwrap();
    assert_eq!(request.dispatch_id, again.dispatch_id);
    assert!(NativeHost::default().advance(temp.path(), NativeInput::default()).await.is_err());
    assert!(host.ship(temp.path(), "anything").await.is_err());
    assert!(host.advance(temp.path(), NativeInput { user_input: Some("change it".into()), ..Default::default() }).await.is_err());
    host.advance(temp.path(), NativeInput { registration: Some(NativeRegistration { dispatch_id: request.dispatch_id.clone(), agent_id: "native-1".into() }), ..Default::default() }).await.unwrap();
    assert_eq!(host.status(temp.path()).await.unwrap().outcome.next, "native_wait");
    drop(host);
    tokio::task::yield_now().await;
    let replacement = NativeHost::default();
    let result = replacement.advance(temp.path(), NativeInput::default()).await.unwrap();
    assert_eq!(result.outcome.next, "native_stop");
    assert_eq!(result.dispatch.unwrap().dispatch_id, request.dispatch_id);
    replacement.advance(temp.path(), NativeInput { stopped: Some(NativeStopped { dispatch_id: request.dispatch_id, agent_id: Some("native-1".into()), all_work_stopped: true }), ..Default::default() }).await.unwrap();
    assert!(orphan(&Store::open(temp.path()).unwrap()).unwrap().is_none());
}

#[tokio::test]
async fn host_consumes_registered_output_and_accepts_identical_replay() {
    use hwahap::native::{NativeHost, NativeInput};
    let (temp, _broker, _spec) = fixture(5, 30).await;
    let host = NativeHost::default();
    let request = host_dispatch(&host, temp.path()).await;
    host.advance(temp.path(), NativeInput { registration: Some(NativeRegistration { dispatch_id: request.dispatch_id.clone(), agent_id: "native-1".into() }), ..Default::default() }).await.unwrap();
    let completion = NativeCompletion { dispatch_id: request.dispatch_id, agent_id: "native-1".into(), final_message: r#"{"facts":[{"id":"F1","question":"what exists?","answer":"empty repository","sources":["git HEAD"]}]}"#.into(), agent_stopped: true, reported_usage: None };
    host.advance(temp.path(), NativeInput { completion: Some(completion.clone()), ..Default::default() }).await.unwrap();
    tokio::task::yield_now().await;
    host.advance(temp.path(), NativeInput { completion: Some(completion), ..Default::default() }).await.unwrap();
    let count = std::fs::read_dir(Store::open(temp.path()).unwrap().artifacts_path()).unwrap()
        .filter_map(|entry| entry.ok()).filter(|entry| entry.file_name().to_string_lossy().starts_with("native-completion-")).count();
    assert_eq!(count, 1);
}
