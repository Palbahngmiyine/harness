//! Hwahap v3: `PLAN -> PLAN FREEZE -> AUTONOMOUS CODING -> DRAFT PR -> ADJUST | SHIP`.
//!
//! The crate is one binary that is two things at once: a local STDIO MCP server exposing exactly
//! three tools to the host, and a durable broker for Codex native sub-agents.
//! Everything between those two edges is a deterministic state machine over files in
//! `.hwahap/`.

pub mod agentresult;
pub mod answer;
pub mod canonical;
pub mod clock;
pub mod config;
pub mod cost;
pub mod engine;
pub mod error;
pub mod forge;
pub mod frontier;
pub mod git;
pub mod mcp;
pub mod native;
pub mod plan;
pub mod pr_review;
pub mod profile;
pub mod prompts;
pub mod proposal;
pub mod render;
pub mod session;
pub mod state;
pub mod validate;

pub use error::{Error, Result};
