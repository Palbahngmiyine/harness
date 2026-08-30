"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _terminal_metrics(run: dict, units: list[dict], timestamp: str) -> dict:
    started = datetime.fromisoformat(str(run.get("started_at")).replace("Z", "+00:00"))
    elapsed = max(0, int((datetime.fromisoformat(timestamp) - started).total_seconds()))
    histories = [unit.get("review_history", []) for unit in units]
    metrics = json.loads(json.dumps(run.get("metrics", {})))
    metrics.update({
        "unit_count": len(units),
        "review_rounds": sum(len(history) for history in histories if isinstance(history, list)),
        "recoveries": sum(bool(history and history[0].get("outcome") == "fail")
                          for history in histories if isinstance(history, list)),
        "replans": sum(sum(record.get("kind") in {"sol_replan", "recursive_improvement"}
                             for record in unit.get("improvement_history", [])
                             if isinstance(record, dict)) for unit in units),
        "scope_deviations": len(run.get("deviations", []))
                            if isinstance(run.get("deviations"), list) else 0,
        "test_runs": sum(len(unit.get("test_receipts", [])) for unit in units
                         if isinstance(unit.get("test_receipts"), list)),
        "elapsed_seconds": elapsed,
    })
    return metrics


def publish_terminal_report(workspace: Path, run_dir: Path, contract_path: Path,
                            run_path: Path, run: dict, event: dict,
                            operation: str = "terminal") -> None:
    events_path = run_dir / "events.jsonl"
    data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
    if run.get("status") not in RUN_TERMINAL_STATES:
        raise HwahapError("HW_STATE_INVALID", "terminal report requires a terminal run")
    if any(path.exists() or path.is_symlink() for path in (data_path, report_path)):
        raise HwahapError("HW_STATE_INVALID", "terminal report artifacts already exist")
    report = run.get("report")
    if not isinstance(report, dict) or report.get("status") != "pending":
        raise HwahapError("HW_STATE_INVALID", "terminal report requires a pending receipt")
    original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
    originals = {"run.json": (True, original_run), "report-data.json": (False, b""),
                 "report.html": (False, b""), "events.jsonl": (True, original_events)}
    marker_run = None
    try:
        units = [unit for _, _, unit in read_unit_files(run_dir / "units")]
        events = parse_events(events_path) + [event]
        separator = b"\n" if original_events and not original_events.endswith(b"\n") else b""
        event_bytes = original_events + separator + (
            json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        working = json.loads(json.dumps(run))
        working["metrics"] = _terminal_metrics(working, units, event["timestamp"])
        unit_files = read_unit_files(run_dir / "units")
        unit_bytes = b"".join(path.name.encode() + b"\0" + raw
                              for path, raw, _ in unit_files)
        digests = {"contract": sha256_file(contract_path),
                   "events": "sha256:" + hashlib.sha256(event_bytes).hexdigest(),
                   "units": "sha256:" + hashlib.sha256(unit_bytes).hexdigest()}
        artifacts = prepare_report_artifacts(
            workspace, read_json(contract_path), working, units, events, digests)
        working["report"] = {**report, "schema_version": REPORT_SCHEMA_VERSION,
            "status": "completed", "generator": REPORT_GENERATOR.copy(),
            "source_payload_sha256": artifacts["source_payload_sha256"],
            "data": {"path": "report-data.json", "file_sha256": artifacts["data_file_sha256"]},
            "html": {"path": "report.html", "file_sha256": artifacts["html_file_sha256"]},
            "generated_at": event["timestamp"], "redaction_policy": REPORT_REDACTION_POLICY}
        target = {"run.json": _json_bytes(working),
                  "report-data.json": artifacts["data_bytes"],
                  "report.html": artifacts["html_bytes"], "events.jsonl": event_bytes}
        journal, marker_run = _recovery_setup(operation, originals, target)
        _write_report_recovery_journal(run_dir, journal)
        _atomic_replace_bytes(run_path, marker_run)
        _atomic_replace_bytes(data_path, target["report-data.json"])
        _atomic_replace_bytes(report_path, target["report.html"])
        _atomic_replace_bytes(run_path, target["run.json"])
        _atomic_replace_bytes(events_path, event_bytes)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=run["goal_id"],
                                        quiet=True, _skip_recovery=True))
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not finalize terminal report")
    except Exception as exc:
        _restore_report_recovery(run_dir, originals, marker_run)
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not generate terminal report") from None
