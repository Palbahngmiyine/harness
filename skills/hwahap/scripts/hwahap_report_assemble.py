"""Assemble normalized report sections without filtering their ledgers."""


def _next_actions(run, units):
    actions = []
    if run.get("deviations"):
        actions.append("절차 편차의 prevention을 확인하고 재발 방지를 기록하세요.")
    if run.get("deferred_security"):
        actions.append("보류된 보안 작업은 승인 전 구현하지 말고 다음 결정을 기록하세요.")
    repeated = any(sum(item.get("outcome") == "fail"
        for item in value.get("review_history", [])) >= 2 for value in units)
    if repeated:
        actions.append("반복 실패의 새 가설과 전략을 검토하세요. 개선 후보는 [보고 전용]입니다.")
    token = run.get("metrics", {}).get("token_usage", {})
    if token.get("availability") == "unavailable":
        actions.append("정확한 token aggregate가 없어 추정하지 마세요.")
    if run.get("fast_status") == "unknown":
        actions.append("Fast 상태의 관찰 증거를 다음 보고에 남기세요.")
    return actions or ["추가 조치 없음."]


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
    if run.get("failure"):
        failures.insert(0, {"unit_id": "run", "failure": run["failure"],
                            "recovery": {}, "improvement_history": []})
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
        "deviations": {"classification": "process", "items": run["deviations"],
                       "deferred_security": run["deferred_security"]},
        "provenance": {"fast_status": run.get("fast_status"),
            "spec": contract.get("spec", {}), "agent_profiles": run["agent_profiles"],
            "goal_link": run["goal_link"], "state_digests": digests},
        "improvement-candidates": candidates,
        "next-actions": _next_actions(run, units),
    }
