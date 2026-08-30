"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
REPORT_SCHEMA_VERSION = 3
REPORT_GENERATOR = {"name": "hwahap-report", "version": 3, "design_system": "material-design-3"}
REPORT_REDACTION_POLICY = "hwahap-report-v3"
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
RUN_STATES = {
    "initialized", "contract_locked", "implementing", "reviewing", "recovering",
    "replanning", "final_review", "completed", "blocked", "failed",
    "awaiting_user", "cancelled",
}
UNIT_STATES = {
    "planned", "implementing", "reviewing", "recovery", "replan_required",
    "passed", "blocked", "failed", "awaiting_user",
}
FAILURE_STATES = {"replan_required", "blocked", "failed", "awaiting_user"}
RUN_FAILURE_STATES = {"blocked", "failed", "awaiting_user"}
FAILURE_CODES = {
    "HW_AGENT_CONFIG_INVALID",
    "HW_SPEC_UNCONFIRMED", "HW_REQUEST_UNCONFIRMED", "HW_GOAL_REQUIRED", "HW_SCOPE_DRIFT", "HW_IMPLEMENTATION_BLOCKED",
    "HW_IMPLEMENTATION_FAILED", "HW_VERIFICATION_FAILED", "HW_REPLAN_REQUIRED",
    "HW_FINAL_REVIEW_FAILED", "HW_MODEL_UNAVAILABLE", "HW_USER_DECISION_REQUIRED",
    "HW_STATE_INVALID", "HW_REPORT_GENERATION_FAILED", "HW_TEST_EXECUTION_DISABLED",
}
PUBLIC_ERROR_MESSAGES = {
    code: message for code, message in {
        "HW_AGENT_CONFIG_INVALID": "installed agent configuration is invalid",
        "HW_SPEC_UNCONFIRMED": "approved specification is unavailable or invalid",
        "HW_REQUEST_UNCONFIRMED": "implementation request is unavailable or invalid",
        "HW_GOAL_REQUIRED": "a bound Goal is required before locking a request run",
        "HW_SCOPE_DRIFT": "requested change is outside the locked scope",
        "HW_IMPLEMENTATION_BLOCKED": "implementation is blocked",
        "HW_IMPLEMENTATION_FAILED": "implementation failed",
        "HW_VERIFICATION_FAILED": "verification failed",
        "HW_REPLAN_REQUIRED": "replanning is required",
        "HW_FINAL_REVIEW_FAILED": "final review failed",
        "HW_MODEL_UNAVAILABLE": "required model is unavailable",
        "HW_USER_DECISION_REQUIRED": "user decision is required",
        "HW_STATE_INVALID": "state is invalid",
        "HW_REPORT_GENERATION_FAILED": "report generation failed",
        "HW_TEST_EXECUTION_DISABLED": "test execution is disabled",
        "HW_RUN_EXISTS": "run already exists",
    }.items() if code in FAILURE_CODES or code == "HW_RUN_EXISTS"
}
