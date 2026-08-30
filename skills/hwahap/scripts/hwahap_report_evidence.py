"""Technical evidence sections and document chrome."""

from hwahap_report_ledger import payload_ledger_block


def evidence_sections(view, contract, agents, units, timeline, review_rows,
                      final_html, scope_html, failures, provenance, goal_history):
    return (
        '<details id="evidence-vault" class="evidence-vault"><summary>원본 증거 전체 보기 · '
        'snapshot, 상태 이력, JSON ledger</summary><div class="evidence-content">'
        '<p class="section-intro">아래 내용은 감사와 재검증을 위한 전체 자료입니다. '
        '앞의 결론·문제·개선 설명과 같은 정본 데이터를 사용합니다.</p>'
        f'<section id="contract"><h2>잠긴 계약</h2><div class="cards">{contract}</div></section>'
        f'<section id="agents"><h2>에이전트·역할 파이프라인</h2><div class="cards">{agents}</div></section>'
        f'<section id="units"><h2>작업 단위</h2><div class="cards">{units}</div></section>'
        f'<section id="timeline"><h2>전체 타임라인</h2><ol class="timeline">{timeline}</ol></section>'
        '<section id="reviews"><h2>단위별 검토</h2><div class="table-wrap"><table>'
        '<caption>Luna 검증과 Terra 범위 검토</caption><thead><tr><th scope="col">단위</th>'
        '<th scope="col">회차</th><th scope="col">결과</th><th scope="col">Luna</th>'
        '<th scope="col">Terra</th><th scope="col">변경 경로</th><th scope="col">Luna 증거</th>'
        '<th scope="col">Terra 증거</th><th scope="col">Git snapshot</th></tr></thead>'
        f'<tbody>{review_rows}</tbody></table></div><h3>최종 검토</h3>{final_html}</section>'
        f'<section id="scope-audit"><h2>범위 감사</h2>{scope_html}</section>'
        f'<section id="failures-recovery"><h2>실패·복구 전체 기록</h2><div class="cards">{failures}</div></section>'
        f'<section id="provenance"><h2>출처와 digest</h2><dl>{provenance}</dl>'
        f'<h3>Goal history</h3>{goal_history}</section>{payload_ledger_block(view.payload)}</div></details>')


def app_header(view, css, label):
    return (
        '<a class="skip-link" href="#summary">결론으로 건너뛰기</a><header class="top-app-bar">'
        '<div><span class="app-kicker">Local evidence report</span><div class="app-title">Hwahap</div></div>'
        f'<span class="status-chip {css}">{view.esc(label)}</span></header>'
        '<nav class="section-nav" aria-label="보고서 주요 항목"><a class="nav-chip" href="#summary">결론</a>'
        '<a class="nav-chip" href="#deviations">문제와 개선</a>'
        '<a class="nav-chip" href="#improvement-candidates">다음 개선</a>'
        '<a class="nav-chip" href="#tests-metrics">검증 근거</a>'
        '<a class="nav-chip" href="#evidence-vault">원본 증거</a></nav>')


FOOTER = ('<footer class="report-footer"><p>Material Design 3의 color roles, type scale, shape, elevation, state, '
          'adaptive layout, standard motion 원칙을 적용한 네트워크 독립형 정적 보고서입니다.</p>'
          '<p><a href="https://m3.material.io/">Material Design 3 공식 문서</a></p></footer>')
