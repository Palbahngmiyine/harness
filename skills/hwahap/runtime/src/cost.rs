//! Requested models and caller-reported tokens are evidence, never a verified bill.
use std::collections::BTreeMap;

use serde::{de::DeserializeOwned, Serialize};

use crate::native::{NativeCompletion, NativeDispatch, NativeStopped};
use crate::state::Store;
use crate::{Error, Result};

#[derive(Default, Serialize)]
struct Counts {
    requests: u64,
    completions: u64,
    stopped_without_completion: u64,
    incomplete: u64,
    coordinator_completions: u64,
    native_child_completions: u64,
    coordinator_usage_reported_completions: u64,
    native_child_usage_reported_completions: u64,
    usage_reported_completions: u64,
    requests_without_reported_usage: u64,
    reported_input_tokens: u64,
    reported_output_tokens: u64,
    reported_cached_input_tokens: u64,
}

fn add(target: &mut u64, value: u64) -> Result<()> {
    *target = target
        .checked_add(value)
        .ok_or_else(|| Error::Corrupt("native usage counter overflow".into()))?;
    Ok(())
}

fn artifacts<T: DeserializeOwned>(store: &Store, prefix: &str) -> Result<BTreeMap<String, T>> {
    let dir = store.artifacts_path();
    let entries = match std::fs::read_dir(&dir) {
        Ok(entries) => entries,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => return Ok(BTreeMap::new()),
        Err(e) => return Err(Error::io(dir, e)),
    };
    let mut records = BTreeMap::new();
    for entry in entries {
        let path = entry.map_err(|e| Error::io(&dir, e))?.path();
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        let Some(id) = name
            .strip_prefix(prefix)
            .and_then(|s| s.strip_suffix(".json"))
        else {
            continue;
        };
        let bytes = std::fs::read(&path).map_err(|e| Error::io(&path, e))?;
        let record = serde_json::from_slice(&bytes)
            .map_err(|e| Error::Corrupt(format!("{}: {e}", path.display())))?;
        records.insert(id.to_owned(), record);
    }
    Ok(records)
}

fn collect(store: &Store) -> Result<(Counts, BTreeMap<String, Counts>)> {
    let run = store.read_run()?;
    let completions = artifacts::<NativeCompletion>(store, "native-completion-")?;
    let stopped = artifacts::<NativeStopped>(store, "native-stopped-")?;
    // Requests are durable before results: read them last while the engine may be progressing.
    let requests = artifacts::<NativeDispatch>(store, "native-request-")?;
    for (id, completion) in &completions {
        if id != &completion.dispatch_id || !requests.contains_key(id) || !completion.agent_stopped
        {
            return Err(Error::Corrupt(format!("invalid native completion {id}")));
        }
    }
    for (id, ack) in &stopped {
        if id != &ack.dispatch_id || !requests.contains_key(id) || !ack.all_work_stopped {
            return Err(Error::Corrupt(format!(
                "invalid native stop acknowledgment {id}"
            )));
        }
    }
    let (mut total, mut models) = (Counts::default(), BTreeMap::<String, Counts>::new());
    for (id, request) in requests {
        if id != request.dispatch_id
            || request.model.trim().is_empty()
            || run.as_ref().is_some_and(|run| run.run_id != request.run_id)
        {
            return Err(Error::Corrupt(format!("invalid native request {id}")));
        }
        let completion = completions.get(&id);
        if let Some(completion) = completion {
            if completion.agent_id.trim().is_empty()
                || (completion.agent_id == "coordinator" && !request.coordinator_allowed)
            {
                return Err(Error::Corrupt(format!(
                    "invalid native completion identity {id}"
                )));
            }
            if let Some(usage) = &completion.reported_usage {
                usage
                    .verify()
                    .map_err(|e| Error::Corrupt(format!("native usage {id}: {e}")))?;
            }
        }
        for counts in [&mut total, models.entry(request.model).or_default()] {
            add(&mut counts.requests, 1)?;
            let Some(completion) = completion else {
                add(&mut counts.incomplete, 1)?;
                add(
                    &mut counts.stopped_without_completion,
                    u64::from(stopped.contains_key(&id)),
                )?;
                add(&mut counts.requests_without_reported_usage, 1)?;
                continue;
            };
            add(&mut counts.completions, 1)?;
            if completion.agent_id == "coordinator" {
                add(&mut counts.coordinator_completions, 1)?;
            } else {
                add(&mut counts.native_child_completions, 1)?;
            }
            if let Some(usage) = &completion.reported_usage {
                add(&mut counts.usage_reported_completions, 1)?;
                if completion.agent_id == "coordinator" {
                    add(&mut counts.coordinator_usage_reported_completions, 1)?;
                } else {
                    add(&mut counts.native_child_usage_reported_completions, 1)?;
                }
                add(&mut counts.reported_input_tokens, usage.input_tokens)?;
                add(&mut counts.reported_output_tokens, usage.output_tokens)?;
                add(
                    &mut counts.reported_cached_input_tokens,
                    usage.cached_input_tokens,
                )?;
            } else {
                add(&mut counts.requests_without_reported_usage, 1)?;
            }
        }
    }
    Ok((total, models))
}

/// Includes every durable request, including retries and work without a completion.
pub fn summary(store: &Store) -> Result<serde_json::Value> {
    let (total, models) = collect(store)?;
    Ok(serde_json::json!({
        "scope": "retained native requests for this run; receipts are not counted again",
        "evidence": "caller-reported tokens grouped by requested model; actual model unverified",
        "coverage": "usage_reported_completions / requests; incomplete work may consume tokens",
        "total_billed_cost": "unknown",
        "parent_relay_usage": "unknown; separate from any reported coordinator dispatch usage",
        "limits": "Missing usage is unknown, not zero. Parent relay tokens are not measured. Token subtotals are reported evidence only; cached input is part of input.",
        "total": total, "by_requested_model": models,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn put(store: &Store, kind: &str, id: &str, value: serde_json::Value) {
        store
            .write_artifact(&format!("native-{kind}-{id}.json"), &value.to_string())
            .unwrap();
    }
    fn request(store: &Store, id: &str, model: &str) {
        put(
            store,
            "request",
            id,
            json!({"dispatch_id":id,"run_id":"run","role":"recommender",
            "profile":"deep","unit":null,"model":model,"effort":"high","cwd":"/tmp",
            "access":"read_only","coordinator_allowed":true,"prompt_digest":"x",
            "plan_digest":null,"base_head":"head","brief":"task","agent_id":null,"stop_required":false}),
        );
    }
    fn complete(store: &Store, id: &str, agent: &str, usage: serde_json::Value) {
        put(
            store,
            "completion",
            id,
            json!({"dispatch_id":id,"agent_id":agent,
            "final_message":"done","agent_stopped":true,"reported_usage":usage}),
        );
    }
    #[test]
    fn retries_partial_coverage_coordinator_and_idempotent_completion() {
        let dir = tempfile::tempdir().unwrap();
        let store = Store::open(dir.path()).unwrap();
        for (id, model) in [
            ("first", "astra"),
            ("retry", "astra"),
            ("child", "luna"),
            ("pending", "luna"),
        ] {
            request(&store, id, model);
        }
        let usage = json!({"input_tokens":100,"output_tokens":20,"cached_input_tokens":80});
        complete(&store, "retry", "coordinator", usage.clone());
        complete(&store, "retry", "coordinator", usage);
        complete(&store, "child", "agent-1", serde_json::Value::Null);
        put(
            &store,
            "stopped",
            "first",
            json!({"dispatch_id":"first","agent_id":"agent-0","all_work_stopped":true}),
        );
        let (total, models) = collect(&store).unwrap();
        assert_eq!(
            (total.requests, total.completions, total.incomplete),
            (4, 2, 2)
        );
        assert_eq!(
            (
                total.coordinator_completions,
                total.native_child_completions
            ),
            (1, 1)
        );
        assert_eq!(
            (
                total.usage_reported_completions,
                total.requests_without_reported_usage
            ),
            (1, 3)
        );
        assert_eq!(total.stopped_without_completion, 1);
        assert_eq!(
            (
                total.coordinator_usage_reported_completions,
                total.native_child_usage_reported_completions
            ),
            (1, 0)
        );
        assert_eq!(models["astra"].reported_input_tokens, 100);
        assert_eq!(
            (
                total.reported_output_tokens,
                total.reported_cached_input_tokens
            ),
            (20, 80)
        );
    }
    #[test]
    fn bad_evidence_is_an_error_instead_of_zero_usage() {
        let dir = tempfile::tempdir().unwrap();
        let store = Store::open(dir.path()).unwrap();
        request(&store, "a", "astra");
        complete(
            &store,
            "a",
            "coordinator",
            json!({"input_tokens":1,"output_tokens":0,"cached_input_tokens":2}),
        );
        assert!(summary(&store).is_err());
        complete(
            &store,
            "a",
            "coordinator",
            json!({"input_tokens":u64::MAX,"output_tokens":0,"cached_input_tokens":0}),
        );
        request(&store, "b", "astra");
        complete(
            &store,
            "b",
            "coordinator",
            json!({"input_tokens":1,"output_tokens":0,"cached_input_tokens":0}),
        );
        assert!(summary(&store).is_err());
        store
            .write_artifact("native-completion-a.json", "{")
            .unwrap();
        assert!(summary(&store).is_err());
    }
}
