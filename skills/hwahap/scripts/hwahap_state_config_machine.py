"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
GOAL_MODES = {"unobserved", "bound", "no_active_goal", "unavailable"}
RUN_TERMINAL_STATES = {"completed", "blocked", "failed", "awaiting_user", "cancelled"}
RUN_UNIT_MUTATION_BLOCKED_STATES = RUN_TERMINAL_STATES | {"final_review"}
UNIT_TERMINAL_STATES = {"passed", "blocked", "failed", "awaiting_user"}
RUN_TRANSITIONS = {
    "initialized": {"contract_locked", "blocked", "failed", "awaiting_user", "cancelled"},
    "contract_locked": {"implementing", "blocked", "failed", "awaiting_user", "cancelled"},
    "implementing": {"reviewing", "recovering", "replanning", "blocked", "failed", "awaiting_user"},
    "reviewing": {"implementing", "recovering", "final_review", "replanning", "blocked", "failed", "awaiting_user"},
    "recovering": {"implementing", "reviewing", "replanning", "blocked", "failed", "awaiting_user"},
    "replanning": {"implementing", "blocked", "failed", "awaiting_user"},
    "final_review": {"completed", "awaiting_user"},
}
UNIT_TRANSITIONS = {
    "planned": {"implementing", "blocked", "failed", "awaiting_user"},
    "implementing": {"reviewing", "recovery", "failed", "blocked", "awaiting_user"},
    "reviewing": {"passed", "recovery", "replan_required", "failed", "blocked", "awaiting_user"},
    "recovery": {"implementing", "reviewing", "replan_required", "failed", "blocked", "awaiting_user"},
    "replan_required": {"implementing", "awaiting_user"},
}
AGENT_PROFILE_DIR = Path(__file__).resolve().parents[1] / "assets" / "agents"
SCOPE_DRIFT_ACTOR = "hwahap-sol-orchestrator"
SCOPE_DRIFT_REASON = "requested unit input is not an exact member of the locked contract; waiting for user decision"
SCOPE_DRIFT_RECOVERY = "ask the user to approve a new Goal/contract or provide a corrected in-scope unit"
SCOPE_DRIFT_EVIDENCE_LIMIT = 3
SCOPE_DRIFT_TEXT_LIMIT = 256
