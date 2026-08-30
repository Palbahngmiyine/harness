"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def goal_sync(args: argparse.Namespace) -> None:
    workspace, _, _, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    run = read_json(run_path)
    goal_link = run.get("goal_link")
    if not isinstance(goal_link, dict) or not isinstance(goal_link.get("history"), list):
        raise HwahapError("HW_STATE_INVALID", "goal_link must contain current and history")
    mode = args.mode
    token_total = getattr(args, "token_total", None)
    if token_total is not None and (mode != "bound" or not isinstance(token_total, int) or isinstance(token_total, bool) or token_total < 0):
        raise HwahapError("HW_STATE_INVALID", "token-total is only a nonnegative integer for bound Goal receipts")
    if mode not in GOAL_MODES - {"unobserved"}:
        raise HwahapError("HW_STATE_INVALID", "goal-sync mode is invalid")
    if not required_text(args.reason) or not isinstance(args.evidence_ref, list) or not args.evidence_ref:
        raise HwahapError("HW_STATE_INVALID", "goal-sync reason and evidence are required")
    if any(not required_text(ref) for ref in args.evidence_ref):
        raise HwahapError("HW_STATE_INVALID", "goal-sync evidence must be nonempty text")
    if mode == "bound":
        if (not required_text(args.thread_id) or not isinstance(args.objective_sha256, str)
                or not SHA256.fullmatch(args.objective_sha256)
                or not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)):
            raise HwahapError("HW_STATE_INVALID", "bound Goal receipt is incomplete")
        bound_pairs = {
            (entry.get("thread_id"), entry.get("objective_sha256"))
            for entry in goal_link["history"] if isinstance(entry, dict) and entry.get("mode") == "bound"
        }
        if bound_pairs and (args.thread_id, args.objective_sha256) not in bound_pairs:
            raise HwahapError("HW_STATE_INVALID", "Goal binding cannot change thread or objective")
        external_status = "active"
        source = "codex.get_goal"
        completion_sync = "pending"
    else:
        if args.thread_id is not None or args.objective_sha256 is not None:
            raise HwahapError("HW_STATE_INVALID", "unbound Goal receipt must clear thread and objective")
        if mode == "unavailable" and args.receipt_sha256 is not None:
            raise HwahapError("HW_STATE_INVALID", "unavailable Goal receipt must not include a receipt hash")
        if mode == "no_active_goal" and (
                not isinstance(args.receipt_sha256, str) or not SHA256.fullmatch(args.receipt_sha256)):
            raise HwahapError("HW_STATE_INVALID", "no-active Goal receipt hash is invalid")
        if any(isinstance(entry, dict) and entry.get("mode") == "bound" for entry in goal_link["history"]):
            raise HwahapError("HW_STATE_INVALID", "bound Goal link cannot downgrade to an unbound receipt")
        external_status = "unknown"
        source = "codex.get_goal"
        completion_sync = "not_applicable"
    record = {
        "mode": mode, "source": source, "thread_id": args.thread_id if mode == "bound" else None,
        "external_status": external_status,
        "objective_sha256": args.objective_sha256 if mode == "bound" else None,
        "receipt_sha256": args.receipt_sha256 if mode != "unavailable" else None,
        "reason": args.reason, "evidence": args.evidence_ref,
        "observed_at": utc_now(), "completion_sync": completion_sync, "sync_result": None,
        "token_total": token_total if mode == "bound" else None,
    }
    run["metrics"]["token_usage"] = (
        {"availability": "available", "source": "codex.get_goal", "total": token_total, "reason": None}
        if mode == "bound" and token_total is not None else
        {"availability": "unavailable", "source": None, "total": None, "reason": "platform aggregate not exposed"}
    )
    try:
        original = ((run_path, run_path.read_bytes()),)
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot Goal state") from exc
    goal_link["current"] = record
    goal_link["history"].append(record.copy())
    try:
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        raise HwahapError("HW_STATE_INVALID", "could not synchronize Goal state") from exc
    print(f"HW_OK: run={args.run_id} goal_mode={mode}")
