use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;

use tokio::sync::Mutex;
use tokio::task::JoinHandle;

use super::{
    acknowledge_stopped, orphan, record_failure, resume_failed, NativeCompletion, NativeDispatch,
    NativeFailure, NativeRegistration, NativeResume, NativeSessions, NativeStopped, RepoLock,
};
use crate::config::Config;
use crate::engine::{Engine, StepOutcome};
use crate::error::{Error, Result};
use crate::state::Store;

#[derive(Default)]
pub struct NativeInput {
    pub build: Option<crate::engine::BuildRequest>,
    pub host_session_id: Option<String>,
    pub request: Option<String>,
    pub user_input: Option<String>,
    pub registration: Option<NativeRegistration>,
    pub completion: Option<NativeCompletion>,
    pub stopped: Option<NativeStopped>,
    pub dispatch_failure: Option<NativeFailure>,
    pub resume: Option<NativeResume>,
}

pub struct NativeProgress {
    pub outcome: StepOutcome,
    pub dispatch: Option<NativeDispatch>,
}

struct Active {
    broker: Arc<NativeSessions>,
    task: JoinHandle<Result<StepOutcome>>,
    // Registry and task both hold the lock, including while cancellation is being delivered.
    _lock: Arc<RepoLock>,
}

impl Drop for Active {
    fn drop(&mut self) {
        self.task.abort();
    }
}

/// One background continuation per canonical Git root. Polling never starts another writer.
#[derive(Default)]
pub struct NativeHost {
    active: Mutex<HashMap<PathBuf, Active>>,
}

impl NativeHost {
    /// Stop engine-owned commands before the MCP process exits; native children remain host-owned.
    pub async fn shutdown(&self) {
        let mut active = self.active.lock().await;
        for running in active.values() {
            running.task.abort();
        }
        for (_, mut running) in active.drain() {
            let _ = (&mut running.task).await;
        }
    }

    pub async fn advance(&self, root: &Path, input: NativeInput) -> Result<NativeProgress> {
        let actions = usize::from(input.build.is_some())
            + usize::from(input.registration.is_some())
            + usize::from(input.completion.is_some())
            + usize::from(input.stopped.is_some())
            + usize::from(input.dispatch_failure.is_some())
            + usize::from(input.resume.is_some());
        if actions > 1 || (actions > 0 && (input.request.is_some() || input.user_input.is_some())) {
            return Err(Error::Rejected(
                "send exactly one native action, without request or user_input".into(),
            ));
        }
        let mut active = self.active.lock().await;
        let store = Store::open(root)?;
        if let Some(scope) = &input.host_session_id {
            if scope.trim().is_empty() || scope.len() > 128 {
                return Err(Error::Rejected("host_session_id must be a stable, nonempty parent task identifier (at most 128 bytes)".into()));
            }
        }
        let expected_scope = input
            .host_session_id
            .clone()
            .or(store.read_run()?.map(|run| run.run_id));
        if active
            .get(root)
            .is_some_and(|running| running.broker.host_session_id != input.host_session_id)
            || orphan(&store)?.is_some_and(|dispatch| {
                !dispatch.pool_scope.is_empty() && Some(dispatch.pool_scope) != expected_scope
            })
        {
            return Err(Error::Rejected(
                "native work belongs to another parent task; do not reuse or stop its agents"
                    .into(),
            ));
        }
        if let Some(build) = &input.build {
            if active.contains_key(root) || orphan(&store)?.is_some() {
                return Err(Error::Rejected(
                    "native execution must finish before direct BUILD".into(),
                ));
            }
            let _lock = RepoLock::acquire(root)?;
            return Ok(NativeProgress {
                outcome: Engine::open(root)?.start_build(build)?,
                dispatch: None,
            });
        }
        if let Some(failure) = &input.dispatch_failure {
            super::failure::check_failure(&store, failure)?;
            let lock = if let Some(mut running) = active.remove(root) {
                running.task.abort();
                let _ = (&mut running.task).await;
                running._lock.clone()
            } else {
                Arc::new(RepoLock::acquire(root)?)
            };
            let dispatch = record_failure(&store, failure)?;
            drop(lock);
            return progress(root, Some(dispatch), false);
        }
        if let Some(resume) = &input.resume {
            if let Some(running) = active.get(root) {
                if super::failure::recorded_resume(&store, resume)? {
                    return progress(root, running.broker.dispatch()?, true);
                }
                return Err(Error::Rejected("native execution is still active".into()));
            }
            let _lock = RepoLock::acquire(root)?;
            resume_failed(&store, resume)?;
            return progress(root, orphan(&store)?, false);
        }
        if let Some(ack) = &input.stopped {
            super::check_stopped(&store, ack)?;
            let lock = if let Some(mut running) = active.remove(root) {
                running.task.abort();
                let _ = (&mut running.task).await;
                running._lock.clone()
            } else {
                Arc::new(RepoLock::acquire(root)?)
            };
            acknowledge_stopped(&store, ack)?;
            drop(lock);
            return progress(root, None, false);
        }
        if let Some(running) = active.get(root) {
            if input.request.is_some() || input.user_input.is_some() {
                return Err(Error::Rejected(
                    "a native continuation is active; stop it before changing its input".into(),
                ));
            }
            if let Some(registration) = &input.registration {
                running.broker.register(registration)?;
            }
            if let Some(completion) = input.completion {
                running.broker.complete(completion)?;
            }
        } else {
            let lock = Arc::new(RepoLock::acquire(root)?);
            if let Some(dispatch) = orphan(&store)? {
                if actions > 0 || input.request.is_some() || input.user_input.is_some() {
                    return Err(Error::Rejected(
                        "pending native work requires recovery before new input".into(),
                    ));
                }
                return progress(root, Some(dispatch), false);
            }
            if input.registration.is_some() {
                return Err(Error::Rejected(
                    "no live native dispatch accepts registration".into(),
                ));
            }
            if let Some(completion) = input.completion {
                if NativeSessions::recorded_completion(&store, &completion)? {
                    return progress(root, None, false);
                }
                return Err(Error::Rejected(
                    "no live native dispatch accepts completion".into(),
                ));
            }
            let config = Config::load(store.root())?;
            let mut sessions = NativeSessions::new(
                store,
                config.profiles,
                config.native_max_calls,
                config.native_timeout_secs,
            );
            if let Some(scope) = input.host_session_id {
                sessions = sessions.with_host_session_id(scope);
            }
            let broker = Arc::new(sessions);
            let engine = Engine::open(root)?;
            let sessions = broker.clone();
            let task_lock = lock.clone();
            let task = tokio::spawn(async move {
                let _lock = task_lock;
                engine
                    .step_with(
                        &*sessions,
                        input.request.as_deref(),
                        input.user_input.as_deref(),
                    )
                    .await
            });
            active.insert(
                root.into(),
                Active {
                    broker,
                    task,
                    _lock: lock,
                },
            );
        }
        tokio::task::yield_now().await;
        if active
            .get(root)
            .is_some_and(|running| running.task.is_finished())
        {
            let mut running = active.remove(root).expect("active entry was just checked");
            let result = (&mut running.task)
                .await
                .map_err(|e| Error::Internal(format!("native engine task ended: {e}")))?;
            if let Some(dispatch) = running.broker.dispatch()? {
                return progress(
                    root,
                    Some(NativeDispatch {
                        stop_required: true,
                        ..dispatch
                    }),
                    false,
                );
            }
            running.broker.finish()?;
            return Ok(NativeProgress {
                outcome: result?,
                dispatch: None,
            });
        }
        let dispatch = active
            .get(root)
            .map(|running| running.broker.dispatch())
            .transpose()?
            .flatten();
        progress(root, dispatch, true)
    }

    pub async fn status(&self, root: &Path) -> Result<NativeProgress> {
        let active = self.active.lock().await;
        match active.get(root) {
            Some(running) => progress(root, running.broker.dispatch()?, true),
            None => progress(root, orphan(&Store::open(root)?)?, false),
        }
    }

    pub async fn ship(&self, root: &Path, confirmation: &str) -> Result<StepOutcome> {
        let active = self.active.lock().await;
        if active.contains_key(root) {
            return Err(Error::Rejected("native execution is still active".into()));
        }
        let _lock = RepoLock::acquire(root)?;
        if let Some(dispatch) = orphan(&Store::open(root)?)? {
            return Err(Error::Rejected(
                if dispatch
                    .failure
                    .as_ref()
                    .is_some_and(|f| f.no_agent_created)
                {
                    "native execution is paused; resume with observed host recovery before shipping"
                        .into()
                } else {
                    "native stop acknowledgment is required before shipping".into()
                },
            ));
        }
        Engine::open(root)?.ship(confirmation)
    }
}

fn progress(
    root: &Path,
    dispatch: Option<NativeDispatch>,
    running: bool,
) -> Result<NativeProgress> {
    let mut outcome = Engine::open(root)?.status()?;
    if let Some(dispatch) = &dispatch {
        outcome.next = if dispatch.stop_required {
            "native_stop"
        } else if dispatch.failure.is_some() {
            "native_paused"
        } else if dispatch.agent_id.is_some() {
            "native_wait"
        } else {
            "native_dispatch"
        }
        .into();
        outcome.message = if let Some(failure) = &dispatch.failure {
            format!(
                "Native dispatch failed: {}. {}",
                failure.message,
                if failure.no_agent_created {
                    "No child was created. Do not poll or spawn again; resume only with new observed host recovery evidence. The run and plan are preserved."
                } else {
                    "Child creation is uncertain. Locate the exact dispatch and stop all its work before acknowledging recovery. Do not spawn again."
                }
            )
        } else if dispatch.stop_required {
            "Stop this native agent and all remaining commands, then acknowledge the exact dispatch before recovery.".into()
        } else {
            format!("Native {} dispatch {}", dispatch.role, dispatch.dispatch_id)
        };
        if !dispatch.stop_required && dispatch.failure.is_none() {
            if let Some(elapsed) =
                super::timing::elapsed_since_offer(&Store::open(root)?, &dispatch.dispatch_id)?
            {
                outcome.message.push_str(&format!(
                    ". Host-observed elapsed: {elapsed} ms; target {}s, deadline {}s.",
                    dispatch.soft_budget_secs, dispatch.hard_timeout_secs,
                ));
                if elapsed > dispatch.soft_budget_secs.saturating_mul(1000) {
                    outcome.message.push_str(" Target exceeded: inspect progress and remaining scope; do not infer completion or start another agent.");
                }
            }
        }
    } else if running {
        outcome.next = "native_wait".into();
        outcome.message =
            "Hwahap is validating or preparing the next native dispatch; poll after one second."
                .into();
    }
    Ok(NativeProgress { outcome, dispatch })
}
