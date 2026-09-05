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
//!   `blocked: unsupported_profile`, never a silent `high`. An agent that then announces a
//!   different model or effort mid-turn ends the run the same way, because the receipt exists to
//!   make a downgrade visible and cannot do that while the answer it describes is kept.
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
use agent_client_protocol::{AcpAgent, AcpAgentConfig, Agent, Client, ConnectTo, ConnectionTo};

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

    /// Rejects an adapter whose version is resolved when it is launched.
    ///
    /// A version resolved at launch means a rerun of the same frozen plan can meet a different
    /// agent. npm resolves everything that is not an exact version that way — a missing version and
    /// a dist tag both mean "whatever is newest", and every range operator means "whatever fits" —
    /// so this is an allowlist of one shape rather than a denylist of the spellings seen so far.
    pub fn require_pinned(&self) -> Result<()> {
        for spec in self.package_specifiers() {
            if !is_exact_version_spec(spec) {
                return Err(Error::Rejected(format!(
                    "the ACP adapter must be pinned to an exact version, but {spec:?} lets npm \
                     choose one at launch: {:?}",
                    self.args
                )));
            }
        }
        Ok(())
    }

    /// The arguments that name an npm package to fetch.
    ///
    /// Two shapes are recognised and nothing else is guessed at: the first non-option argument of
    /// an npm runner, which is where the runner takes its package, and a scoped `@scope/name`
    /// argument anywhere, which nothing but an npm specifier looks like. Arguments the adapter
    /// itself consumes are left alone — a value that happens to read like a package name is not one.
    fn package_specifiers(&self) -> Vec<&str> {
        let mut runner_package_seen = !matches!(
            self.command.file_stem().and_then(|stem| stem.to_str()),
            Some("npx" | "bunx" | "pnpx")
        );
        let mut specifiers = Vec::new();
        for arg in &self.args {
            // A filesystem path is pinned by being a path, and an option is not a package.
            if arg.starts_with('-') || arg.starts_with('.') || arg.starts_with('/') {
                continue;
            }
            if !runner_package_seen {
                runner_package_seen = true;
                specifiers.push(arg.as_str());
            } else if arg.starts_with('@') {
                specifiers.push(arg.as_str());
            }
        }
        specifiers
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

/// Whether an npm specifier names one exact published version.
///
/// The version is everything after the last `@` that is not the leading `@` of a scope. No `@` at
/// all is the `latest` dist tag spelled by omission, which is why it is rejected here rather than
/// waved through as "no version to check".
fn is_exact_version_spec(spec: &str) -> bool {
    match spec.rfind('@') {
        Some(at) if at > 0 => is_exact_version(&spec[at + 1..]),
        _ => false,
    }
}

/// Whether a version is one release rather than a tag or a range.
///
/// A prerelease or build suffix still names one release, so only the numeric core has to be exact.
fn is_exact_version(version: &str) -> bool {
    let core = match version.find(['-', '+']) {
        Some(suffix) => &version[..suffix],
        None => version,
    };
    let mut parts = core.split('.');
    let numbered = [parts.next(), parts.next(), parts.next()].into_iter().all(
        |part| matches!(part, Some(p) if !p.is_empty() && p.bytes().all(|b| b.is_ascii_digit())),
    );
    numbered && parts.next().is_none()
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
    /// The sessions Hwahap currently has open. A session id absent here is one it did not open or
    /// has already finished, and notifications naming it belong to no outcome.
    access: HashMap<String, Access>,
    permissions: HashMap<String, Vec<PermissionRecord>>,
    /// The verified profile per session, present only once the agent has echoed it back.
    pinned: HashMap<String, Pinned>,
}

/// The profile a session was proved to be running, and the first departure the agent announced.
///
/// The pin is recorded after the echo is verified and before the prompt is sent, so the unsolicited
/// config update an adapter emits right after `session/new` describes a session that has no pin yet
/// and is therefore not a departure from anything.
struct Pinned {
    model: String,
    effort: String,
    violation: Option<String>,
}

/// What a finished session leaves behind in [`Shared`].
struct Drained {
    chunks: Vec<(Option<String>, String)>,
    permissions: Vec<PermissionRecord>,
    violation: Option<String>,
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
    link_over(AcpAgent::new(adapter.to_config()), profiles, body).await
}

/// Runs `body` against an already-chosen transport.
///
/// The adapter process is one transport among several the SDK accepts. Naming the transport here
/// rather than inside [`with_link`] is what lets the wire behaviour this module is responsible for —
/// the profile echo, the notification window, the shutdown round trip — be exercised against a
/// scripted agent in process, with no adapter to install and no timing to guess at.
async fn link_over<T, F, R>(transport: T, profiles: &Profiles, body: F) -> Result<R>
where
    T: ConnectTo<Client> + 'static,
    F: AsyncFnOnce(AgentLink) -> Result<R>,
{
    let shared = Arc::new(Mutex::new(Shared::default()));
    let profiles = profiles.clone();

    let notify_shared = shared.clone();
    let permission_shared = shared.clone();

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
        // The turn is over when `session/prompt` answers, so that is when what the turn produced is
        // taken. Draining after the `session/close` round trip would let a chunk streamed during
        // shutdown — after the agent said `end_turn` — become the answer Hwahap parses.
        let drained = self.drain(&key);
        self.close_session(&session_id).await;

        let (stop_reason, receipt) = result?;
        let Drained {
            chunks,
            permissions,
            violation,
        } = drained?;
        if let Some(violation) = violation {
            return Err(Error::UnsupportedProfile(violation));
        }
        Ok(SessionOutcome {
            final_message: final_message(&chunks),
            transcript: chunks.iter().map(|(_, text)| text.as_str()).collect(),
            receipt,
            stop_reason,
            permissions,
        })
    }

    /// Closes a session's books: nothing recorded after this belongs to it.
    fn drain(&self, key: &str) -> Result<Drained> {
        let mut state = self.lock()?;
        state.access.remove(key);
        Ok(Drained {
            chunks: state.transcripts.remove(key).unwrap_or_default(),
            permissions: state.permissions.remove(key).unwrap_or_default(),
            violation: state.pinned.remove(key).and_then(|pinned| pinned.violation),
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
        {
            // Pinned only now: from here the agent has told Hwahap what it is running, so any
            // config update it announces during the turn is a change to something proved.
            let mut state = self.lock()?;
            state.pinned.insert(
                key.to_string(),
                Pinned {
                    model: receipt.model_applied.clone(),
                    effort: receipt.effort_applied.as_str().to_string(),
                    violation: None,
                },
            );
        }

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
    let Ok(mut state) = shared.lock() else {
        return;
    };
    let key = notification.session_id.0.to_string();
    if !state.access.contains_key(&key) {
        // A session Hwahap does not have open: an id it never created, or one whose books are
        // already closed. Neither belongs to any outcome, and recording them would grow the maps
        // for the length of the run. The agent cannot stream an answer before it is prompted, so
        // nothing an outcome needs can arrive before `run_session` records the session.
        return;
    }

    match &notification.update {
        SessionUpdate::AgentMessageChunk(ContentChunk {
            content: ContentBlock::Text(TextContent { text, .. }),
            message_id,
            ..
        }) => {
            state
                .transcripts
                .entry(key)
                .or_default()
                .push((message_id.as_ref().map(ToString::to_string), text.clone()));
        }
        SessionUpdate::ConfigOptionUpdate(update) => {
            // The one notification that bears on an invariant: it reports the session's whole
            // config, so an agent that switches model or effort mid-turn says so here. Git and exit
            // status cannot catch this — they say nothing about which model ran.
            if let Some(pinned) = state.pinned.get_mut(&key) {
                let departure = announced_departure(&update.config_options, pinned);
                if pinned.violation.is_none() {
                    pinned.violation = departure;
                }
            }
        }
        // The agent talking to itself, or about surfaces Hwahap does not drive: reasoning, tool
        // calls, plans, slash commands, modes, titles and token usage. Hwahap judges by git and
        // exit status instead. A non-text chunk lands here too — there is no JSON in an image.
        SessionUpdate::AgentMessageChunk(_)
        | SessionUpdate::UserMessageChunk(_)
        | SessionUpdate::AgentThoughtChunk(_)
        | SessionUpdate::ToolCall(_)
        | SessionUpdate::ToolCallUpdate(_)
        | SessionUpdate::Plan(_)
        | SessionUpdate::AvailableCommandsUpdate(_)
        | SessionUpdate::CurrentModeUpdate(_)
        | SessionUpdate::SessionInfoUpdate(_)
        | SessionUpdate::UsageUpdate(_) => {}
        // `SessionUpdate` is `#[non_exhaustive]`, so a variant added to the protocol lands here.
        // It is ignored until someone reads it and decides it is ignorable, which is why the
        // variants above are named rather than swept up by this arm.
        _ => {}
    }
}

/// The mid-turn departure from `pinned` that a config update announces, if it announces one.
///
/// Only a value that can be read counts: a category the update leaves out, or reports in a shape
/// with no readable current value, says nothing about what the turn is running on.
fn announced_departure(options: &[SessionConfigOption], pinned: &Pinned) -> Option<String> {
    for (category, expected) in [
        (SessionConfigOptionCategory::Model, pinned.model.as_str()),
        (
            SessionConfigOptionCategory::ThoughtLevel,
            pinned.effort.as_str(),
        ),
    ] {
        match current_value(options, category.clone()) {
            Ok(announced) if announced != expected => {
                return Some(format!(
                    "the agent announced mid-turn that the session's {} is now {announced:?}, but \
                     the run was pinned to {expected:?} and had verified it",
                    category_name(&category)
                ));
            }
            _ => {}
        }
    }
    None
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
        // Only a session Hwahap has open has an evidence trail to add to; a request naming any
        // other id is answered and forgotten rather than filed under a key nobody reads.
        if let Some(records) = state.permissions.get_mut(&key) {
            records.push(PermissionRecord {
                tool: request
                    .tool_call
                    .fields
                    .title
                    .clone()
                    .unwrap_or_else(|| request.tool_call.tool_call_id.0.to_string()),
                granted: matches!(access, Access::WorkspaceWrite) && chosen.is_some(),
            });
        }
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
