//! The MCP surface: exactly three tools, and the instructions that govern them.
//!
//! The host sees `hwahap_step`, `hwahap_status`, and `hwahap_ship` and nothing else. There is no
//! `plan`, `cycle`, `retry`, `create_unit`, `spawn_worker`, or `integrate` tool, because every one
//! of those would hand a scheduling or approval decision back to the calling model. The state
//! machine decides; the host only relays.
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

use crate::engine::{Engine, StepOutcome};
use crate::error::Error;

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

Hwahap owns implementation. Do not edit files, run tests, spawn agents, or create branches or pull \
requests yourself while a run is active; hwahap_step does all of it and verifies the result from \
git and exit status rather than from what any agent claims.

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
    /// `continue`, `await_user`, `completed`, or `blocked`.
    pub next: String,
    /// The text to show the user.
    pub message: String,
    /// The frozen plan's digest, once there is one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub plan_digest: Option<String>,
    /// The draft pull request, once there is one.
    #[serde(skip_serializing_if = "Option::is_none")]
    pub pr_url: Option<String>,
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
        }
    }
}

/// The MCP server.
///
/// `rmcp` dispatches tool calls concurrently and does not serialize them, so the one-active-run
/// invariant is enforced here: `step` and `ship` take [`Hwahap::engine_lock`] for their whole
/// duration. `status` deliberately does not, because it only reads files that are replaced
/// atomically, and a progress query that blocked behind an hour of autonomous coding would be
/// useless.
#[derive(Clone)]
pub struct Hwahap {
    tool_router: ToolRouter<Self>,
    engine_lock: std::sync::Arc<tokio::sync::Mutex<()>>,
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
            engine_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
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
        let _exclusive = self.engine_lock.lock().await;
        let engine = engine_for(&args.cwd)?;
        let outcome = engine
            .step(args.request.as_deref(), args.user_input.as_deref())
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
        let engine = engine_for(&args.cwd)?;
        let outcome = engine.status().map_err(to_error_data)?;
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
        let _exclusive = self.engine_lock.lock().await;
        let engine = engine_for(&args.cwd)?;
        let outcome = engine.ship(&args.confirmation).map_err(to_error_data)?;
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

fn engine_for(cwd: &str) -> Result<Engine, ErrorData> {
    let path = PathBuf::from(cwd);
    if !path.is_absolute() {
        return Err(ErrorData::invalid_params(
            format!("cwd must be an absolute path, got {cwd:?}"),
            None,
        ));
    }
    Engine::open(&path).map_err(to_error_data)
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
