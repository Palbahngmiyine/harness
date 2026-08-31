"""Human-first report sections."""

from hwahap_report_human_detail import completion
from hwahap_report_human_decisions import decision_html


def human_sections(view, summary, css, label, counts, metrics, metrics_html,
                   token_html, command_html, receipt_html, final_html,
                   deviations, deferred, candidates):
    reviews = view.payload.get("reviews", {})
    conclusion, receipt_explanation, completion_detail = completion(view, metrics, counts)
    summary_metrics = (
        '<div class="summary-grid"><div class="metric"><span class="metric-label">최종 판정</span>'
        f'<span class="metric-value">{view.esc(label)} · Sol '
        f'{view.esc(reviews.get("final_review", {}).get("status"))}</span></div>'
        '<div class="metric"><span class="metric-label">통과한 작업 단위</span>'
        f'<span class="metric-value">{counts["passed"]} / {counts["total"]}</span></div>'
        '<div class="metric"><span class="metric-label">검증 기록</span>'
        f'<span class="metric-value">{counts["tests"]}개 receipt</span></div>'
        '<div class="metric"><span class="metric-label">발견·개선한 문제</span>'
        f'<span class="metric-value">{counts["deviations"]}건</span></div></div>')
    return (
        f'<section id="summary" class="outcome-panel panel md-card md-card-elevated"><span class="eyebrow">Hwahap orchestration · '
        f'{view.esc(summary.get("run_id"))}</span><p><span class="status-chip {css}">'
        f'{view.esc(label)}</span></p><h1>Hwahap 실행 결과</h1><p class="hero-copy">'
        f'{view.esc(summary.get("goal"))}</p><p class="section-intro">결론과 변화부터 읽고, '
        f'전체 snapshot·receipt·JSON 값은 맨 아래 원본 증거에서 확인할 수 있습니다.</p>{summary_metrics}</section>'
        '<div class="decision-layout"><div><section id="deviations"><span class="eyebrow">Before → after</span>'
        '<h2>무엇이 문제였고 어떻게 개선했나</h2><p class="section-intro">각 항목은 이전 문제, 발생 원인, '
        f'적용한 개선, 이전 대비 기대 변화를 같은 순서로 보여줍니다.</p><div class="change-grid">{deviations}</div>'
        '</section></div><aside class="supporting-pane" aria-label="남은 위험"><section><span class="eyebrow">Remaining risk</span>'
        f'<h2>아직 남은 위험</h2><p class="section-intro">완료 판정과 별개로 아직 직접 검증하지 못했거나 새 승인이 '
        f'필요한 항목 {counts["risks"]}건입니다.</p><div class="cards">{deferred}</div></section></aside></div>'
        '<section id="improvement-candidates"><span class="eyebrow">Report only</span>'
        f'<h2>다음에 개선할 수 있는 것</h2><p class="section-intro">현재 기능을 실패로 바꾸지 않는 후속 후보 '
        f'{counts["candidates"]}건입니다. 기대 효과와 다음 결정을 확인한 뒤 사용자가 승인해야 실행합니다.</p>'
        f'<div class="proposal-grid">{candidates}</div></section><section id="next-actions">'
        '<span class="eyebrow">Decision</span><h2>지금 사용자가 판단할 것</h2>'
        f'{decision_html(view)}</section><section id="tests-metrics">'
        '<span class="eyebrow">Verification</span><h2>어떤 근거로 완료라고 판단했나</h2>'
        f'<p class="completion-judgment">{view.esc(conclusion)}</p><p class="section-intro">{view.esc(receipt_explanation)}</p>'
        f'{completion_detail}'
        f'<div class="metrics-grid"><article class="card tile md-card md-card-filled"><h3>원본 수치</h3>'
        f'<p class="notice">수치는 판정 문장을 뒷받침하는 기록이며, 수치만으로 완료를 뜻하지 않습니다.</p><dl>{metrics_html}</dl>'
        f'<p>{token_html}</p></article><article class="card tile md-card md-card-filled"><h3>Sol 최종 리뷰 원문</h3>{final_html}</article></div>'
        f'<details><summary>테스트 명령과 receipt 전체 보기</summary><h3>Acceptance commands</h3>{command_html}'
        f'<h3>Test receipts</h3>{receipt_html}</details></section>')
