"""Decision cards with explicit evidence and user authority boundaries."""

from hwahap_report_human_context import fivew3h


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


def decision_html(view):
    payload = view.payload
    units = payload.get("units", [])
    provenance = payload.get("provenance", {})
    metrics = payload.get("tests-metrics", {}).get("metrics", {})
    for item in units:
        if not isinstance(item, dict):
            continue
    def record(action):
        text = str(action)
        section, count, why, evidence = "이 보고서", "관련 항목 수를 자동으로 연결할 수 없음", "정본 payload가 후속 조치로 기록했기 때문", []
        if text.startswith("범위 편차"):
            values = payload.get("deviations", {}).get("items", [])
            section, count = "문제와 개선 섹션", f"개선 기록 {len(values)}건"
            why = "이미 적용한 prevention이 같은 유형의 문제를 막는지 사용자가 수용해야 하기 때문"
            evidence = [v for item in values if isinstance(item, dict) for v in [item.get("summary"), *item.get("evidence", [])]]
        elif text.startswith("보류된 보안"):
            values = payload.get("deviations", {}).get("deferred_security", [])
            section, count = "아직 남은 위험 섹션", f"보류된 위험 {len(values)}건"
            reasons = [item.get("decision_context", {}).get("decision_reason") for item in values if isinstance(item, dict) and isinstance(item.get("decision_context"), dict)]
            why = " ".join(reason for reason in reasons if reason) or "위험별 사용자 결정 이유가 기록되지 않아 판단 근거가 불충분함"
            evidence = [v for item in values if isinstance(item, dict) for v in [item.get("summary"), item.get("reason"), *item.get("evidence", [])]]
        elif "반복 실패" in text:
            histories = [record for unit in units if isinstance(unit, dict) for record in unit.get("improvement_history", []) if isinstance(record, dict)]
            section, count, why = "실패·복구 원본 기록", f"개선 이력 {len(histories)}건", "두 번 실패한 작업은 같은 전략을 반복하지 않고 Sol 재계획 여부를 결정해야 하기 때문"
            evidence = [v for item in histories for v in item.get("evidence", [])]
        elif "token" in text:
            token = metrics.get("token_usage", {})
            section, count, why = "원본 수치의 token 사용량", "token aggregate 1항목", "플랫폼이 정확한 합계를 제공하지 않은 상태에서 추정치를 사실처럼 쓰지 않기 위함"
            evidence = [token.get(key) for key in ("availability", "reason", "source")]
        elif "Fast 상태" in text:
            section, count, why = "출처와 digest의 fast_status", "Fast 상태 1항목", "실제 Fast 활성 여부를 관찰한 receipt가 없어 모델 실행 조건을 확정할 수 없기 때문"
            evidence = [f"fast_status={provenance.get('fast_status') or '기록 없음'}"]
        rows = (("누가 (Who)", "사용자가 최종 결정. Hwahap는 정본 payload 조건을 근거로 이 조치만 제시"),
                ("언제 (When)", "이 보고서를 검토한 뒤; 결정 기한은 미기록"), ("어디서 (Where)", section),
                ("무엇을 (What)", text), ("왜 (Why)", why),
                ("어떻게 (How)", "관련 기록과 원문 근거를 확인한 뒤 승인·보류·추가 검증 중 하나를 사용자가 선택"),
                ("얼마나 (How much)", count), ("얼마 동안 (How long)", "결정·후속 작업 소요 시간 미기록"))
        details = fivew3h(view, "이 결정이 필요한 근거와 한계 보기", text, rows, _unique(evidence),
                          "이 보고서는 결정을 제안할 뿐 승인으로 간주하거나 후속 작업을 자동 실행하지 않음")
        return f'<article class="decision-item"><h3>{view.esc(text)}</h3><p><strong>판단 이유</strong><br>{view.esc(why)}</p>{details}</article>'
    return '<div class="decision-list">' + "".join(record(action) for action in payload.get("next-actions", [])) + '</div>'
