"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def goal_complete_sync(args: argparse.Namespace) -> None:
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    data_path = run_dir / "report-data.json"
    report_path = run_dir / "report.html"
    if not _single_regular_file(data_path) or not _single_regular_file(report_path):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync requires completed report artifacts")
    contract, run = read_json(contract_path), read_json(run_path)
    goal_link = run.get("goal_link")
    current = goal_link.get("current") if isinstance(goal_link, dict) else None
    if (run.get("status") != "completed" or not isinstance(current, dict) or current.get("mode") != "bound"
            or current.get("source") == "codex.update_goal" and current.get("completion_sync") == "completed"):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync requires a bound completed run")
    if (not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)
            or args.sync_result not in {"completed", "already_completed", "failed"}
            or not required_text(args.reason) or not args.evidence_ref or any(not required_text(ref) for ref in args.evidence_ref)):
        raise HwahapError("HW_STATE_INVALID", "goal completion sync receipt is incomplete")
    token_total = getattr(args, "token_total", None)
    if args.sync_result in {"completed", "already_completed"}:
        if not isinstance(token_total, int) or isinstance(token_total, bool) or token_total < 0:
            raise HwahapError("HW_STATE_INVALID", "successful Goal completion sync requires token-total")
    elif token_total is not None:
        raise HwahapError("HW_STATE_INVALID", "failed Goal completion sync must not include token-total")
    original_run, original_data, original_report = run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes()
    originals = {
        "run.json": (True, original_run), "report-data.json": (True, original_data),
        "report.html": (True, original_report), "events.jsonl": (True, (run_dir / "events.jsonl").read_bytes()),
    }
    marker_run_bytes = None
    try:
        units = [read_json(path) for path in sorted((run_dir / "units").glob("*.json"))]
        events = parse_events(run_dir / "events.jsonl")
        record = {
            "mode": "bound", "source": "codex.update_goal", "thread_id": current.get("thread_id"),
            "external_status": "completed" if args.sync_result in {"completed", "already_completed"} else "active",
            "objective_sha256": current.get("objective_sha256"), "receipt_sha256": args.receipt_sha256,
            "reason": args.reason, "evidence": args.evidence_ref, "observed_at": utc_now(),
            "completion_sync": "completed" if args.sync_result in {"completed", "already_completed"} else "failed",
            "sync_result": args.sync_result, "token_total": token_total if args.sync_result in {"completed", "already_completed"} else None,
        }
        working_run = json.loads(json.dumps(run))
        working_run["goal_link"]["current"] = record
        working_run["goal_link"]["history"].append(record.copy())
        if args.sync_result in {"completed", "already_completed"}:
            working_run["metrics"]["token_usage"] = {
                "availability": "available", "source": "codex.update_goal", "total": token_total, "reason": None,
            }
        artifacts = prepare_report_artifacts(workspace, contract, working_run, units, events,
                                              report_state_digests(contract_path, run_dir / "events.jsonl", run_dir / "units"))
        source_digest = artifacts["source_payload_sha256"]
        report_bytes = artifacts["html_bytes"]
        working_run["report"] = {**run["report"], "schema_version": REPORT_SCHEMA_VERSION, "status": "completed",
                                  "generator": REPORT_GENERATOR.copy(), "source_payload_sha256": source_digest,
                                  "data": {"path": "report-data.json", "file_sha256": artifacts["data_file_sha256"]},
                                  "html": {"path": "report.html", "file_sha256": artifacts["html_file_sha256"]},
                                  "redaction_policy": REPORT_REDACTION_POLICY, "generated_at": record["observed_at"]}
        target = {"run.json": _json_bytes(working_run), "report-data.json": artifacts["data_bytes"],
                  "report.html": report_bytes, "events.jsonl": (run_dir / "events.jsonl").read_bytes()}
        journal_bytes, marker_run_bytes = _recovery_setup("goal_complete_sync", originals, target)
        _write_report_recovery_journal(run_dir, journal_bytes)
        _atomic_replace_bytes(run_path, marker_run_bytes)
        _atomic_replace_bytes(data_path, artifacts["data_bytes"])
        _atomic_replace_bytes(report_path, report_bytes)
        _atomic_replace_bytes(run_path, target["run.json"])
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True, _skip_recovery=True))
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not finalize Goal completion report")
    except Exception:
        _restore_report_recovery(run_dir, originals, marker_run_bytes)
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "Goal completion report generation failed") from None
    print(f"HW_OK: run={args.run_id} goal_completion_sync={args.sync_result}")
