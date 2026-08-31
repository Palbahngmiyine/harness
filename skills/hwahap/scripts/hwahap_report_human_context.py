"""Shared causal and evidence-detail presentation helpers."""


def fivew3h(view, title, claim, rows, evidence, limitation):
    facts = "".join(f'<div><dt>{view.esc(label)}</dt><dd>{view.esc(value)}</dd></div>'
                     for label, value in rows)
    return (f'<details class="evidence-explanation"><summary>{view.esc(title)}</summary>'
            f'<div class="evidence-brief"><p class="evidence-conclusion"><strong>이 근거가 뒷받침하는 판단</strong><br>{view.esc(claim)}</p>'
            f'<dl class="fivew3h-grid">{facts}</dl><div class="evidence-source"><strong>근거 원문</strong>{view.items(evidence)}</div>'
            f'<p class="evidence-limit"><strong>이 근거로는 알 수 없는 것</strong><br>{view.esc(limitation)}</p></div></details>')


def decision_context(view, value, subject):
    context = value if isinstance(value, dict) else {}
    fields = ("scenario", "affected_scope", "impact", "decision_reason",
              "evidence_relation", "success_condition")
    if any(not context.get(field) for field in fields):
        return ('<p class="evidence-limit"><strong>판단 설명 누락</strong><br>'
                f'{view.esc(subject)}의 실제 발생 상황, 영향, 결정 이유, 근거 연결, 해결 기준이 정본 데이터에 모두 기록되지 않았습니다. '
                '이 상태에서는 제목만으로 위험이나 후속 작업의 필요성을 판단할 수 없습니다.</p>')
    labels = ((f"왜 {subject}인가", f"{context['scenario']} {context['impact']}"),
              ("어디에 영향을 주는가", context["affected_scope"]),
              ("왜 사용자가 결정해야 하는가", context["decision_reason"]),
              ("근거가 이 판단을 뒷받침하는 방식", context["evidence_relation"]),
              ("해결됐다고 볼 기준", context["success_condition"]))
    return '<div class="causal-chain">' + "".join(
        f'<div class="causal-step"><span class="field-label">{view.esc(label)}</span><p>{view.esc(value)}</p></div>'
        for label, value in labels) + '</div>'


def _unique(values):
    result = []
    for value in values if isinstance(values, list) else []:
        if value and value not in result:
            result.append(value)
    return result


def contextual_evidence(view, title, claim, why, method, evidence, limitation, context=None):
    context = context if isinstance(context, dict) else {}
    evidence = evidence if isinstance(evidence, list) else []
    scenario, affected = context.get("scenario"), context.get("affected_scope")
    impact, reason = context.get("impact"), context.get("decision_reason")
    relation, success = context.get("evidence_relation"), context.get("success_condition")
    rows = (("누가 (Who)", "항목별 작성자는 미기록. 완료 상태 기록자는 미기록"),
            ("언제 (When)", f"항목별 확인 시각 미기록. 문제가 되는 조건: {scenario or '구체적 시나리오 미기록'}"),
            ("어디서 (Where)", f"{affected or '영향 범위 미기록'}. 항목과 연결된 변경 경로는 정본 payload에서 대조"),
            ("무엇을 (What)", scenario or claim),
            ("왜 (Why)", " ".join(value for value in (why, impact, reason) if value)),
            ("어떻게 (How)", relation or method),
            ("얼마나 (How much)", f"해결 판단 기준: {success or '미기록'}; 근거 문구 {len(evidence)}개; 직접 연결된 구조화 receipt 필드는 없음"),
            ("얼마 동안 (How long)", "항목별 조사·검증 시간 미기록"))
    return fivew3h(view, title, claim, rows, _unique(evidence), limitation)


def evidence_reference(values):
    return " / ".join(_unique(values)) or "근거 원문 없음"
