"""Metrics and test receipt report sections."""

LABELS = {
    "unit_count": "작업 단위", "agent_runs": "에이전트 실행",
    "review_rounds": "검수 회차", "recoveries": "복구", "replans": "재계획",
    "scope_deviations": "범위 편차", "test_runs": "검증된 테스트 영수증 수",
    "elapsed_seconds": "완료 시간(초)", "availability": "확인 가능 여부",
    "reason": "사유", "source": "출처", "total": "총 토큰",
}
RECEIPT_LABELS = (
    ("status", "결과"), ("source", "출처"), ("observer_role", "관찰 역할"),
    ("observer_thread_id", "Luna verifier thread"),
    ("diff_digest", "검토 diff digest"),
    ("execution_receipt_sha256", "실행 receipt digest"),
    ("command_sha256", "명령 digest"), ("output_sha256", "출력 digest"),
    ("started_at", "시작"), ("ended_at", "종료"), ("exit_code", "exit code"),
    ("command_index", "명령 번호"),
)


def _metric_value(view, key, value):
    if key == "agent_runs" and isinstance(value, dict):
        return (f'{view.esc(LABELS["availability"])}: '
                f'{view.display(value.get("availability"))}; '
                f'{view.esc(LABELS["reason"])}: {view.display(value.get("reason"))}')
    return view.esc(value)


def _receipt_items(view, values):
    cards = []
    if not isinstance(values, list):
        values = []
    for item in values:
        if not isinstance(item, dict) or not isinstance(item.get("receipts"), list):
            continue
        for receipt in item["receipts"]:
            if not isinstance(receipt, dict):
                continue
            fields = "".join(
                f"<dt>{view.esc(label)}</dt><dd>{view.esc(receipt.get(key))}</dd>"
                for key, label in RECEIPT_LABELS)
            fields += f'<dt>diff snapshot</dt><dd>{view.snapshot(receipt.get("diff_snapshot"))}</dd>'
            cards.append(f'<article class="receipt"><h3>{view.esc(item.get("unit_id"))}/'
                         f'{view.esc(receipt.get("test_id"))}</h3><dl>{fields}</dl></article>')
    if not cards:
        return '<p class="empty">기록 없음</p>'
    return '<div class="receipt-list">' + "".join(cards) + "</div>"


def metric_sections(view):
    section = view.payload.get("tests-metrics", {})
    metrics = section.get("metrics", {})
    metrics_html = "".join(
        f'<dt>{view.esc(LABELS.get(key, "기타 정보"))}</dt>'
        f'<dd>{_metric_value(view, key, value)}</dd>'
        for key, value in metrics.items() if key != "token_usage")
    token = metrics.get("token_usage", {})
    token_html = (f'{view.esc(LABELS["availability"])}: '
        f'{view.display(token.get("availability"))}; {view.esc(LABELS["source"])}: '
        f'{view.display(token.get("source"))}; {view.esc(LABELS["total"])}: '
        f'{view.display(token.get("total"))}; {view.esc(LABELS["reason"])}: '
        f'{view.display(token.get("reason"))}')
    return metrics, metrics_html, token_html, view.commands(
        section.get("acceptance_commands", [])), _receipt_items(
            view, section.get("test_receipts", []))
