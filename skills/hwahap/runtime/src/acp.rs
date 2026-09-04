//! The ACP client: one pinned adapter process, one session at a time.
//!
//! Hwahap is the client; `codex-acp` is the agent. The whole run happens inside a single
//! [`with_link`] call, so exactly one adapter process exists while a run is active and it is killed
//! — process group and all — when that call returns.
//!
//! Two invariants live here and nowhere else:
//!
//! - **The profile is applied, or the run stops.** ACP v1 has no model or effort field; both are
//!   session *config options* the agent defines. So Hwahap reads the advertised options, refuses to
//!   proceed unless the exact model and the exact effort are offered, sets them, and re-reads the
//!   echoed state to confirm. There is no downgrade path: a missing `xhigh` is
//!   `blocked: unsupported_profile`, never a silent `high`.
//! - **A read-only role cannot be talked into writing.** Hwahap advertises no filesystem and no
//!   terminal capability, so the SDK answers those requests with method-not-found on its own, and
//!   the permission handler rejects every request made during a read-only session. The host still
//!   re-checks the git diff afterwards, because a permission callback that is never invoked proves
//!   nothing.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use agent_client_protocol::schema::v1::{
    CancelNotification, ClientCapabilities, CloseSessionRequest, ContentBlock, ContentChunk,
    Implementation, InitializeRequest, NewSessionRequest, PermissionOption, PermissionOptionKind,
    PromptRequest, RequestPermissionOutcome, RequestPermissionRequest, RequestPermissionResponse,
    SelectedPermissionOutcome, SessionConfigId, SessionConfigKind, SessionConfigOption,
    SessionConfigOptionCategory, SessionConfigOptionValue, SessionConfigSelectOptions, SessionId,
    SessionNotification, SessionUpdate, SetSessionConfigOptionRequest, StopReason, TextContent,
};
use agent_client_protocol::schema::ProtocolVersion;
use agent_client_protocol::{AcpAgent, AcpAgentConfig, Agent, Client, ConnectionTo};

use crate::error::{Error, Result};
use crate::profile::{Effort, Profiles, Receipt, Role};

/// What a session is allowed to do to the working tree.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Access {
    /// Every permission request is rejected.
    ReadOnly,
    /// Permission is granted once per request, never remembered.
    WorkspaceWrite,
}

/// The access a role gets.
///
/// Only the two roles that exist to change code may change code. Everything else — facts, reviews,
/// diagnoses, syntheses — reads.
pub fn access_for(role: Role) -> Access {
    match role {
        Role::Implementer | Role::Rework => Access::WorkspaceWrite,
        Role::FactFinder
        | Role::ColdConsumer
        | Role::PlanCritic
        | Role::UnitReviewer
        | Role::FailureDiagnosis
        | Role::Recommender
        | Role::PlanSynthesis
        | Role::ConflictReplan
        | Role::FinalReview => Access::ReadOnly,
    }
}

/// How to launch the adapter.
///
/// The command is pinned by configuration. `@latest` is deliberately not a default: an adapter that
/// changes under a frozen plan changes the thing the plan was proved against.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Adapter {
    command: PathBuf,
    args: Vec<String>,
    env: std::collections::BTreeMap<String, String>,
}

impl Adapter {
    /// A pinned adapter invocation.
    pub fn new(command: impl Into<PathBuf>, args: Vec<String>) -> Adapter {
        Adapter {
            command: command.into(),
            args,
            env: std::collections::BTreeMap::new(),
        }
    }

    /// Adds one environment variable for the child.
    pub fn with_env(mut self, name: impl Into<String>, value: impl Into<String>) -> Adapter {
        self.env.insert(name.into(), value.into());
        self
    }

    /// Rejects an adapter pinned to a floating version.
    ///
    /// `@latest` in the argv means a rerun of the same frozen plan can meet a different agent.
    pub fn require_pinned(&self) -> Result<()> {
        if self.args.iter().any(|a| a.contains("@latest")) {
            return Err(Error::Rejected(format!(
                "the ACP adapter must be pinned to an exact version, but its arguments contain \
                 \"@latest\": {:?}",
                self.args
            )));
        }
        Ok(())
    }

    fn to_config(&self) -> AcpAgentConfig {
        let mut config = AcpAgentConfig::new(self.command.clone());
        for arg in &self.args {
            config = config.arg(arg.clone());
        }
        for (name, value) in &self.env {
            config = config.env(name.clone(), value.clone());
        }
        config
    }
}

/// One prompt to one fresh session.
#[derive(Debug, Clone)]
pub struct SessionSpec {
    /// The session's working directory. For a worker this is the run worktree, which is the only
    /// scoping the protocol itself provides.
    pub cwd: PathBuf,
    pub role: Role,
    /// The unit this session serves, recorded on the receipt.
    pub unit: Option<String>,
    pub prompt: String,
}

/// What one session produced.
#[derive(Debug, Clone)]
pub struct SessionOutcome {
    /// The agent's final message: the last contiguous run of chunks sharing a message id.
    pub final_message: String,
    /// Everything the agent said, for the artifact record.
    pub transcript: String,
    pub receipt: Receipt,
    /// The stop reason, as the wire spells it.
    pub stop_reason: String,
    /// Permission requests seen during this session, in order.
    pub permissions: Vec<PermissionRecord>,
}

/// One permission decision, kept so the evidence trail can show what was allowed.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PermissionRecord {
    pub tool: String,
    pub granted: bool,
}

#[derive(Default)]
struct Shared {
    /// Chunks per session, in arrival order, as `(message_id, text)`.
    transcripts: HashMap<String, Vec<(Option<String>, String)>>,
    access: HashMap<String, Access>,
    permissions: HashMap<String, Vec<PermissionRecord>>,
}

/// A live connection to the one adapter process.
#[derive(Clone)]
pub struct AgentLink {
    cx: ConnectionTo<Agent>,
    shared: Arc<Mutex<Shared>>,
    profiles: Profiles,
    supports_close: bool,
}

/// Runs `body` with a live adapter, then shuts the adapter down.
///
/// The adapter is spawned in its own process group and killed on drop, so a cancelled or panicking
/// body cannot leave a Codex process behind.
pub async fn with_link<F, R>(adapter: &Adapter, profiles: &Profiles, body: F) -> Result<R>
where
    F: AsyncFnOnce(AgentLink) -> Result<R>,
{
    adapter.require_pinned()?;
    let shared = Arc::new(Mutex::new(Shared::default()));
    let profiles = profiles.clone();

    let notify_shared = shared.clone();
    let permission_shared = shared.clone();

    let transport = AcpAgent::new(adapter.to_config());

    let outcome = Client
        .builder()
        .name("hwahap")
        .on_receive_notification(
            {
                let shared = notify_shared;
                async move |notification: SessionNotification, _cx: ConnectionTo<Agent>| {
                    record_notification(&shared, &notification);
                    Ok(())
                }
            },
            agent_client_protocol::on_receive_notification!(),
        )
        .on_receive_request(
            {
                let shared = permission_shared;
                async move |request: RequestPermissionRequest,
                            responder,
                            _cx: ConnectionTo<Agent>| {
                    let response = decide_permission(&shared, &request);
                    responder.respond(response)
                }
            },
            agent_client_protocol::on_receive_request!(),
        )
        .connect_with(transport, async move |cx: ConnectionTo<Agent>| {
            // The inner Result is Hwahap's; the outer one belongs to the transport. Keeping them
            // separate means a profile failure stays `UnsupportedProfile` instead of being
            // flattened into a generic protocol error.
            let link = match handshake(cx, shared, profiles).await {
                Ok(link) => link,
                Err(e) => return Ok(Err(e)),
            };
            Ok(body(link).await)
        })
        .await
        .map_err(|e| Error::command("codex-acp", format!("ACP transport failed: {e}")))?;

    outcome
}

async fn handshake(
    cx: ConnectionTo<Agent>,
    shared: Arc<Mutex<Shared>>,
    profiles: Profiles,
) -> Result<AgentLink> {
    let initialized = cx
        .send_request(
            InitializeRequest::new(ProtocolVersion::V1)
                // No filesystem and no terminal capability: the SDK then answers `fs/*` and
                // `terminal/*` with method-not-found without Hwahap writing a single handler.
                .client_capabilities(ClientCapabilities::new())
                .client_info(Implementation::new("hwahap", env!("CARGO_PKG_VERSION"))),
        )
        .block_task()
        .await
        .map_err(|e| Error::command("codex-acp", format!("initialize failed: {e}")))?;

    if initialized.protocol_version != ProtocolVersion::V1 {
        return Err(Error::Rejected(format!(
            "the adapter negotiated ACP protocol version {}, but Hwahap only speaks stable v1",
            initialized.protocol_version
        )));
    }

    let supports_close = initialized
        .agent_capabilities
        .session_capabilities
        .close
        .is_some();

    Ok(AgentLink {
        cx,
        shared,
        profiles,
        supports_close,
    })
}

impl AgentLink {
    /// Runs one prompt in a fresh session and closes it.
    ///
    /// Session ids are never persisted: after a crash the unit is rerun from its last accepted
    /// checkpoint rather than resumed, so there is nothing to reload.
    pub async fn run_session(&self, spec: &SessionSpec) -> Result<SessionOutcome> {
        let access = access_for(spec.role);
        let session = self
            .cx
            .send_request(NewSessionRequest::new(spec.cwd.clone()).mcp_servers(vec![]))
            .block_task()
            .await
            .map_err(|e| Error::command("codex-acp", format!("session/new failed: {e}")))?;
        let session_id = session.session_id.clone();
        let key = session_id.0.to_string();

        {
            let mut state = self.lock()?;
            state.access.insert(key.clone(), access);
            state.transcripts.entry(key.clone()).or_default();
            state.permissions.entry(key.clone()).or_default();
        }

        // `session/new` is the only place the agent volunteers its config options, so they are
        // carried forward rather than re-fetched: ACP v1 has no read-only accessor for them.
        let offered = session.config_options.clone().ok_or_else(|| {
            Error::UnsupportedProfile(
                "the adapter returned no session config options, so Hwahap cannot pin a model or \
                 a reasoning effort"
                    .into(),
            )
        });

        // Everything after this point must close the session, so the body is wrapped and the
        // result inspected once. An early `?` here would leak a live session in the adapter.
        let result = match offered {
            Ok(offered) => self.prompt_session(spec, &session_id, &key, offered).await,
            Err(e) => Err(e),
        };
        self.close_session(&session_id).await;
        let mut state = self.lock()?;
        state.access.remove(&key);
        let permissions = state.permissions.remove(&key).unwrap_or_default();
        let chunks = state.transcripts.remove(&key).unwrap_or_default();
        drop(state);

        let (stop_reason, receipt) = result?;
        Ok(SessionOutcome {
            final_message: final_message(&chunks),
            transcript: chunks.iter().map(|(_, text)| text.as_str()).collect(),
            receipt,
            stop_reason,
            permissions,
        })
    }

    async fn prompt_session(
        &self,
        spec: &SessionSpec,
        session_id: &SessionId,
        key: &str,
        offered: Vec<SessionConfigOption>,
    ) -> Result<(String, Receipt)> {
        let receipt = self.apply_profile(spec, session_id, offered).await?;

        let reply = self
            .cx
            .send_request(PromptRequest::new(
                session_id.clone(),
                vec![ContentBlock::Text(TextContent::new(spec.prompt.clone()))],
            ))
            .block_task()
            .await
            .map_err(|e| Error::command("codex-acp", format!("session/prompt failed: {e}")))?;

        let stop_reason = stop_reason_name(&reply.stop_reason);
        if !matches!(reply.stop_reason, StopReason::EndTurn) {
            return Err(Error::command(
                "codex-acp",
                format!("the session for {key} stopped with {stop_reason} instead of end_turn"),
            ));
        }
        Ok((stop_reason, receipt))
    }

    /// Applies the role's model and effort, refusing to prompt unless both took effect exactly.
    async fn apply_profile(
        &self,
        spec: &SessionSpec,
        session_id: &SessionId,
        options: Vec<SessionConfigOption>,
    ) -> Result<Receipt> {
        let wanted = self.profiles.for_role(spec.role);
        let model_id =
            require_offered(&options, SessionConfigOptionCategory::Model, &wanted.model)?;
        let after_model = self.set_option(session_id, model_id, &wanted.model).await?;

        // The effort list is read only after the model is set: the adapter recomputes which efforts
        // a model supports, so a list gathered before the switch describes the wrong model. Failing
        // here is the documented `blocked: unsupported_profile`, never a downgrade.
        let effort_id = require_offered(
            &after_model,
            SessionConfigOptionCategory::ThoughtLevel,
            wanted.effort.as_str(),
        )?;
        let after_effort = self
            .set_option(session_id, effort_id, wanted.effort.as_str())
            .await?;

        let model_applied = current_value(&after_effort, SessionConfigOptionCategory::Model)?;
        let effort_applied =
            current_value(&after_effort, SessionConfigOptionCategory::ThoughtLevel)?;

        let receipt = Receipt {
            profile: spec.role.profile(),
            role: spec.role,
            unit: spec.unit.clone(),
            model_requested: wanted.model.clone(),
            model_applied,
            effort_requested: wanted.effort,
            effort_applied: Effort::parse(&effort_applied)?,
        };
        receipt.verify()?;
        Ok(receipt)
    }

    async fn set_option(
        &self,
        session_id: &SessionId,
        config_id: SessionConfigId,
        value: &str,
    ) -> Result<Vec<SessionConfigOption>> {
        self.cx
            .send_request(SetSessionConfigOptionRequest::new(
                session_id.clone(),
                config_id.clone(),
                SessionConfigOptionValue::value_id(value.to_string()),
            ))
            .block_task()
            .await
            .map(|response| response.config_options)
            .map_err(|e| {
                Error::UnsupportedProfile(format!(
                    "the adapter refused to set {} to {value:?}: {e}",
                    config_id.0
                ))
            })
    }

    async fn close_session(&self, session_id: &SessionId) {
        if !self.supports_close {
            // Nothing to do: the session dies with the adapter process, and Hwahap never reuses one.
            return;
        }
        let _ = self
            .cx
            .send_request(CloseSessionRequest::new(session_id.clone()))
            .block_task()
            .await;
    }

    /// Asks the agent to abandon the current turn.
    pub fn cancel(&self, session_id: &SessionId) -> Result<()> {
        self.cx
            .send_notification(CancelNotification::new(session_id.clone()))
            .map_err(|e| Error::command("codex-acp", format!("session/cancel failed: {e}")))
    }

    fn lock(&self) -> Result<std::sync::MutexGuard<'_, Shared>> {
        self.shared
            .lock()
            .map_err(|_| Error::Internal("the ACP session state lock was poisoned".into()))
    }
}

impl crate::engine::Sessions for AgentLink {
    fn run<'a>(
        &'a self,
        spec: &'a SessionSpec,
    ) -> std::pin::Pin<Box<dyn std::future::Future<Output = Result<SessionOutcome>> + Send + 'a>>
    {
        Box::pin(self.run_session(spec))
    }
}

/// Finds a select config option in `category` that offers `wanted`, returning its id.
fn require_offered(
    options: &[SessionConfigOption],
    category: SessionConfigOptionCategory,
    wanted: &str,
) -> Result<SessionConfigId> {
    let option = options
        .iter()
        .find(|o| o.category.as_ref() == Some(&category))
        .ok_or_else(|| {
            Error::UnsupportedProfile(format!(
                "the adapter exposes no {} session option, so Hwahap cannot pin {wanted:?}",
                category_name(&category)
            ))
        })?;
    let offered = select_values(option);
    if !offered.iter().any(|v| v == wanted) {
        return Err(Error::UnsupportedProfile(format!(
            "the adapter does not offer {wanted:?} for {}; it offers {offered:?}",
            category_name(&category)
        )));
    }
    Ok(option.id.clone())
}

fn current_value(
    options: &[SessionConfigOption],
    category: SessionConfigOptionCategory,
) -> Result<String> {
    let option = options
        .iter()
        .find(|o| o.category.as_ref() == Some(&category))
        .ok_or_else(|| {
            Error::UnsupportedProfile(format!(
                "the {} session option disappeared after being set",
                category_name(&category)
            ))
        })?;
    match &option.kind {
        SessionConfigKind::Select(select) => Ok(select.current_value.0.to_string()),
        _ => Err(Error::UnsupportedProfile(format!(
            "the {} session option is not a select, so its applied value cannot be read back",
            category_name(&category)
        ))),
    }
}

fn select_values(option: &SessionConfigOption) -> Vec<String> {
    match &option.kind {
        SessionConfigKind::Select(select) => match &select.options {
            SessionConfigSelectOptions::Ungrouped(values) => {
                values.iter().map(|v| v.value.0.to_string()).collect()
            }
            SessionConfigSelectOptions::Grouped(groups) => groups
                .iter()
                .flat_map(|g| g.options.iter().map(|v| v.value.0.to_string()))
                .collect(),
            // The enum is #[non_exhaustive]; an unknown shape offers nothing we can verify, and
            // "nothing offered" is exactly the fail-closed answer.
            _ => Vec::new(),
        },
        _ => Vec::new(),
    }
}

fn category_name(category: &SessionConfigOptionCategory) -> &'static str {
    match category {
        SessionConfigOptionCategory::Model => "model",
        SessionConfigOptionCategory::ThoughtLevel => "reasoning effort",
        SessionConfigOptionCategory::Mode => "mode",
        SessionConfigOptionCategory::ModelConfig => "model config",
        _ => "unknown",
    }
}

fn stop_reason_name(reason: &StopReason) -> String {
    match reason {
        StopReason::EndTurn => "end_turn",
        StopReason::MaxTokens => "max_tokens",
        StopReason::MaxTurnRequests => "max_turn_requests",
        StopReason::Refusal => "refusal",
        StopReason::Cancelled => "cancelled",
        _ => "unknown",
    }
    .to_string()
}

fn record_notification(shared: &Arc<Mutex<Shared>>, notification: &SessionNotification) {
    let SessionUpdate::AgentMessageChunk(ContentChunk {
        content: ContentBlock::Text(TextContent { text, .. }),
        message_id,
        ..
    }) = &notification.update
    else {
        // Thoughts, tool calls, plans and mode changes are not the control channel. They are the
        // agent talking to itself, and Hwahap judges by git and exit status instead.
        return;
    };
    let Ok(mut state) = shared.lock() else {
        return;
    };
    state
        .transcripts
        .entry(notification.session_id.0.to_string())
        .or_default()
        .push((message_id.as_ref().map(ToString::to_string), text.clone()));
}

fn decide_permission(
    shared: &Arc<Mutex<Shared>>,
    request: &RequestPermissionRequest,
) -> RequestPermissionResponse {
    let key = request.session_id.0.to_string();
    let access = shared
        .lock()
        .ok()
        .and_then(|state| state.access.get(&key).copied())
        // An unknown session is not a session Hwahap opened, so it gets the strictest answer.
        .unwrap_or(Access::ReadOnly);

    let chosen = match access {
        Access::ReadOnly => pick(&request.options, PermissionOptionKind::RejectOnce)
            .or_else(|| pick(&request.options, PermissionOptionKind::RejectAlways)),
        // Never `AllowAlways`: a remembered grant would outlive the unit that justified it.
        Access::WorkspaceWrite => pick(&request.options, PermissionOptionKind::AllowOnce),
    };

    if let Ok(mut state) = shared.lock() {
        state
            .permissions
            .entry(key)
            .or_default()
            .push(PermissionRecord {
                tool: request
                    .tool_call
                    .fields
                    .title
                    .clone()
                    .unwrap_or_else(|| request.tool_call.tool_call_id.0.to_string()),
                granted: matches!(access, Access::WorkspaceWrite) && chosen.is_some(),
            });
    }

    match chosen {
        Some(option) => RequestPermissionResponse::new(RequestPermissionOutcome::Selected(
            SelectedPermissionOutcome::new(option),
        )),
        // No option matched the policy, so refuse the whole turn rather than pick something else.
        None => RequestPermissionResponse::new(RequestPermissionOutcome::Cancelled),
    }
}

fn pick(
    options: &[PermissionOption],
    kind: PermissionOptionKind,
) -> Option<agent_client_protocol::schema::v1::PermissionOptionId> {
    options
        .iter()
        .find(|o| o.kind == kind)
        .map(|o| o.option_id.clone())
}

/// The final message: the trailing run of chunks that share the last message id.
///
/// Agents emit reasoning and then a conclusion as separate messages. Concatenating everything would
/// hand the strict-JSON parser a transcript, so only the last message counts.
fn final_message(chunks: &[(Option<String>, String)]) -> String {
    let Some((last_id, _)) = chunks.last() else {
        return String::new();
    };
    chunks
        .iter()
        .rev()
        .take_while(|(id, _)| id == last_id)
        .collect::<Vec<_>>()
        .into_iter()
        .rev()
        .map(|(_, text)| text.as_str())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn only_the_two_writing_roles_may_write() {
        for role in Role::ALL {
            let expected = match role {
                Role::Implementer | Role::Rework => Access::WorkspaceWrite,
                _ => Access::ReadOnly,
            };
            assert_eq!(access_for(role), expected, "wrong access for {role:?}");
        }
        assert_eq!(
            Role::ALL
                .iter()
                .filter(|r| access_for(**r) == Access::WorkspaceWrite)
                .count(),
            2
        );
    }

    #[test]
    fn a_floating_adapter_version_is_rejected() {
        let adapter = Adapter::new(
            "npx",
            vec!["-y".into(), "@agentclientprotocol/codex-acp@latest".into()],
        );
        let err = adapter.require_pinned().unwrap_err().to_string();
        assert!(err.contains("@latest"), "{err}");
        assert!(err.contains("pinned"), "{err}");
    }

    #[test]
    fn a_pinned_adapter_is_accepted() {
        Adapter::new(
            "npx",
            vec!["-y".into(), "@agentclientprotocol/codex-acp@1.7.0".into()],
        )
        .require_pinned()
        .unwrap();
        Adapter::new("codex-acp", vec![]).require_pinned().unwrap();
    }

    #[test]
    fn the_adapter_environment_is_an_explicit_allowlist() {
        let adapter = Adapter::new("codex-acp", vec![])
            .with_env("CODEX_HOME", "/home/u/.codex")
            .with_env("PATH", "/usr/bin");
        assert_eq!(adapter.env.len(), 2);
        assert_eq!(
            adapter.env.get("CODEX_HOME").map(String::as_str),
            Some("/home/u/.codex")
        );
        // A BTreeMap keeps the child's environment ordering deterministic across runs.
        assert_eq!(
            adapter.env.keys().collect::<Vec<_>>(),
            vec!["CODEX_HOME", "PATH"]
        );
    }

    #[test]
    fn the_final_message_is_the_last_message_not_the_transcript() {
        let chunks = vec![
            (Some("m1".into()), "thinking about it".into()),
            (Some("m2".into()), r#"{"status":"#.to_string()),
            (
                Some("m2".into()),
                r#""completed","summary":"done"}"#.to_string(),
            ),
        ];
        assert_eq!(
            final_message(&chunks),
            r#"{"status":"completed","summary":"done"}"#
        );
    }

    #[test]
    fn an_empty_transcript_has_an_empty_final_message() {
        assert_eq!(final_message(&[]), "");
    }

    #[test]
    fn chunks_without_message_ids_form_one_message() {
        let chunks = vec![
            (None, "{\"verdict\":".to_string()),
            (None, "\"pass\"}".to_string()),
        ];
        assert_eq!(final_message(&chunks), r#"{"verdict":"pass"}"#);
    }

    #[test]
    fn a_single_trailing_message_wins_over_many_earlier_ones() {
        let chunks = vec![
            (Some("a".into()), "one".into()),
            (Some("b".into()), "two".into()),
            (Some("c".into()), "three".into()),
        ];
        assert_eq!(final_message(&chunks), "three");
    }

    #[test]
    fn a_repeated_message_id_after_a_gap_does_not_merge_backwards() {
        // Ids can repeat; only the contiguous trailing run is the final message.
        let chunks = vec![
            (Some("m1".into()), "early".into()),
            (Some("m2".into()), "middle".into()),
            (Some("m1".into()), "late".into()),
        ];
        assert_eq!(final_message(&chunks), "late");
    }

    #[test]
    fn stop_reasons_map_to_their_wire_names() {
        assert_eq!(stop_reason_name(&StopReason::EndTurn), "end_turn");
        assert_eq!(stop_reason_name(&StopReason::MaxTokens), "max_tokens");
        assert_eq!(
            stop_reason_name(&StopReason::MaxTurnRequests),
            "max_turn_requests"
        );
        assert_eq!(stop_reason_name(&StopReason::Refusal), "refusal");
        assert_eq!(stop_reason_name(&StopReason::Cancelled), "cancelled");
    }

    #[test]
    fn category_names_are_human_readable() {
        assert_eq!(category_name(&SessionConfigOptionCategory::Model), "model");
        assert_eq!(
            category_name(&SessionConfigOptionCategory::ThoughtLevel),
            "reasoning effort"
        );
    }
}
