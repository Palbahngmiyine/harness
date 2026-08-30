"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def run_test(args: argparse.Namespace) -> None:
    raise HwahapError("HW_TEST_EXECUTION_DISABLED", "test execution is disabled; use an authorized Luna verifier and record-test-receipt")


def record_test_receipt(args: argparse.Namespace) -> None:
    unit_id = require_safe_unit_id(args.unit_id)
    workspace, run_dir, contract_path, run_path = command_paths(args.workspace, args.run_id)
    validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    require_run_unit_mutation_allowed(run_path)
    contract, run = read_json(contract_path), read_json(run_path)
    if not contract.get("locked") or run.get("status") != "reviewing":
        raise HwahapError("HW_STATE_INVALID", "record-test-receipt requires a locked reviewing run")
    unit_path = run_dir / "units" / f"{unit_id}.json"
    if unit_path.is_symlink() or not unit_path.is_file():
        raise HwahapError("HW_STATE_INVALID", "unit must be a regular file")
    unit = read_json(unit_path)
    if unit.get("status") != "reviewing":
        raise HwahapError("HW_STATE_INVALID", "record-test-receipt requires a reviewing unit")
    index = args.command_index
    commands = unit.get("acceptance_commands")
    if (not isinstance(index, int) or isinstance(index, bool) or not isinstance(commands, list)
            or not 1 <= index <= len(commands) or not isinstance(commands[index - 1], str)):
        raise HwahapError("HW_STATE_INVALID", "command_index is outside acceptance_commands")
    if (not isinstance(args.execution_receipt_sha256, str) or not SHA256.fullmatch(args.execution_receipt_sha256)
            or not required_text(args.observer_thread_id) or not isinstance(args.diff_digest, str)
            or not SHA256.fullmatch(args.diff_digest) or not required_text(args.started_at)
            or not required_text(args.ended_at) or not isinstance(args.output_sha256, str)
            or not SHA256.fullmatch(args.output_sha256)):
        raise HwahapError("HW_STATE_INVALID", "external test receipt fields are invalid")
    snapshot = git_diff_snapshot(workspace, getattr(args, "base_commit", None), getattr(args, "target_commit", None))
    if args.diff_digest != snapshot["diff_digest"]:
        raise HwahapError("HW_STATE_INVALID", "test receipt diff digest does not match Git snapshot")
    timed_out = bool(getattr(args, "timed_out", False))
    exit_code = getattr(args, "exit_code", None)
    if timed_out == (exit_code is not None) or (exit_code is not None and (
            not isinstance(exit_code, int) or isinstance(exit_code, bool))):
        raise HwahapError("HW_STATE_INVALID", "provide exactly one of exit-code or timed-out")
    status = "timeout" if timed_out else "pass" if exit_code == 0 else "fail"
    receipts = unit.get("test_receipts")
    if not isinstance(receipts, list) or any(
            isinstance(receipt, dict) and receipt.get("execution_receipt_sha256") == args.execution_receipt_sha256
            for receipt in receipts):
        raise HwahapError("HW_STATE_INVALID", "duplicate execution receipt")
    for other_path in sorted((run_dir / "units").glob("*.json")):
        if other_path == unit_path:
            continue
        other = read_json(other_path)
        other_receipts = other.get("test_receipts")
        if isinstance(other_receipts, list) and any(
                isinstance(receipt, dict) and receipt.get("execution_receipt_sha256") == args.execution_receipt_sha256
                for receipt in other_receipts):
            raise HwahapError("HW_STATE_INVALID", "duplicate execution receipt")
    occurrence = sum(isinstance(receipt, dict) and receipt.get("command_index") == index for receipt in receipts) + 1
    receipt = {
        "test_id": f"test-{index}-{occurrence}", "command_index": index,
        "command_sha256": "sha256:" + hashlib.sha256(commands[index - 1].encode("utf-8")).hexdigest(),
        "source": "codex.exec_command", "execution_receipt_sha256": args.execution_receipt_sha256,
        "observer_role": "verifier", "observer_thread_id": args.observer_thread_id,
        "diff_snapshot": snapshot, "diff_digest": snapshot["diff_digest"],
        "started_at": args.started_at, "ended_at": args.ended_at,
        "exit_code": None if timed_out else exit_code, "output_sha256": args.output_sha256, "status": status,
    }
    try:
        original = ((unit_path, unit_path.read_bytes()), (run_path, run_path.read_bytes()))
    except Exception as exc:
        raise HwahapError("HW_STATE_INVALID", "could not snapshot receipt state") from exc
    receipts.append(receipt)
    run["metrics"]["test_runs"] = sum(
        len(item.get("test_receipts", [])) for item in
        [read_json(path) for path in sorted((run_dir / "units").glob("*.json"))]
        if isinstance(item.get("test_receipts"), list)
    ) + 1
    try:
        write_json(unit_path, unit)
        write_json(run_path, run)
        validate_run(argparse.Namespace(workspace=str(workspace), run_id=args.run_id, quiet=True))
    except Exception as exc:
        restore_state_files(original)
        raise HwahapError("HW_STATE_INVALID", "could not record test receipt") from exc
    print(f"HW_OK: run={args.run_id} unit={args.unit_id} test={receipt['test_id']} status={status}")
