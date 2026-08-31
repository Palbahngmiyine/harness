"""Contract, agent, unit, and timeline report sections."""

from hwahap_report_types import CONTRACT_LISTS, EVENT_FIELDS

LABELS = {
    "goals": "목표", "non_goals": "제외 범위", "allowed_paths": "허용 경로",
    "forbidden_changes": "금지 변경", "acceptance_criteria": "완료 기준",
    "test_commands": "테스트 명령",
}


def core_sections(view):
    payload = view.payload
    contract = payload.get("contract", {})
    spec = contract.get("spec", {}) if isinstance(contract.get("spec"), dict) else {}
    metadata = (
        ("schema_version", contract.get("schema_version")),
        ("goal_id", contract.get("goal_id")), ("goal", contract.get("goal")),
        ("locked", contract.get("locked")), ("lock_sha256", contract.get("lock_sha256")),
        ("spec source", spec.get("source")), ("spec sha256", spec.get("sha256")),
        ("spec confirmed_at", spec.get("confirmed_at")),
        ("spec status", spec.get("status", "prfaq")),
    )
    metadata_html = "".join(
        f"<dt>{view.esc(key)}</dt><dd>{view.esc(value)}</dd>" for key, value in metadata)
    contract_html = f'<article class="card md-card md-card-filled"><h3>계약 메타데이터</h3><dl>{metadata_html}</dl></article>'
    contract_html += "".join(
        f'<article class="card md-card md-card-filled"><h3>{view.esc(LABELS[key])}</h3>'
        f'{view.commands(contract.get(key)) if key == "test_commands" else view.items(contract.get(key))}</article>'
        for key in CONTRACT_LISTS)
    agents = payload.get("agents", {})
    role_html = "".join(
        f'<article class="card md-card md-card-filled"><h3>{view.esc(role)}</h3>'
        f'<p>agent: {view.esc(info.get("agent"))}</p>'
        f'<p>model: {view.esc(info.get("model"))}</p>'
        f'<p>effort: {view.esc(info.get("effort"))}</p>'
        f'<p>Fast: {view.esc(info.get("fast", info.get("fallback_effort", "unknown")))}</p></article>'
        for role, info in agents.get("roles", {}).items() if isinstance(info, dict))
    profile_html = "".join(
        f'<article class="card md-card md-card-filled"><h3>agent profile</h3><p>filename: {view.esc(name)}</p>'
        f'<p>digest: {view.esc(digest)}</p></article>'
        for name, digest in agents.get("profiles", {}).items())
    agents_html = role_html + profile_html or view.card("상태", "역할 정보 없음")
    units = payload.get("units", [])
    unit_html = "".join(
        f'<article class="card md-card md-card-filled"><h3>{view.esc(unit.get("unit_id"))}: {view.esc(unit.get("title"))}</h3>'
        f'<p>상태: {view.esc(unit.get("status"))}</p><p>writer: {view.shown(unit.get("writer"))}</p>'
        f'<p>replan_count: {view.shown(unit.get("replan_count"))}</p><p>허용 경로</p>'
        f'{view.items(unit.get("allowed_paths"))}<p>Acceptance receipts</p>'
        f'{view.commands(unit.get("acceptance_commands"))}<p>검토 {len(unit.get("review_history", []))}회 · '
        f'개선 {len(unit.get("improvement_history", []))}건</p></article>' for unit in units)
    unit_html = unit_html or '<p class="empty">기록 없음</p>'
    timeline_html = "".join(
        f'<li><dl>{"".join(f"<dt>{view.esc(field)}</dt><dd>{view.comma(event.get(field)) if isinstance(event.get(field), list) else view.esc(event.get(field))}</dd>" for field in EVENT_FIELDS)}</dl></li>'
        for event in payload.get("timeline", []))
    return contract_html, agents_html, unit_html, timeline_html
