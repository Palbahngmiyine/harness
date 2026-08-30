"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def complete_run(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    events_path = run_dir / "events.jsonl"
    data_path = run_dir / "report-data.json"
    report_path = run_dir / "report.html"
    if any(path.exists() or path.is_symlink() for path in (data_path, report_path)):
        raise HwahapError("HW_STATE_INVALID", "report artifacts already exist; complete will not overwrite them")
    contract, run = read_json(contract_path), read_json(run_path)
    unit_files = read_unit_files(run_dir / "units")
    unit_paths = [path for path, _, _ in unit_files]
    units = [unit for _, _, unit in unit_files]
    final_errors: list[str] = []
    validate_final_review(run.get("final_review"), True, final_errors, workspace)
    final_status = run.get("final_review", {}).get("status") if isinstance(run.get("final_review"), dict) else None
    goal = run.get("goal_link", {}).get("current", {}) if isinstance(run.get("goal_link"), dict) else {}
    report = run.get("report")
    if (run.get("status") != "final_review" or final_status != "pass"
            or final_errors or not contract.get("locked") or not units or any(unit.get("status") != "passed" for unit in units)):
        raise HwahapError("HW_STATE_INVALID", "complete requires a valid final_review, locked contract, and passed units")
    final_digest = final_review_passing_digest(run.get("final_review"), workspace)
    if (not isinstance(args.input_digest, str) or not SHA256.fullmatch(args.input_digest)
            or not isinstance(final_digest, str) or args.input_digest != final_digest):
        raise HwahapError("HW_STATE_INVALID", "complete input digest must match the final passing review digest")
    if not isinstance(goal, dict) or goal.get("mode") == "unobserved":
        raise HwahapError("HW_STATE_INVALID", "complete requires an observed Goal link")
    if not isinstance(report, dict) or report.get("status") != "pending":
        raise HwahapError("HW_STATE_INVALID", "complete requires a pending report receipt")
    original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
    originals = {
        "run.json": (True, original_run), "report-data.json": (False, b""),
        "report.html": (False, b""), "events.jsonl": (True, original_events),
    }
    marker_run_bytes = None
    try:
        events = parse_events(events_path)
        event = transition_event(len(events) + 1, "run", "final_review", "completed", argparse.Namespace(
            actor=args.actor, role="orchestrator", reason=args.reason,
            input_digest=args.input_digest, evidence_ref=args.evidence_ref, review_round=0,
        ))
        completed_at = utc_now()
        started = datetime.fromisoformat(str(run.get("started_at")).replace("Z", "+00:00"))
        elapsed = max(0, int((datetime.fromisoformat(completed_at) - started).total_seconds()))
        histories = [unit.get("review_history", []) for unit in units]
        metrics = run.get("metrics") if isinstance(run.get("metrics"), dict) else {}
        metrics.update({
            "unit_count": len(units), "review_rounds": sum(len(history) for history in histories if isinstance(history, list)),
            "recoveries": sum(bool(history and history[0].get("outcome") == "fail") for history in histories if isinstance(history, list)),
            "replans": sum(sum(record.get("kind") in {"sol_replan", "recursive_improvement"} for record in unit.get("improvement_history", []) if isinstance(record, dict)) for unit in units),
            "scope_deviations": len(run.get("deviations", [])) if isinstance(run.get("deviations"), list) else 0,
            "test_runs": sum(len(unit.get("test_receipts", [])) for unit in units if isinstance(unit.get("test_receipts"), list)),
            "elapsed_seconds": elapsed,
        })
        working_run = json.loads(json.dumps(run))
        working_run.update({"status": "completed", "completed_at": completed_at, "metrics": metrics})
        completed_events = events + [event]
        separator = b"\n" if original_events and not original_events.endswith(b"\n") else b""
        event_bytes = original_events + separator + (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        unit_bytes = b"".join(path.name.encode() + b"\0" + raw for path, raw, _ in unit_files)
        digests = {
            "contract": sha256_file(contract_path), "events": "sha256:" + hashlib.sha256(event_bytes).hexdigest(),
            "units": "sha256:" + hashlib.sha256(unit_bytes).hexdigest(),
        }
        artifacts = prepare_report_artifacts(workspace, contract, working_run, units, completed_events, digests)
        source_digest = artifacts["source_payload_sha256"]
        report_bytes = artifacts["html_bytes"]
        working_run["report"] = {**report, "schema_version": REPORT_SCHEMA_VERSION, "status": "completed",
                                  "generator": REPORT_GENERATOR.copy(),
                                  "source_payload_sha256": source_digest,
                                  "data": {"path": "report-data.json", "file_sha256": artifacts["data_file_sha256"]},
                                  "html": {"path": "report.html", "file_sha256": artifacts["html_file_sha256"]},
                                  "redaction_policy": REPORT_REDACTION_POLICY, "generated_at": event["timestamp"]}
        target = {"run.json": _json_bytes(working_run), "report-data.json": artifacts["data_bytes"],
                  "report.html": report_bytes, "events.jsonl": event_bytes}
        journal_bytes, marker_run_bytes = _recovery_setup("complete", originals, target)
        _write_report_recovery_journal(run_dir, journal_bytes)
        _atomic_replace_bytes(run_path, marker_run_bytes)
        _atomic_replace_bytes(data_path, artifacts["data_bytes"])
        _atomic_replace_bytes(report_path, report_bytes)
        _atomic_replace_bytes(run_path, target["run.json"])
        _atomic_replace_bytes(events_path, event_bytes)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True, _skip_recovery=True))
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not finalize completed report")
    except Exception:
        _restore_report_recovery(run_dir, originals, marker_run_bytes)
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not generate completed report") from None
    print(f"HW_OK: run={args.run_id} completed report={report_path}")
