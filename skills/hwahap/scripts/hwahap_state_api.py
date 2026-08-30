"""Compose verified Hwahap state responsibility modules."""

import hwahap_state_agent_dependency as _agent
import hwahap_state_credential_dependency as _credential
import hwahap_state_report_entry as _report
import hwahap_state_runtime as _runtime
import hwahap_state_dependencies
import hwahap_state_config_report
import hwahap_state_config_schema
import hwahap_state_config_machine
import hwahap_state_errors_git
import hwahap_state_json_store
import hwahap_state_atomic
import hwahap_state_journal
import hwahap_state_recovery
import hwahap_state_agents
import hwahap_state_init_data
import hwahap_state_init_command
import hwahap_state_report_gateway
import hwahap_state_report_schema
import hwahap_state_terminal
import hwahap_state_complete
import hwahap_state_lock
import hwahap_state_final_units
import hwahap_state_scope_drift
import hwahap_state_add_unit
import hwahap_state_receipt
import hwahap_state_transition
import hwahap_state_improvement_command
import hwahap_state_candidate
import hwahap_state_goal_sync
import hwahap_state_goal_complete
import hwahap_state_security
import hwahap_state_goal_observation
import hwahap_state_goal_validation
import hwahap_state_review_rounds
import hwahap_state_review_history
import hwahap_state_test_validation
import hwahap_state_unit_validation
import hwahap_state_spec_validation
import hwahap_state_metrics
import hwahap_state_events
import hwahap_state_final_review
import hwahap_state_final_scope
import hwahap_state_final_lifecycle
import hwahap_state_run_contract
import hwahap_state_run_units
import hwahap_state_run_validate
import hwahap_state_parser_setup
import hwahap_state_parser_workflow
import hwahap_state_cli

_exports, _owners = _runtime.compose()
_runtime.publish("_dependency_modules", (_agent, _credential))
_runtime.publish("_report_module", _report)


def get_value(name: str):
    try:
        return _owners[name][name]
    except KeyError:
        raise AttributeError(name) from None


def set_value(name: str, value: object) -> None:
    _runtime.publish(name, value)


def has_value(name: str) -> bool:
    return name in _owners


def values() -> dict:
    return {name: space[name] for name, space in _owners.items()}
