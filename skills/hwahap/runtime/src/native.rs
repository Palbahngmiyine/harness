//! Native Codex dispatches. The host owns agents; Hwahap owns durable progress.

use std::path::{Path, PathBuf};

use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::error::{Error, Result};
use crate::session::TokenUsage;
use crate::state::Store;

mod broker;
pub use broker::NativeSessions;
mod host;
pub use host::{NativeHost, NativeInput, NativeProgress};

const PENDING: &str = "native-pending.json";

/// One exact request to relay to a fresh native child, without inherited history.
#[derive(Debug, Clone, Serialize, Deserialize, JsonSchema)]
pub struct NativeDispatch {
    pub dispatch_id: String,
    pub run_id: String,
    pub role: String,
    pub profile: String,
    pub unit: Option<String>,
    pub model: String,
    pub effort: String,
    pub cwd: String,
    pub access: String,
    /// Only an already-Astra host may perform these planning roles directly.
    pub coordinator_allowed: bool,
    pub prompt_digest: String,
    pub plan_digest: Option<String>,
    pub base_head: String,
    pub brief: String,
    pub agent_id: Option<String>,
    /// True after a deadline or process restart: stop the child before acknowledging recovery.
    pub stop_required: bool,
}

/// Persist the child identity immediately after spawn, before waiting for its answer.
#[derive(Debug, Clone, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NativeRegistration {
    pub dispatch_id: String,
    pub agent_id: String,
}

/// Agent text is untrusted input. Only real host tool usage may populate reported_usage.
#[derive(Debug, Clone, Deserialize, Serialize, JsonSchema, PartialEq, Eq)]
#[serde(deny_unknown_fields)]
pub struct NativeCompletion {
    pub dispatch_id: String,
    pub agent_id: String,
    pub final_message: String,
    pub agent_stopped: bool,
    #[serde(default)]
    pub reported_usage: Option<TokenUsage>,
}

/// Explicit host confirmation after it has stopped an orphan and its remaining work.
#[derive(Debug, Clone, Deserialize, Serialize, JsonSchema)]
#[serde(deny_unknown_fields)]
pub struct NativeStopped {
    pub dispatch_id: String,
    pub agent_id: Option<String>,
    pub all_work_stopped: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub(super) struct Pending {
    pub dispatch: NativeDispatch,
    pub completion: Option<NativeCompletion>,
}

pub(super) fn save(store: &Store, pending: &Pending) -> Result<()> {
    store.write_artifact(PENDING, &json(pending)?)
}

fn json(value: &impl Serialize) -> Result<String> {
    serde_json::to_string_pretty(value).map_err(|e| Error::Internal(e.to_string()))
}

pub(super) fn load(store: &Store) -> Result<Option<Pending>> {
    let path = store.artifacts_path().join(PENDING);
    match std::fs::read_to_string(&path) {
        Ok(text) => serde_json::from_str(&text)
            .map(Some)
            .map_err(|e| Error::Corrupt(format!("{}: {e}", path.display()))),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(None),
        Err(e) => Err(Error::io(path, e)),
    }
}

pub fn orphan(store: &Store) -> Result<Option<NativeDispatch>> {
    Ok(load(store)?.map(|pending| NativeDispatch {
        stop_required: true,
        ..pending.dispatch
    }))
}

pub fn acknowledge_stopped(store: &Store, ack: &NativeStopped) -> Result<()> {
    let pending =
        load(store)?.ok_or_else(|| Error::Rejected("no native dispatch to stop".into()))?;
    if !ack.all_work_stopped
        || ack.dispatch_id != pending.dispatch.dispatch_id
        || ack.agent_id != pending.dispatch.agent_id
    {
        return Err(Error::Rejected(
            "stop acknowledgment does not match the pending native dispatch".into(),
        ));
    }
    store.write_artifact(
        &format!("native-stopped-{}.json", ack.dispatch_id),
        &json(ack)?,
    )?;
    clear(store)
}

pub(super) fn clear(store: &Store) -> Result<()> {
    let path = store.artifacts_path().join(PENDING);
    match std::fs::remove_file(&path) {
        Ok(()) => Ok(()),
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(()),
        Err(e) => Err(Error::io(path, e)),
    }
}

/// An OS lock survives task cancellation and is released automatically on process death.
pub struct RepoLock(std::fs::File);

impl RepoLock {
    pub fn acquire(root: &Path) -> Result<Self> {
        let dir = root.join(".hwahap");
        std::fs::create_dir_all(&dir).map_err(|e| Error::io(&dir, e))?;
        let path: PathBuf = dir.join("native.lock");
        let file = std::fs::OpenOptions::new()
            .create(true)
            .truncate(false)
            .read(true)
            .write(true)
            .open(&path)
            .map_err(|e| Error::io(&path, e))?;
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            // SAFETY: flock only observes this live descriptor and stores no Rust pointer.
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
                return Err(Error::Rejected(format!(
                    "another Hwahap process owns {}",
                    root.display()
                )));
            }
            Ok(Self(file))
        }
        #[cfg(not(unix))]
        Err(Error::Rejected(
            "native runs require a supported OS file lock".into(),
        ))
    }
}

impl Drop for RepoLock {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            use std::os::fd::AsRawFd;
            // SAFETY: this descriptor remains live until the File field is dropped.
            unsafe {
                libc::flock(self.0.as_raw_fd(), libc::LOCK_UN);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn independent_lock_owners_are_excluded() {
        let temp = tempfile::tempdir().unwrap();
        let lock = RepoLock::acquire(temp.path()).unwrap();
        assert!(RepoLock::acquire(temp.path()).is_err());
        drop(lock);
        RepoLock::acquire(temp.path()).unwrap();
    }

    #[test]
    fn no_pending_is_read_only_and_cannot_be_acknowledged() {
        let temp = tempfile::tempdir().unwrap();
        let store = Store::open(temp.path()).unwrap();
        assert!(orphan(&store).unwrap().is_none());
        assert!(!store.root().exists());
        assert!(acknowledge_stopped(
            &store,
            &NativeStopped {
                dispatch_id: "unknown".into(),
                agent_id: None,
                all_work_stopped: true,
            }
        )
        .is_err());
    }
}
