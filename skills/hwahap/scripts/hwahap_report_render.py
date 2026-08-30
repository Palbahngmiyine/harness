"""Compose the deterministic offline HTML report."""

from hwahap_report_assets import META_STATIC, STYLE_BLOCK
from hwahap_report_canonical import validate_payload
from hwahap_report_changes import deferred_html, deviation_html, failure_html, proposal_html
from hwahap_report_core_sections import core_sections
from hwahap_report_evidence import FOOTER, app_header, evidence_sections
from hwahap_report_human import human_sections
from hwahap_report_metrics import metric_sections
from hwahap_report_provenance import provenance_html, status_data
from hwahap_report_review_sections import review_sections
from hwahap_report_view import View


def render_report(payload: dict, source_digest: str) -> bytes:
    validate_payload(payload, source_digest)
    view = View(payload)
    contract, agents, units, timeline = core_sections(view)
    review_rows, final_html, scope_html = review_sections(view)
    metrics, metrics_html, token_html, commands, receipts = metric_sections(view)
    provenance, goal_history = provenance_html(view)
    summary, css, label, counts = status_data(view, metrics)
    human = human_sections(view, summary, css, label, counts, metrics,
        metrics_html, token_html, commands, receipts, final_html,
        deviation_html(view), deferred_html(view), proposal_html(view))
    evidence = evidence_sections(view, contract, agents, units, timeline,
        review_rows, final_html, scope_html, failure_html(view), provenance,
        goal_history)
    main = f'<main id="report">{human}{evidence}{FOOTER}</main>'
    head = ('<!doctype html><html lang="ko"><head>' + "".join(META_STATIC[:5])
            + '<meta name="hwahap-source-sha256" content="' + view.esc(source_digest)
            + '">' + META_STATIC[5]
            + '<title>Hwahap 실행 결과 · 문제, 개선, 근거</title>'
            + STYLE_BLOCK + '</head><body>')
    return (head + app_header(view, css, label) + main + '</body></html>').encode("utf-8")
