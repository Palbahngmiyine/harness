"""Provenance and status presentation helpers."""

import json


def provenance_html(view):
    provenance = view.payload.get("provenance", {})
    goal = provenance.get("goal_link", {}).get("current", {})
    spec = provenance.get("spec", {})
    fields = [
        ("fast_status", provenance.get("fast_status")),
        ("spec source", spec.get("source")), ("spec sha256", spec.get("sha256")),
        ("spec confirmed_at", spec.get("confirmed_at")),
        ("spec status", spec.get("status", "prfaq")),
    ]
    fields.extend((f"Goal current {key}", goal.get(key)) for key in (
        "thread_id", "receipt_sha256", "objective_sha256", "observed_at",
        "token_total", "source", "reason"))
    fields.append(("Goal current evidence", goal.get("evidence", [])))
    fields.extend((("Goal mode", goal.get("mode")),
                   ("Goal sync", goal.get("completion_sync")),
                   ("Goal sync result", goal.get("sync_result"))))
    fields.extend((f"state digest {key}", value)
                  for key, value in provenance.get("state_digests", {}).items())
    fields.extend((f"agent profile {key}", value)
                  for key, value in provenance.get("agent_profiles", {}).items())
    html = "".join(f"<dt>{view.esc(key)}</dt><dd>{view.display(value)}</dd>"
                   for key, value in fields)
    history = [json.dumps(item, ensure_ascii=False, sort_keys=True)
               for item in provenance.get("goal_link", {}).get("history", [])
               if isinstance(item, dict)]
    return html, view.items(history)


def status_data(view, metrics):
    summary = view.payload.get("summary", {})
    status = str(summary.get("status", "unknown"))
    stopped = {"failed", "blocked", "cancelled"}
    css = "status-success" if status == "completed" else \
        "status-error" if status in stopped else "status-warning"
    label = "완료" if status == "completed" else \
        "실패 또는 중단" if status in stopped else "진행 상태 확인 필요"
    units = view.payload.get("units", [])
    passed = sum(isinstance(unit, dict) and unit.get("status") == "passed"
                 for unit in units)
    counts = {
        "passed": passed, "total": len(units) if isinstance(units, list) else 0,
        "deviations": len(view.payload.get("deviations", {}).get("items", [])),
        "risks": len(view.payload.get("deviations", {}).get("deferred_security", [])),
        "candidates": len(view.payload.get("improvement-candidates", [])),
        "tests": view.display(metrics.get("test_runs")),
    }
    return summary, css, label, counts
