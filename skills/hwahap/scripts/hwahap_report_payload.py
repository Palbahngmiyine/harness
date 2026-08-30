"""Build the allowlisted canonical report payload."""

from pathlib import Path

from hwahap_report_assemble import assemble
from hwahap_report_clean import clean, pick, scope_audit, snapshot
from hwahap_report_goal import goal_link, improvement_candidates
from hwahap_report_security import text
from hwahap_report_types import CONTRACT_LISTS, EVENT_FIELDS, SHA256
from hwahap_report_unit import command_receipts, roles, unit


def _next_actions(run: dict, units: list[dict]) -> list[str]:
    actions = []
    if run.get("deviations"):
        actions.append("범위 편차의 prevention을 확인하고 재발 방지를 기록하세요.")
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


def _run_data(run: dict, root: str) -> dict:
    data = pick(run, ("schema_version", "goal_id", "status", "started_at",
                       "completed_at", "fast_status"), root)
    data["roles"] = roles(run.get("roles"), root)
    profiles = run.get("agent_profiles") if isinstance(run.get("agent_profiles"), dict) else {}
    data["agent_profiles"] = {key: clean(value, root)
        for key, value in profiles.items() if isinstance(key, str)
        and key.endswith(".toml") and isinstance(value, str) and SHA256.fullmatch(value)}
    metrics = pick(run.get("metrics"), ("unit_count", "agent_runs", "review_rounds",
        "recoveries", "replans", "scope_deviations", "test_runs", "elapsed_seconds"), root)
    token = pick(run.get("metrics", {}).get("token_usage"),
        ("availability", "reason", "source", "total"), root)
    data["metrics"] = metrics | {"token_usage": token}
    data["deviations"] = [pick(item,
        ("summary", "root_cause", "impact", "prevention", "evidence"), root)
        for item in run.get("deviations", [])]
    data["deferred_security"] = [pick(item,
        ("summary", "reason", "next_action", "evidence"), root)
        for item in run.get("deferred_security", [])]
    final = run.get("final_review") if isinstance(run.get("final_review"), dict) else {}
    attempts = []
    for item in final.get("attempts", []):
        attempt = pick(item, ("model", "effort", "status", "thread_id",
                               "diff_digest", "evidence"), root)
        value = snapshot(item.get("diff_snapshot"), root)
        if value:
            attempt["diff_snapshot"] = value
        attempts.append(attempt)
    data["final_review"] = pick(final, ("status",), root) | {"attempts": attempts}
    data["goal_link"] = goal_link(run.get("goal_link"), root)
    return data


def build_payload(workspace, contract, run, units, events, state_digests,
                  scope_audit_data=None) -> dict:
    root = str(Path(workspace).absolute())
    spec = pick(contract.get("spec"), ("source", "sha256", "confirmed_at", "status"), root)
    contract_data = pick(contract,
        ("schema_version", "goal_id", "goal", "locked", "lock_sha256"), root)
    contract_data.update({key: clean(contract.get(key, []), root)
                          for key in CONTRACT_LISTS})
    contract_data["test_commands"] = command_receipts(
        contract.get("test_commands"), "test-command")
    data = _run_data(run, root)
    units = sorted([unit(item, root) for item in units if isinstance(item, dict)],
                   key=lambda item: item.get("unit_id", ""))
    digests = state_digests if isinstance(state_digests, dict) else {}
    digests = {key: value for key, value in digests.items()
               if isinstance(key, str) and isinstance(value, str) and SHA256.fullmatch(value)}
    payload = assemble(contract_data | {"spec": spec}, data, units,
        [pick(event, EVENT_FIELDS, root) for event in events if isinstance(event, dict)],
        digests, improvement_candidates(run.get("improvement_candidates"), root),
        scope_audit(scope_audit_data, root))
    return clean(payload, root)
