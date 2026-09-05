//! Capacity recovery uses durable native dispatches and real Git, without live models.
#![cfg(unix)]
mod common;

use common::{git, Fixture};
use hwahap::native::{NativeDispatch, NativeFailure, NativeHost, NativeInput, NativeResume};

async fn setup() -> (Fixture, NativeHost, NativeDispatch) {
    let fixture = Fixture::new();
    fixture
        .engine()
        .step(Some("Inspect this repository"), None)
        .await
        .unwrap();
    let host = NativeHost::default();
    let request = dispatch(&host, &fixture).await;
    (fixture, host, request)
}

async fn dispatch(host: &NativeHost, fixture: &Fixture) -> NativeDispatch {
    tokio::time::timeout(std::time::Duration::from_secs(5), async {
        loop {
            let progress = host
                .advance(&fixture.repo, NativeInput::default())
                .await
                .unwrap();
            if progress.outcome.next == "native_dispatch" {
                break progress.dispatch.unwrap();
            }
            tokio::task::yield_now().await;
        }
    })
    .await
    .unwrap()
}

fn failure(request: &NativeDispatch, no_agent_created: bool) -> NativeFailure {
    NativeFailure {
        dispatch_id: request.dispatch_id.clone(),
        message: "agent thread limit reached".into(),
        no_agent_created,
    }
}

fn resume(request: &NativeDispatch) -> NativeInput {
    NativeInput {
        resume: Some(NativeResume {
            dispatch_id: request.dispatch_id.clone(),
            recovery_evidence: format!(
                "host capacity check after {} reports a free slot",
                request.dispatch_id
            ),
        }),
        ..Default::default()
    }
}

fn requests(fixture: &Fixture) -> usize {
    fixture
        .repo
        .join(".hwahap/artifacts")
        .read_dir()
        .unwrap()
        .filter(|e| {
            e.as_ref()
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("native-request-")
        })
        .count()
}

#[tokio::test]
async fn confirmed_no_child_failure_survives_restart_and_requires_fresh_recovery_evidence() {
    let (fixture, host, mut request) = setup().await;
    let run = std::fs::read(fixture.repo.join(".hwahap/run.json")).unwrap();
    let head = git(&fixture.repo, &["rev-parse", "HEAD"]);
    let failed = failure(&request, true);
    for _ in 0..2 {
        let paused = host
            .advance(
                &fixture.repo,
                NativeInput {
                    dispatch_failure: Some(failed.clone()),
                    ..Default::default()
                },
            )
            .await
            .unwrap();
        assert_eq!(paused.outcome.next, "native_paused");
        assert_eq!(
            paused.dispatch.unwrap().failure.unwrap().message,
            failed.message
        );
    }
    let mut altered = failed.clone();
    altered.message = "different failure".into();
    assert!(host
        .advance(
            &fixture.repo,
            NativeInput {
                dispatch_failure: Some(altered),
                ..Default::default()
            }
        )
        .await
        .is_err());
    host.shutdown().await;
    drop(host);
    let host = NativeHost::default();
    for _ in 0..3 {
        assert_eq!(
            host.status(&fixture.repo).await.unwrap().outcome.next,
            "native_paused"
        );
        assert_eq!(
            host.advance(&fixture.repo, NativeInput::default())
                .await
                .unwrap()
                .outcome
                .next,
            "native_paused"
        );
    }
    assert_eq!(requests(&fixture), 1);
    assert_eq!(
        std::fs::read(fixture.repo.join(".hwahap/run.json")).unwrap(),
        run
    );
    assert_eq!(git(&fixture.repo, &["rev-parse", "HEAD"]), head);
    assert!(host
        .advance(
            &fixture.repo,
            NativeInput {
                request: Some("replace it".into()),
                ..Default::default()
            }
        )
        .await
        .is_err());
    let evidence = resume(&request).resume.unwrap().recovery_evidence;
    let mut blank = resume(&request);
    blank.resume.as_mut().unwrap().recovery_evidence = " ".into();
    assert!(host.advance(&fixture.repo, blank).await.is_err());
    for expected in 2..=3 {
        assert_eq!(
            host.advance(&fixture.repo, resume(&request))
                .await
                .unwrap()
                .outcome
                .next,
            "continue"
        );
        let next = dispatch(&host, &fixture).await;
        assert_eq!(next.run_id, request.run_id);
        assert_ne!(next.dispatch_id, request.dispatch_id);
        assert_eq!(requests(&fixture), expected);
        request = next;
        host.advance(
            &fixture.repo,
            NativeInput {
                dispatch_failure: Some(failure(&request, true)),
                ..Default::default()
            },
        )
        .await
        .unwrap();
    }
    let mut reused = resume(&request);
    reused.resume.as_mut().unwrap().recovery_evidence = evidence;
    assert!(host.advance(&fixture.repo, reused).await.is_err());
    assert_eq!(requests(&fixture), 3);
    host.shutdown().await;
}
