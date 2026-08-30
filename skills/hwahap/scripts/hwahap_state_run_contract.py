"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _validate_run_contract(args: argparse.Namespace, workspace: Path, contract: dict,
                           run: dict, errors: list[str]) -> tuple[object, object, object]:
    try:
        installed_profiles = verify_installed_agents(workspace)
    except HwahapError as exc:
        if exc.code == "HW_AGENT_CONFIG_INVALID":
            raise
        errors.append("installed Hwahap profiles are invalid")
        installed_profiles = {}
    if contract.get("schema_version") != 1 or run.get("schema_version") != 1:
        errors.append("schema_version must be 1")
    if contract.get("goal_id") != args.run_id or run.get("goal_id") != args.run_id:
        errors.append("goal_id mismatch")
    spec = contract.get("spec")
    if not isinstance(spec, dict):
        errors.append("spec must be an object")
        spec = {}
    if (not required_text(spec.get("source"))
            or not re.fullmatch(r"[0-9a-f]{64}", str(spec.get("sha256", "")))
            or not required_text(spec.get("confirmed_at"))):
        errors.append("approved spec evidence is incomplete")
    else:
        validate_approved_spec(workspace, spec, contract, errors)
    status = run.get("status")
    if (not isinstance(status, str) or status not in RUN_STATES
            or run.get("roles") != ROLE_MAP or run.get("agent_profiles") != installed_profiles):
        errors.append("run status, role map, or agent profiles are invalid")
    if isinstance(status, str) and status in RUN_FAILURE_STATES:
        validate_failure(run.get("failure"), "run", errors)
    elif run.get("failure") is not None:
        errors.append("non-failure run must not contain failure")
    validate_goal_link(run.get("goal_link"), errors)
    goal_link = run.get("goal_link")
    current_goal = goal_link.get("current") if isinstance(goal_link, dict) else None
    validate_improvement_candidates(run.get("improvement_candidates"), errors)
    locked = contract.get("locked")
    if not isinstance(locked, bool):
        errors.append("locked must be a boolean")
    if locked and (not isinstance(current_goal, dict)
                   or current_goal.get("mode") != "bound"):
        errors.append("locked contract requires a bound Goal")
    if locked and any(not isinstance(contract.get(field), list) or not contract[field]
                      for field in CONTRACT_LISTS):
        errors.append("locked contract fields must be nonempty")
    commands = contract.get("test_commands")
    if isinstance(commands, list) and any(not safe_test_command(command) for command in commands):
        errors.append("credential-bearing test command is unsafe")
    for field in ("allowed_paths", "forbidden_changes"):
        values = contract.get(field)
        if isinstance(values, list):
            if any(not safe_relative_path(value) for value in values):
                errors.append(f"contract.{field} contains an unsafe path")
        else:
            errors.append(f"contract.{field} must be a list")
    lock_digest = contract.get("lock_sha256")
    if locked and (not isinstance(lock_digest, str) or not SHA256.fullmatch(lock_digest)):
        errors.append("locked contract requires lock_sha256")
    elif locked and lock_digest != canonical_contract_digest(contract):
        errors.append("lock_sha256 does not match contract")
    elif not locked and lock_digest is not None:
        errors.append("unlocked contract lock_sha256 must be null")
    return status, locked, contract.get("forbidden_changes")
