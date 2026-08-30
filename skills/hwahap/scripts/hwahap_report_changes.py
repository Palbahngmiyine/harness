"""Failure, recovery, deviation, and proposal report sections."""

from hwahap_report_security import text


def _improvement(record):
    def shown(value):
        if value is None or value == "":
            return "기록 없음"
        if isinstance(value, list):
            return ", ".join(shown(item) for item in value)
        return text(value)
    keys = ("after_round", "kind", "failure_signature", "root_cause", "hypothesis",
            "action", "strategy_digest", "scope_status", "evidence")
    return "; ".join(f"{key}={shown(record.get(key))}" for key in keys)


def proposal_html(view):
    html = "".join(
        '<article class="proposal-card"><span class="label-chip status-warning">사용자 결정 필요</span>'
        f'<h3>{view.esc(item.get("summary"))}</h3><span class="field-label">기대 효과</span>'
        f'<p>{view.esc(item.get("expected_effect"))}</p><span class="field-label">다음 결정</span>'
        f'<p>{view.esc(item.get("next_action"))}</p><details><summary>제안 근거 보기</summary>'
        f'{view.items(item.get("evidence"))}</details>'
        '<p class="notice">보고 전용 · 사용자 승인 전에는 실행하지 않음</p></article>'
        for item in view.payload.get("improvement-candidates", []) if isinstance(item, dict))
    return html or '<p class="empty">추가 개선 제안 없음</p>'


def failure_html(view):
    values = [item for item in view.payload.get("failures-recovery", [])
              if item.get("failure") or item.get("recovery")
              or item.get("improvement_history")]
    html = "".join(
        f'<article class="card"><h3>{view.esc(item.get("unit_id"))}</h3>'
        f'<p>{view.esc(item.get("failure", {}).get("code", "실패 없음"))}: '
        f'{view.esc(item.get("failure", {}).get("reason", ""))}</p><p>실패 증거</p>'
        f'{view.items(item.get("failure", {}).get("evidence"))}'
        f'<p>failure.recovery: {view.shown(item.get("failure", {}).get("recovery"))}</p>'
        f'<p>recovery.reason: {view.shown(item.get("recovery", {}).get("reason"))}</p>'
        f'<p>recovery.action: {view.shown(item.get("recovery", {}).get("action"))}</p>'
        f'<p>복구 증거</p>{view.items(item.get("recovery", {}).get("evidence"))}'
        f'{view.items([_improvement(record) for record in item.get("improvement_history", [])])}'
        '</article>' for item in values)
    return html or '<p class="empty">기록 없음</p>'


def deviation_html(view):
    html = "".join(
        '<article class="change-card"><header class="change-card-header">'
        '<span class="status-chip status-success">개선 적용·검증됨</span>'
        f'<h3>{view.esc(item.get("summary"))}</h3></header><div class="change-card-body">'
        f'<div class="change-field"><span class="field-label">이전 문제</span><p>{view.esc(item.get("impact"))}</p></div>'
        f'<div class="change-field"><span class="field-label">발생 원인</span><p>{view.esc(item.get("root_cause"))}</p></div>'
        f'<div class="change-field"><span class="field-label">적용한 개선</span><p>{view.esc(item.get("prevention"))}</p></div></div>'
        '<p class="expected-change"><strong>이전 대비 기대 변화</strong><br>'
        '위의 “이전 문제”가 다시 발생하기 전에 “적용한 개선”에 적힌 검사로 '
        '같은 유형의 누락이나 오판을 발견하거나 차단할 것으로 기대합니다. '
        '표시된 검증 근거 범위의 기대이며 실제 운영 효과를 보장한다는 뜻은 아닙니다.</p>'
        f'<details><summary>검증 근거 보기</summary>{view.items(item.get("evidence"))}</details></article>'
        for item in view.payload.get("deviations", {}).get("items", []))
    return html or '<p class="empty">기록된 문제와 개선 없음</p>'


def deferred_html(view):
    html = "".join(
        '<article class="risk-card"><span class="status-chip status-error">아직 확인되지 않음</span>'
        f'<h3>{view.esc(item.get("summary"))}</h3><span class="field-label">남은 이유</span>'
        f'<p>{view.esc(item.get("reason"))}</p><span class="field-label">다음 결정</span>'
        f'<p>{view.esc(item.get("next_action"))}</p><details><summary>현재 근거 보기</summary>'
        f'{view.items(item.get("evidence"))}</details></article>'
        for item in view.payload.get("deviations", {}).get("deferred_security", []))
    return html or '<p class="empty">별도로 보류된 위험 없음</p>'
