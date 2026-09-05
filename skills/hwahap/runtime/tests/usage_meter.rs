use hwahap::{
    clock::FixedClock,
    cost::meter,
    plan::SCHEMA,
    state::{Run, RunState, Store},
};
use serde_json::json;

fn fixture() -> (tempfile::TempDir, Store, std::path::PathBuf) {
    let dir = tempfile::tempdir().unwrap();
    let store = Store::open(dir.path()).unwrap();
    store
        .write_run(
            &FixedClock::new("2026-09-06T00:00:00Z"),
            &Run {
                schema: SCHEMA.into(),
                run_id: "run".into(),
                goal_id: "goal".into(),
                revision: 1,
                state: RunState::Inspecting,
                accepted_units: vec![],
                accepted_fingerprints: Default::default(),
                plan_digest: None,
                branch: String::new(),
                reviewed_head: None,
                seq: 0,
            },
        )
        .unwrap();
    let log = dir.path().join("session.jsonl");
    let text = format!(
        "{}\n{}\n",
        json!({"type":"session_meta","payload":{"id":"parent"}}),
        json!({"type":"turn_context","payload":{"model":"gpt-6-astra"}})
    );
    std::fs::write(&log, text).unwrap();
    (dir, store, log)
}
fn event(path: &std::path::Path, input: u64, cached: u64, output: u64) {
    use std::io::Write;
    writeln!(std::fs::OpenOptions::new().append(true).open(path).unwrap(), "{}", json!({
        "type":"event_msg","payload":{"type":"token_count","info":{"total_token_usage":{
        "input_tokens":input,"cached_input_tokens":cached,"output_tokens":output,"reasoning_output_tokens":output/2}}}})).unwrap();
}

#[test]
fn baseline_replay_cache_and_reasoning_are_counted_once_without_transcripts() {
    let (_dir, store, log) = fixture();
    event(&log, 100, 80, 10);
    meter::attach(&store, &log, false).unwrap();
    event(&log, 180, 140, 30);
    event(&log, 180, 140, 30); // repeated cumulative notification
    meter::attach(&store, &log, false).unwrap(); // baseline never moves on replay
    let value = meter::summary(&store).unwrap();
    assert_eq!(value["total"]["input_tokens"], 80);
    assert_eq!(value["total"]["cached_input_tokens"], 60);
    assert_eq!(value["total"]["output_tokens"], 20); // reasoning already included
    assert_eq!(meter::summary(&store).unwrap(), value);
    assert!(meter::attach(&store, &log, true).is_err());
    for entry in std::fs::read_dir(store.artifacts_path()).unwrap() {
        assert!(!std::fs::read_to_string(entry.unwrap().path())
            .unwrap()
            .contains("token_count"));
    }
}

#[test]
fn missing_reset_and_replaced_sources_are_unknown_instead_of_zero_usage() {
    let (_dir, store, log) = fixture();
    event(&log, 100, 80, 10);
    meter::attach(&store, &log, false).unwrap();
    event(&log, 90, 70, 9);
    let value = meter::summary(&store).unwrap();
    assert_eq!(value["observed_sessions"], 0);
    assert_eq!(value["unavailable_sessions"], json!(["parent"]));
    std::fs::remove_file(&log).unwrap();
    assert_eq!(
        meter::summary(&store).unwrap()["unavailable_sessions"],
        json!(["parent"])
    );
}

#[test]
fn explicit_whole_session_counts_model_changes_and_ignores_partial_writes() {
    use std::io::Write;
    let (_dir, store, log) = fixture();
    event(&log, 10, 5, 2);
    writeln!(
        std::fs::OpenOptions::new().append(true).open(&log).unwrap(),
        "{}",
        json!({"type":"turn_context","payload":{"model":"gpt-5.6-terra"}})
    )
    .unwrap();
    event(&log, 30, 15, 5);
    write!(
        std::fs::OpenOptions::new().append(true).open(&log).unwrap(),
        "{{partial"
    )
    .unwrap();
    meter::attach(&store, &log, true).unwrap();
    let value = meter::summary(&store).unwrap();
    assert_eq!(value["total"]["input_tokens"], 30);
    assert_eq!(value["by_model"]["gpt-5.6-terra"]["input_tokens"], 20);
    assert_eq!(value["by_model"]["gpt-6-astra"]["output_tokens"], 2);
}
