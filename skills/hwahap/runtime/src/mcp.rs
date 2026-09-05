//! The MCP surface: exactly three tools, and the instructions that govern them.
//!
//! The host sees `hwahap_step`, `hwahap_status`, and `hwahap_ship` and nothing else. There is no
//! `plan`, `cycle`, `retry`, `create_unit`, `spawn_worker`, or `integrate` tool, because every one
//! of those would hand a scheduling or approval decision back to the calling model. The state
//! machine decides; the host executes the explicit native dispatch protocol.
//!
//! [`INSTRUCTIONS`] is the single source of the cross-tool protocol. The skill file does not repeat
//! it, and neither does any reference document: one rule, one place.

use std::path::PathBuf;

use rmcp::handler::server::router::tool::ToolRouter;
use rmcp::handler::server::wrapper::Parameters;
use rmcp::model::{Implementation, ServerCapabilities, ServerInfo};
use rmcp::{tool, tool_handler, tool_router, ErrorData, Json, ServerHandler};
use schemars::JsonSchema;
use serde::{Deserialize, Serialize};

use crate::engine::StepOutcome;
use crate::error::Error;
use crate::git::Git;
use crate::native::{NativeCompletion, NativeDispatch, NativeHost, NativeInput, NativeProgress, NativeRegistration, NativeStopped};

/// The cross-tool protocol, returned in the MCP `initialize` response.
///
/// The first paragraph stands alone: a host that reads only the opening of this string still learns
/// the loop it must run and the one thing it must never do.
pub const INSTRUCTIONS: &str = "\
Hwahap turns an implementation request into a confirmed plan and then builds it autonomously. Call \
hwahap_step and follow its `next` field: `continue` means call hwahap_step again immediately \
without asking the user; `await_user` means show `message` and wait; `completed` and `blocked` mean \
show `message` and stop. Pass the user's reply verbatim in `user_input`. Never compose, complete, \
or infer a CONFIRM PLAN or SHIP line on the user's behalf — only the user may type one.

For `native_dispatch`, use the returned native_dispatch exactly. If coordinator_allowed is true \
and you are already Astra, register agent_id `coordinator` and perform only that planning role. \
Otherwise spawn exactly one fresh Codex native sub-agent with task_name=hwahap_<dispatch_id>, \
fork_turns=none, the specified model \
and effort, and the exact brief. Never silently substitute models or inherit conversation history. \
If native spawn/wait tools are unavailable, report that limitation; never fabricate a child result \
or launch an ACP/CLI replacement. \
Immediately call hwahap_step with registration={dispatch_id,agent_id}, then wait for that child. \
Do not spawn a second child for a dispatch with an agent_id. For `native_wait`, wait on the registered \
child, or poll hwahap_step after one second when no child is pending. Once the child has stopped and \
its commands have ended, pass its exact final text via completion={dispatch_id,agent_id,final_message,\
agent_stopped:true,reported_usage:null}. Report token usage only if native tools actually expose it; \
never estimate or ask the child to invent counters. Model/effort and read-only access are host \
requests, not independently verified sandbox or applied-model evidence.

For `native_stop`, stop the named child and all remaining commands before sending \
stopped={dispatch_id,agent_id,all_work_stopped:true}. If no agent_id was registered, locate and stop \
any child you may have spawned for this exact dispatch. Never acknowledge an uncertain stop. \
Hwahap owns code edits, test execution, commits and PRs. Outside a dispatch, do not edit files, \
run tests, spawn agents or create branches/PRs. Final reviews always require an independent child.

There are two human gates and no others. `CONFIRM PLAN <challenge>` freezes the plan; after that, a \
normal cycle asks the user nothing until it finishes. `SHIP <challenge>` marks the finished draft \
pull request ready for review. Both challenges are printed by Hwahap and are bound to exact \
content, so a challenge that does not match is rejected rather than corrected.

hwahap_status reads the run and changes nothing. hwahap_ship is the only consequential action, and \
it refuses unless the user typed the exact SHIP line, the pull request head is unchanged, required \
checks pass, and the final review is still fresh.";

/// Arguments to `hwahap_step`.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub struct StepArgs {
    /// Absolute path to the repository Hwahap should work in.
    pub cwd: String,
    /// The user's implementation request. Supply it only when starting a new run.
    #[serde(default)]
    pub request: Option<String>,
    /// The user's message, verbatim. Never paraphrase, complete, or invent it.
    #[serde(default)]
    pub user_input: Option<String>,
    /// Record the native child immediately after spawning it.
    #[serde(default)]
    pub registration: Option<NativeRegistration>,
    /// Relay an exact terminal native result; absent usage remains unknown.
    #[serde(default)]
    pub completion: Option<NativeCompletion>,
    /// Confirm an orphan and its commands have stopped before recovery.
    #[serde(default)]
    pub stopped: Option<NativeStopped>,
}

/// Arguments to `hwahap_status`.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub struct StatusArgs {
    /// Absolute path to the repository whose run should be reported.
    pub cwd: String,
}

/// Arguments to `hwahap_ship`.
#[derive(Debug, Clone, Deserialize, JsonSchema)]
pub struct ShipArgs {
    /// Absolute path to the repository holding the finished run.
    pub cwd: String,
    /// The user's exact `SHIP <challenge>` line. Hwahap rejects anything else.
    pub confirmation: String,
}

/// What every tool returns.
#[derive(Debug, Clone, Serialize, JsonSchema)]
pub struct RunReport {
    /// The run's stable identifier.
    pub run_id: String,
    /// `plan`, `build`, or `review`.
    pub phase: String,
    /// The engine state, for diagnostics.
    pub state: String,
    /// `continue`, `await_user`, `completed`, `blocked`, or a `native_*` protocol action.
    pub next: String,
    /// The text to show the user.
    pub message: String,
    /// The frozen plan's digest, once there is one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plan_digest: Option<String>,
    /// The draft pull request, once there is one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pr_url: Option<String>,
    /// The exact native request, present while dispatching, waiting or stopping a child.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub native_dispatch: Option<NativeDispatch>,
}

impl From<StepOutcome> for RunReport {
    fn from(outcome: StepOutcome) -> Self {
        RunReport {
            run_id: outcome.run_id,
            phase: outcome.phase,
            state: outcome.state,
            next: outcome.next,
            message: outcome.message,
            plan_digest: outcome.plan_digest,
            pr_url: outcome.pr_url,
            native_dispatch: None,
        }
    }
}

impl From<NativeProgress> for RunReport {
    fn from(progress: NativeProgress) -> Self {
        let mut report = RunReport::from(progress.outcome);
        report.native_dispatch = progress.dispatch;
        report
    }
}

/// The MCP server.
///
/// NativeHost owns background continuations and repository locks. Tool requests return promptly;
/// status reads a snapshot while a native child or test command is running.
#[derive(Clone)]
pub struct Hwahap {
    tool_router: ToolRouter<Self>,
    native: std::sync::Arc<NativeHost>,
}

impl Default for Hwahap {
    fn default() -> Self {
        Self::new()
    }
}

// `vis = "pub"` because the generated constructor is private by default, which would put the
// "exactly three tools" gate out of reach of an integration test.
#[tool_router(router = tool_router, vis = "pub")]
impl Hwahap {
    pub fn new() -> Self {
        Hwahap {
            tool_router: Self::tool_router(),
            native: std::sync::Arc::new(NativeHost::default()),
        }
    }

    /// Start or advance the one active Hwahap run in this repository.
    #[tool(
        name = "hwahap_step",
        description = "Start or advance the Hwahap run for a repository. Supply `request` to \
                       start, `user_input` to pass the user's exact reply, and neither to let the \
                       run continue. Returns `next`, which tells you whether to call again \
                       immediately, wait for the user, or stop.",
        annotations(
            title = "Advance the Hwahap run",
            read_only_hint = false,
            destructive_hint = false,
            idempotent_hint = false,
            open_world_hint = true
        )
    )]
    async fn step(
        &self,
        Parameters(args): Parameters<StepArgs>,
    ) -> Result<Json<RunReport>, ErrorData> {
        let root = root_for(&args.cwd)?;
        let outcome = self.native
            .advance(&root, NativeInput {
                request: args.request, user_input: args.user_input, registration: args.registration,
                completion: args.completion, stopped: args.stopped,
            })
            .await
            .map_err(to_error_data)?;
        Ok(Json(outcome.into()))
    }

    /// Report the run without changing it.
    #[tool(
        name = "hwahap_status",
        description = "Report the state of the Hwahap run in a repository without changing \
                       anything. Use this to answer 'how is it going?' during autonomous coding.",
        annotations(
            title = "Read the Hwahap run",
            read_only_hint = true,
            destructive_hint = false,
            idempotent_hint = true,
            open_world_hint = false
        )
    )]
    async fn status(
        &self,
        Parameters(args): Parameters<StatusArgs>,
    ) -> Result<Json<RunReport>, ErrorData> {
        let root = root_for(&args.cwd)?;
        let outcome = self.native.status(&root).await.map_err(to_error_data)?;
        Ok(Json(outcome.into()))
    }

    /// Mark the finished draft pull request ready for review.
    #[tool(
        name = "hwahap_ship",
        description = "Mark the finished draft pull request ready for review. Call this only after \
                       the user has typed an exact `SHIP <challenge>` line themselves; pass that \
                       line verbatim as `confirmation`. Hwahap does not merge and does not enable \
                       auto-merge.",
        annotations(
            title = "Ship the draft pull request",
            read_only_hint = false,
            destructive_hint = false,
            idempotent_hint = true,
            open_world_hint = true
        )
    )]
    async fn ship(
        &self,
        Parameters(args): Parameters<ShipArgs>,
    ) -> Result<Json<RunReport>, ErrorData> {
        let root = root_for(&args.cwd)?;
        let outcome = self.native.ship(&root, &args.confirmation).await.map_err(to_error_data)?;
        Ok(Json(outcome.into()))
    }
}

#[tool_handler(router = self.tool_router)]
impl ServerHandler for Hwahap {
    fn get_info(&self) -> ServerInfo {
        // Written by hand rather than synthesized by the macro: without an explicit name the
        // generated version identifies the server as "rmcp", because the `env!` calls expand
        // inside the rmcp crate.
        ServerInfo::new(ServerCapabilities::builder().enable_tools().build())
            .with_server_info(Implementation::new("hwahap", env!("CARGO_PKG_VERSION")))
            .with_instructions(INSTRUCTIONS)
    }
}

#[cfg(test)]
fn engine_for(cwd: &str) -> Result<crate::engine::Engine, ErrorData> {
    crate::engine::Engine::open(&root_for(cwd)?).map_err(to_error_data)
}

fn root_for(cwd: &str) -> Result<PathBuf, ErrorData> {
    let path = PathBuf::from(cwd);
    if !path.is_absolute() {
        return Err(ErrorData::invalid_params(
            format!("cwd must be an absolute path, got {cwd:?}"),
            None,
        ));
    }
    Git::open(&path).map(|git| git.root().to_path_buf()).map_err(to_error_data)
}

/// Maps a Hwahap error onto the MCP error the host will render.
///
/// Bad arguments are protocol errors; everything else is a run-level failure the user needs to
/// read, so it keeps its own message.
fn to_error_data(error: Error) -> ErrorData {
    match error {
        Error::Rejected(message) => ErrorData::invalid_params(message, None),
        other => ErrorData::internal_error(other.to_string(), None),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn there_are_exactly_three_tools() {
        let tools = Hwahap::tool_router().list_all();
        let names: Vec<&str> = tools.iter().map(|t| t.name.as_ref()).collect();
        assert_eq!(names, vec!["hwahap_ship", "hwahap_status", "hwahap_step"]);
    }

    #[test]
    fn exactly_one_tool_is_read_only() {
        let read_only: Vec<String> = Hwahap::tool_router()
            .list_all()
            .iter()
            .filter(|t| {
                t.annotations
                    .as_ref()
                    .and_then(|a| a.read_only_hint)
                    .unwrap_or(false)
            })
            .map(|t| t.name.to_string())
            .collect();
        assert_eq!(read_only, vec!["hwahap_status".to_string()]);
    }

    #[test]
    fn no_tool_is_marked_destructive() {
        // Hwahap creates a branch and a draft PR; it never deletes or merges. A destructive hint
        // would ask the host to gate work that is in fact reversible.
        for tool in Hwahap::tool_router().list_all() {
            let destructive = tool.annotations.as_ref().and_then(|a| a.destructive_hint);
            assert_eq!(
                destructive,
                Some(false),
                "{} claims to be destructive",
                tool.name
            );
        }
    }

    #[test]
    fn every_tool_has_a_description_and_a_title() {
        for tool in Hwahap::tool_router().list_all() {
            let description = tool.description.as_deref().unwrap_or_default();
            assert!(
                description.len() > 40,
                "{} has a thin description",
                tool.name
            );
            assert!(
                tool.annotations
                    .as_ref()
                    .and_then(|a| a.title.as_deref())
                    .is_some(),
                "{} has no title",
                tool.name
            );
        }
    }

    #[test]
    fn tool_descriptions_do_not_overlap() {
        // Two tools whose descriptions could each answer the same question make the host guess.
        let tools = Hwahap::tool_router().list_all();
        for a in &tools {
            for b in &tools {
                if a.name >= b.name {
                    continue;
                }
                assert_ne!(
                    a.description, b.description,
                    "{} and {} share a description",
                    a.name, b.name
                );
            }
        }
    }

    #[test]
    fn the_server_identifies_itself_and_not_rmcp() {
        let info = Hwahap::new().get_info();
        assert_eq!(info.server_info.name, "hwahap");
        assert_eq!(info.server_info.version, env!("CARGO_PKG_VERSION"));
    }

    #[test]
    fn the_instructions_are_advertised_and_self_contained_at_the_front() {
        let info = Hwahap::new().get_info();
        let instructions = info.instructions.expect("instructions must be advertised");
        assert_eq!(instructions, INSTRUCTIONS);

        let opening: String = instructions.chars().take(512).collect();
        for expected in [
            "hwahap_step",
            "continue",
            "await_user",
            "CONFIRM PLAN",
            "SHIP",
        ] {
            assert!(
                opening.contains(expected),
                "the first 512 chars omit {expected:?}"
            );
        }
    }

    #[test]
    fn the_instructions_name_every_tool() {
        for tool in Hwahap::tool_router().list_all() {
            assert!(
                INSTRUCTIONS.contains(tool.name.as_ref()),
                "the instructions never mention {}",
                tool.name
            );
        }
    }

    #[test]
    fn the_instructions_forbid_the_host_from_inventing_a_confirmation() {
        assert!(INSTRUCTIONS.contains("Never compose, complete, or infer"));
        assert!(INSTRUCTIONS.contains("only the user may type one"));
    }

    #[test]
    fn a_relative_cwd_is_rejected_as_a_parameter_error() {
        let Err(err) = engine_for("relative/path") else {
            panic!("a relative cwd must be rejected");
        };
        assert_eq!(err.code, rmcp::model::ErrorCode::INVALID_PARAMS);
        assert!(err.message.contains("absolute"), "{}", err.message);
    }

    #[test]
    fn a_rejection_becomes_invalid_params_and_anything_else_becomes_internal_error() {
        assert_eq!(
            to_error_data(Error::Rejected("no".into())).code,
            rmcp::model::ErrorCode::INVALID_PARAMS
        );
        assert_eq!(
            to_error_data(Error::UnsupportedProfile("x".into())).code,
            rmcp::model::ErrorCode::INTERNAL_ERROR
        );
        assert!(to_error_data(Error::UnsupportedProfile("x".into()))
            .message
            .contains("unsupported_profile"));
    }

    #[test]
    fn the_step_tool_derives_an_input_schema_that_requires_only_cwd() {
        let tool = Hwahap::step_tool_attr();
        let schema = serde_json::to_value(&tool.input_schema).unwrap();
        let required = schema
            .get("required")
            .and_then(|r| r.as_array())
            .cloned()
            .unwrap_or_default();
        let required: Vec<&str> = required.iter().filter_map(|v| v.as_str()).collect();
        assert_eq!(required, vec!["cwd"]);
        let properties = schema
            .get("properties")
            .and_then(|p| p.as_object())
            .unwrap();
        assert!(properties.contains_key("request"));
        assert!(properties.contains_key("user_input"));
    }

    #[test]
    fn the_ship_tool_requires_the_users_confirmation_line() {
        let tool = Hwahap::ship_tool_attr();
        let schema = serde_json::to_value(&tool.input_schema).unwrap();
        let required: Vec<String> = schema
            .get("required")
            .and_then(|r| r.as_array())
            .map(|a| {
                a.iter()
                    .filter_map(|v| v.as_str().map(str::to_string))
                    .collect()
            })
            .unwrap_or_default();
        assert!(
            required.contains(&"confirmation".to_string()),
            "{required:?}"
        );
        assert!(required.contains(&"cwd".to_string()), "{required:?}");
    }
}
