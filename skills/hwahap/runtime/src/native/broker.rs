use std::sync::Mutex;

use tokio::sync::oneshot;

use super::{json, load, save, NativeCompletion, NativeDispatch, NativeRegistration, Pending};
use crate::error::{Error, Result};
use crate::profile::Profiles;
use crate::state::Store;

mod dispatch;

pub(super) struct Waiting {
    pub pending: Pending,
    pub sender: Option<oneshot::Sender<NativeCompletion>>,
}

/// A single-flight bridge: request is durable before the host can spawn an agent.
pub struct NativeSessions {
    pub(super) store: Store,
    pub(super) profiles: Profiles,
    pub(super) max_calls: u64,
    pub(super) timeout_secs: u64,
    pub(super) waiting: Mutex<Option<Waiting>>,
}

impl NativeSessions {
    pub fn new(store: Store, profiles: Profiles, max_calls: u64, timeout_secs: u64) -> Self {
        Self { store, profiles, max_calls, timeout_secs, waiting: Mutex::new(None) }
    }

    pub fn dispatch(&self) -> Result<Option<NativeDispatch>> {
        let guard = self.waiting.lock().map_err(poisoned)?;
        Ok(guard.as_ref().and_then(|w| {
            if w.pending.completion.is_some() { None } else { Some(w.pending.dispatch.clone()) }
        }))
    }

    pub fn register(&self, registration: &NativeRegistration) -> Result<()> {
        if registration.agent_id.trim().is_empty() {
            return Err(Error::Rejected("native agent_id must not be empty".into()));
        }
        let mut guard = self.waiting.lock().map_err(poisoned)?;
        let waiting = guard.as_mut().ok_or_else(|| Error::Rejected("no pending native dispatch".into()))?;
        let dispatch = &mut waiting.pending.dispatch;
        if dispatch.dispatch_id != registration.dispatch_id || dispatch.stop_required {
            return Err(Error::Rejected("registration does not match an active dispatch".into()));
        }
        match &dispatch.agent_id {
            Some(id) if id != &registration.agent_id => {
                return Err(Error::Rejected("native dispatch already belongs to another agent".into()));
            }
            Some(_) => return Ok(()),
            None => dispatch.agent_id = Some(registration.agent_id.clone()),
        }
        save(&self.store, &waiting.pending)
    }

    /// Durable recording precedes delivery. Identical retries do not deliver twice.
    pub fn complete(&self, completion: NativeCompletion) -> Result<()> {
        if !completion.agent_stopped {
            return Err(Error::Rejected("wait for the native child to stop before completing".into()));
        }
        if let Some(usage) = &completion.reported_usage { usage.verify()?; }
        let mut guard = self.waiting.lock().map_err(poisoned)?;
        let waiting = guard.as_mut().ok_or_else(|| Error::Rejected("no pending native dispatch".into()))?;
        let dispatch = &waiting.pending.dispatch;
        if completion.dispatch_id != dispatch.dispatch_id
            || dispatch.agent_id.as_deref() != Some(&completion.agent_id)
            || dispatch.stop_required
        {
            return Err(Error::Rejected("completion does not match the registered native dispatch".into()));
        }
        if let Some(previous) = &waiting.pending.completion {
            return if previous == &completion { Ok(()) } else {
                Err(Error::Rejected("native completion was already recorded with different content".into()))
            };
        }
        self.store.write_artifact(&format!("native-completion-{}.json", completion.dispatch_id), &json(&completion)?)?;
        waiting.pending.completion = Some(completion.clone());
        save(&self.store, &waiting.pending)?;
        let sender = waiting.sender.take().ok_or_else(|| Error::Rejected("native continuation no longer exists".into()))?;
        sender.send(completion).map_err(|_| Error::Rejected("native continuation ended; stop acknowledgment is required before recovery".into()))
    }

    /// Only after the engine has finished consuming the final result can its guard disappear.
    pub fn finish(&self) -> Result<()> {
        let guard = self.waiting.lock().map_err(poisoned)?;
        if guard.as_ref().is_some_and(|w| w.pending.completion.is_none()) {
            return Err(Error::Rejected("native agent still needs stop acknowledgment".into()));
        }
        super::clear(&self.store)
    }

    pub(super) fn expire(&self) -> Result<()> {
        let mut guard = self.waiting.lock().map_err(poisoned)?;
        if let Some(waiting) = guard.as_mut() {
            waiting.pending.dispatch.stop_required = true;
            save(&self.store, &waiting.pending)?;
        }
        Ok(())
    }

    pub(super) fn next_call(&self) -> Result<u64> {
        let count = match std::fs::read_dir(self.store.artifacts_path()) {
            Ok(files) => files.collect::<std::io::Result<Vec<_>>>()
                .map_err(|e| Error::io(self.store.artifacts_path(), e))?
                .iter().filter(|entry| entry.file_name().to_string_lossy().starts_with("native-request-")).count() as u64,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => 0,
            Err(e) => return Err(Error::io(self.store.artifacts_path(), e)),
        };
        if count >= self.max_calls {
            return Err(Error::UnsupportedProfile(format!("native call budget {} is exhausted; no agent was spawned", self.max_calls)));
        }
        if let Some(pending) = load(&self.store)? {
            if pending.completion.is_none() {
                return Err(Error::Rejected("unconsumed native agent must be stopped before another dispatch".into()));
            }
        }
        Ok(count + 1)
    }
}

fn poisoned<T>(_: std::sync::PoisonError<T>) -> Error {
    Error::Internal("native broker lock poisoned".into())
}
