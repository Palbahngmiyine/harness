"""Normalize, validate, and render align-goal source traceability."""
from hwahap_report_clean import clean, pick
from hwahap_report_types import HwahapReportError, SHA256

HANDOFF_KEYS = {"schema", "revision", "spec_digest", "specifications",
                "acceptance_checks", "implementation_units", "confirmation"}
TRACE_KEYS = {"unit_id", "spec_ids", "acceptance_ids"}


def report_spec(value: object, workspace: str) -> dict:
    result = pick(value, ("source", "sha256", "confirmed_at", "status"), workspace)
    if isinstance(value, dict) and value.get("status") == "align-goal":
        result["handoff"] = clean(value.get("handoff"), workspace)
    return result


def report_source_trace(value: object, workspace: str) -> dict:
    return pick(value, ("unit_id", "spec_ids", "acceptance_ids"), workspace)


def _source_units(handoff: dict) -> dict:
    values = handoff.get("implementation_units")
    if not isinstance(values, list) or not values:
        raise HwahapReportError("align-goal source units are missing")
    result = {item.get("id"): item for item in values if isinstance(item, dict)}
    if len(result) != len(values) or any(not isinstance(key, str) or not key for key in result):
        raise HwahapReportError("align-goal source unit IDs are invalid")
    return result


def validate_report_handoff(payload: dict) -> None:
    contract = payload.get("contract") if isinstance(payload, dict) else None
    spec = contract.get("spec") if isinstance(contract, dict) else None
    units = payload.get("units", []) if isinstance(payload, dict) else []
    traces = [unit.get("source_trace") for unit in units if isinstance(unit, dict)
              and unit.get("source_trace")]
    if not isinstance(spec, dict) or spec.get("status") != "align-goal":
        if isinstance(spec, dict) and "handoff" in spec or traces:
            raise HwahapReportError("source traces require an align-goal handoff")
        return
    handoff = spec.get("handoff")
    if not isinstance(handoff, dict) or set(handoff) != HANDOFF_KEYS \
            or handoff.get("schema") != "align-goal/v1" \
            or not SHA256.fullmatch(str(handoff.get("spec_digest", ""))) \
            or not all(isinstance(handoff.get(key), list) and handoff[key]
                       for key in ("specifications", "acceptance_checks")) \
            or not isinstance(handoff.get("confirmation"), dict):
        raise HwahapReportError("align-goal report handoff is incomplete")
    sources = _source_units(handoff); mapped = []
    for trace in traces:
        source = sources.get(trace.get("unit_id")) if isinstance(trace, dict) else None
        if not isinstance(trace, dict) or set(trace) != TRACE_KEYS or source is None \
                or trace.get("spec_ids") != source.get("spec_ids") \
                or trace.get("acceptance_ids") != source.get("acceptance_ids"):
            raise HwahapReportError("align-goal report unit trace is invalid")
        mapped.append(trace["unit_id"])
    if len(mapped) != len(set(mapped)):
        raise HwahapReportError("align-goal report unit trace is duplicated")
    status = payload.get("summary", {}).get("status")
    if status == "completed" and set(mapped) != set(sources):
        raise HwahapReportError("completed report lacks align-goal unit coverage")


def handoff_html(view, spec: dict) -> str:
    handoff = spec.get("handoff") if isinstance(spec, dict) else None
    if not isinstance(handoff, dict):
        return ""
    groups = (("Specifications", handoff.get("specifications", [])),
              ("Acceptance", handoff.get("acceptance_checks", [])),
              ("Implementation units", handoff.get("implementation_units", [])))
    cards = "".join('<article class="card md-card md-card-filled"><h3>'
        f'{view.esc(label)}</h3>{view.items([view.shown(item) for item in items])}</article>'
        for label, items in groups)
    return ('<article class="card md-card md-card-filled"><h3>align-goal source</h3><dl>'
        f'<dt>schema</dt><dd>{view.esc(handoff.get("schema"))}</dd>'
        f'<dt>spec digest</dt><dd>{view.esc(handoff.get("spec_digest"))}</dd></dl></article>'
        + cards)
