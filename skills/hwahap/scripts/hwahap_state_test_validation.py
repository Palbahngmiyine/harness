"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_test_receipts(unit: dict, errors: list[str], workspace: Path | None = None) -> dict[int, dict]:
    label = str(unit.get("unit_id"))
    commands = unit.get("acceptance_commands")
    receipts = unit.get("test_receipts")
    if not isinstance(receipts, list):
        errors.append(f"{label}: test_receipts must be a list")
        return {}
    latest: dict[int, dict] = {}
    occurrences: dict[int, int] = {}
    required = {"test_id", "command_index", "command_sha256", "source", "execution_receipt_sha256", "diff_snapshot",
                "observer_role", "observer_thread_id", "diff_digest", "started_at", "ended_at",
                "exit_code", "output_sha256", "status"}
    execution_receipts: set[str] = set()
    for receipt in receipts:
        if not isinstance(receipt, dict) or not required.issubset(receipt):
            errors.append(f"{label}: test receipt is incomplete")
            continue
        index = receipt.get("command_index")
        if not isinstance(index, int) or isinstance(index, bool) or not isinstance(commands, list) or not 1 <= index <= len(commands):
            errors.append(f"{label}: test receipt command_index is invalid")
            continue
        occurrences[index] = occurrences.get(index, 0) + 1
        if receipt.get("test_id") != f"test-{index}-{occurrences[index]}":
            errors.append(f"{label}: test receipt ID/order is invalid")
        command = commands[index - 1]
        expected_digest = "sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest() if isinstance(command, str) else None
        if receipt.get("command_sha256") != expected_digest or not isinstance(expected_digest, str):
            errors.append(f"{label}: test receipt command digest does not match")
        execution_digest = receipt.get("execution_receipt_sha256")
        if not isinstance(execution_digest, str) or not SHA256.fullmatch(execution_digest):
            errors.append(f"{label}: execution receipt digest is invalid")
        elif execution_digest in execution_receipts:
            errors.append(f"{label}: duplicate execution receipt")
        else:
            execution_receipts.add(execution_digest)
        if receipt.get("source") != "codex.exec_command" or receipt.get("observer_role") != "verifier":
            errors.append(f"{label}: test receipt source or observer role is invalid")
        if not required_text(receipt.get("observer_thread_id")):
            errors.append(f"{label}: observer thread ID is invalid")
        snapshot = validate_diff_snapshot(receipt.get("diff_snapshot"), workspace,
                                          f"{label}: test receipt diff_snapshot", errors)
        if snapshot is not None and receipt.get("diff_digest") != snapshot["diff_digest"]:
            errors.append(f"{label}: test receipt diff does not match snapshot")
        if not required_text(receipt.get("started_at")) or not required_text(receipt.get("ended_at")):
            errors.append(f"{label}: test receipt timestamps are invalid")
        if not isinstance(receipt.get("output_sha256"), str) or not SHA256.fullmatch(receipt["output_sha256"]):
            errors.append(f"{label}: test receipt output digest is invalid")
        status, exit_code = receipt.get("status"), receipt.get("exit_code")
        if status not in {"pass", "fail", "timeout"}:
            errors.append(f"{label}: test receipt status is invalid")
        elif (status == "pass" and exit_code != 0) or (status == "fail" and (not isinstance(exit_code, int) or isinstance(exit_code, bool) or exit_code == 0)) or (status == "timeout" and exit_code is not None):
            errors.append(f"{label}: test receipt status and exit_code disagree")
        latest[index] = receipt
    if unit.get("status") == "passed" and isinstance(commands, list) and any(latest.get(index, {}).get("status") != "pass" for index in range(1, len(commands) + 1)):
        errors.append(f"{label}: passed unit requires a passing latest receipt for every command")
    return latest
