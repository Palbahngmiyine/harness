"""Assemble normalized report sections without filtering their ledgers."""


def assemble(contract, run, units, timeline, digests, candidates, scope_audit):
    reviews = [{"unit_id": item.get("unit_id"),
                "history": item.get("review_history", [])} for item in units]
    receipts = [{"unit_id": item.get("unit_id"),
                 "receipts": item.get("test_receipts", [])} for item in units]
    commands = [command for item in units
                for command in item.get("acceptance_commands", [])
                if isinstance(command, dict)]
    failures = [{
        "unit_id": item.get("unit_id"),
        "failure": item.get("failure", {}),
        "recovery": item.get("recovery", {}),
        "improvement_history": item.get("improvement_history", []),
    } for item in units]
    return {
        "schema_version": 2,
        "scope_audit": scope_audit,
        "summary": {"goal": contract.get("goal"), "status": run.get("status"),
                    "run_id": run.get("goal_id")},
        "contract": contract,
        "agents": {"roles": run["roles"], "profiles": run["agent_profiles"]},
        "units": units,
        "timeline": timeline,
        "reviews": {"units": reviews, "final_review": run["final_review"]},
        "tests-metrics": {"metrics": run["metrics"],
                          "acceptance_commands": commands, "test_receipts": receipts},
        "failures-recovery": failures,
        "deviations": {"items": run["deviations"],
                       "deferred_security": run["deferred_security"]},
        "provenance": {"fast_status": run.get("fast_status"),
            "spec": contract.get("spec", {}), "agent_profiles": run["agent_profiles"],
            "goal_link": run["goal_link"], "state_digests": digests},
        "improvement-candidates": candidates,
        "next-actions": _next_actions(run, units),
    }


def _next_actions(run, units):
    from hwahap_report_payload import _next_actions as next_actions
    return next_actions(run, units)
