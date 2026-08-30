"""Review and scope-audit report sections."""


def _reviewer(view, value):
    if not isinstance(value, dict):
        return '<span class="empty">기록 없음</span>'
    fields = "".join(f"<dt>{view.esc(key)}</dt><dd>{view.esc(value.get(key))}</dd>"
                     for key in ("status", "model", "effort", "thread_id", "diff_digest"))
    return "<dl>" + fields + "</dl>"


def _audit_units(view, value):
    if not isinstance(value, list):
        return ""
    return "; ".join(f'{view.esc(item.get("unit_id"))}: '
                    f'{view.comma(item.get("matched_rules", []))}'
                    for item in value if isinstance(item, dict))


def review_sections(view):
    reviews = view.payload.get("reviews", {})
    rows = "".join(
        f'<tr><td>{view.esc(unit.get("unit_id"))}</td><td>{view.esc(review.get("round"))}</td>'
        f'<td>{view.esc(review.get("outcome"))}</td><td>{_reviewer(view, review.get("verifier"))}</td>'
        f'<td>{_reviewer(view, review.get("scope_reviewer"))}</td>'
        f'<td>{view.comma(review.get("changed_paths", []))}</td>'
        f'<td>{view.comma(review.get("verifier", {}).get("evidence", []))}</td>'
        f'<td>{view.comma(review.get("scope_reviewer", {}).get("evidence", []))}</td>'
        f'<td>{view.snapshot(review.get("diff_snapshot"))}</td></tr>'
        for unit in reviews.get("units", []) for review in unit.get("history", []))
    rows = rows or '<tr><td colspan="9" class="empty">기록 없음</td></tr>'
    final = reviews.get("final_review", {})
    attempts = final.get("attempts", [])
    cards = "".join(
        f'<article class="receipt"><p>{view.esc(item.get("model"))} / '
        f'{view.esc(item.get("effort"))} / {view.esc(item.get("status"))} / '
        f'{view.esc(item.get("thread_id"))}</p><p>diff_digest: '
        f'{view.esc(item.get("diff_digest"))}</p><p>evidence: '
        f'{view.comma(item.get("evidence", []))}</p>'
        f'{view.snapshot(item.get("diff_snapshot"))}</article>'
        for item in attempts if isinstance(item, dict))
    final_html = f'<p>aggregate status: {view.esc(final.get("status"))}</p>'
    final_html += '<div class="receipt-list">' + cards + '</div>' \
        if attempts else '<p class="empty">기록 없음</p>'
    scope = view.payload.get("scope_audit", {})
    scope_rows = "".join(
        f'<article class="card"><h3>{view.esc(item.get("path"))}: {view.esc(item.get("verdict"))}</h3>'
        f'<p>contract_allowed: {view.esc(item.get("contract_allowed"))}; '
        f'passed_unit_covered: {view.esc(item.get("passed_unit_covered"))}; '
        f'forbidden_overlap: {view.esc(item.get("forbidden_overlap"))}</p>'
        f'<p>계약 규칙: {view.comma(item.get("matched_contract_rules", []))}</p>'
        f'<p>통과 단위·규칙: {_audit_units(view, item.get("covering_passed_units"))}</p>'
        f'<p>금지 규칙: {view.comma(item.get("matched_forbidden_rules", []))}</p>'
        f'<p>증거 diff digest: {view.esc(item.get("evidence", {}).get("diff_digest"))}; '
        f'contract lock: {view.esc(item.get("evidence", {}).get("contract_lock_sha256"))}; '
        f'passed unit IDs: {view.comma(item.get("evidence", {}).get("passed_unit_ids", []))}</p></article>'
        for item in (scope.get("paths", []) if isinstance(scope, dict) else [])
        if isinstance(item, dict)) or '<p class="empty">기록 없음</p>'
    scope_html = (f'<dl><dt>authority</dt><dd>{view.esc(scope.get("authority"))}</dd>'
        f'<dt>affects_gate</dt><dd>{view.esc(scope.get("affects_gate"))}</dd>'
        f'<dt>source_diff_digest</dt><dd>{view.esc(scope.get("source_diff_digest"))}</dd>'
        f'<dt>contract_lock_sha256</dt><dd>{view.esc(scope.get("contract_lock_sha256"))}</dd>'
        f'</dl><div class="cards">{scope_rows}</div>')
    return rows, final_html, scope_html
