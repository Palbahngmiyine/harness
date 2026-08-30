"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_report_schema(run: dict, run_dir: Path, contract: dict, units: list[dict], errors: list[str]) -> None:
    report = run.get("report")
    required = {"schema_version", "status", "generator", "source_payload_sha256", "data", "html", "generated_at", "redaction_policy"}
    if not isinstance(report, dict) or not required.issubset(report):
        errors.append("report receipt is incomplete")
        return
    generator = report.get("generator")
    data_meta = report.get("data") if isinstance(report.get("data"), dict) else None
    html_meta = report.get("html") if isinstance(report.get("html"), dict) else None
    if (report.get("schema_version") != REPORT_SCHEMA_VERSION or report.get("redaction_policy") != REPORT_REDACTION_POLICY
            or generator != REPORT_GENERATOR
            or report.get("data") != {"path": "report-data.json", "file_sha256": data_meta.get("file_sha256") if data_meta else None}
            or report.get("html") != {"path": "report.html", "file_sha256": html_meta.get("file_sha256") if html_meta else None}):
        errors.append("report receipt metadata is invalid")
        return
    data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
    if report.get("status") == "pending":
        if (run.get("status") == "completed" or report.get("source_payload_sha256") is not None
                or report.get("generated_at") is not None
                or (data_meta and data_meta.get("file_sha256") is not None)
                or (html_meta and html_meta.get("file_sha256") is not None)):
            errors.append("pending report is invalid for completed run")
        if any(path.exists() or path.is_symlink() for path in (data_path, report_path)):
            errors.append("pending report must not have report artifacts")
        return
    if report.get("status") != "completed":
        errors.append("report status is invalid")
        return
    if run.get("status") not in RUN_TERMINAL_STATES or not required_text(report.get("generated_at")):
        errors.append("completed report requires a terminal run and generated_at")
    if any(not _single_regular_file(path) for path in (data_path, report_path)):
        errors.append("completed report artifacts must be regular files")
        return
    if not isinstance(report.get("source_payload_sha256"), str) or not SHA256.fullmatch(report["source_payload_sha256"]):
        errors.append("report source digest is invalid")
    for artifact in (report.get("data"), report.get("html")):
        if not isinstance(artifact, dict) or not isinstance(artifact.get("file_sha256"), str) or not SHA256.fullmatch(artifact["file_sha256"]):
            errors.append("report artifact digest is invalid")
    try:
        events = parse_events(run_dir / "events.jsonl")
        digests = report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
        artifacts = prepare_report_artifacts(run_dir.parents[2], contract, run, units, events, digests)
        current_goal = run.get("goal_link", {}).get("current", {}) if isinstance(run.get("goal_link"), dict) else {}
        if isinstance(current_goal, dict) and current_goal.get("source") == "codex.update_goal":
            expected_generated_at = current_goal.get("observed_at")
        else:
            terminal = [event.get("timestamp") for event in events
                        if event.get("entity") == "run" and event.get("to") in RUN_TERMINAL_STATES]
            expected_generated_at = terminal[-1] if terminal else None
        if report.get("generated_at") != expected_generated_at:
            errors.append("report generated_at does not match authoritative state event")
        if artifacts["source_payload_sha256"] != report.get("source_payload_sha256"):
            errors.append("report source digest does not match state")
        data = data_path.read_bytes()
        report_bytes = report_path.read_bytes()
        data_digest = "sha256:" + hashlib.sha256(data).hexdigest()
        if data_digest != report.get("source_payload_sha256") or data_digest != report.get("data", {}).get("file_sha256"):
            errors.append("report data digest does not match contents")
        html_digest = "sha256:" + hashlib.sha256(report_bytes).hexdigest()
        if html_digest != report.get("html", {}).get("file_sha256"):
            errors.append("report file digest does not match contents")
        if report.get("html", {}).get("file_sha256") != artifacts["html_file_sha256"]:
            errors.append("report file digest does not match regenerated artifact")
        if report_bytes != artifacts["html_bytes"]:
            errors.append("report HTML does not match canonical renderer")
        module = report_module()
        if json.loads(data.decode("utf-8")) != artifacts["payload"]:
            errors.append("report data does not match state")
        module.validate_report_data_bytes(data, artifacts["payload"], artifacts["source_payload_sha256"])
        module.validate_report_bytes(report_bytes, artifacts["source_payload_sha256"], artifacts["payload"])
    except (OSError, UnicodeError, ValueError, json.JSONDecodeError, HwahapError):
        errors.append("report validation failed")
