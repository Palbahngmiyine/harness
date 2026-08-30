"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _bounded_scope_text(value: str) -> str:
    if len(value) <= SCOPE_DRIFT_TEXT_LIMIT:
        return value
    return value[:SCOPE_DRIFT_TEXT_LIMIT - 3] + "..."


def _scope_drift_digest(paths: list[str], command_digests: list[str]) -> str:
    payload = json.dumps({"allowed_paths": paths, "acceptance_commands": command_digests},
                         ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def record_add_unit_scope_drift(run_dir: Path, run_path: Path, args: argparse.Namespace,
                               paths: list[str], commands: list[str]) -> None:
    """Gate safe but out-of-contract unit inputs without creating a unit."""
    events_path = run_dir / "events.jsonl"
    original_events = events_path.read_bytes()
    command_digests = ["sha256:" + hashlib.sha256(command.encode("utf-8")).hexdigest()
                       for command in commands]
    path_limit = SCOPE_DRIFT_EVIDENCE_LIMIT - 1 if command_digests else SCOPE_DRIFT_EVIDENCE_LIMIT
    evidence = [f"safe path outside locked contract: {_bounded_scope_text(path)}"
                for path in paths[:path_limit]]
    evidence.extend(
        f"acceptance command outside locked contract; digest={digest}"
        for digest in command_digests[:SCOPE_DRIFT_EVIDENCE_LIMIT]
    )
    # The caller has already established that at least one safe drift exists.
    evidence = evidence[:SCOPE_DRIFT_EVIDENCE_LIMIT]
    input_digest = (command_digests[0] if len(command_digests) == 1 and not paths
                    else _scope_drift_digest(paths, command_digests))
    failure = {
        "code": "HW_SCOPE_DRIFT", "reason": SCOPE_DRIFT_REASON,
        "evidence": evidence, "recovery": SCOPE_DRIFT_RECOVERY,
    }
    run = read_json(run_path)
    event_lines = [line for line in original_events.decode("utf-8").splitlines() if line.strip()]
    event = transition_event(len(event_lines) + 1, "run", "contract_locked", "awaiting_user",
                             argparse.Namespace(
                                 actor=SCOPE_DRIFT_ACTOR, role="orchestrator",
                                 reason=SCOPE_DRIFT_REASON, input_digest=input_digest,
                                 evidence_ref=evidence, review_round=0,
                             ))
    run["status"] = "awaiting_user"
    run["failure"] = failure
    try:
        publish_terminal_report(run_dir.parents[2], run_dir, run_dir / "contract.json",
                                run_path, run, event)
    except Exception as exc:
        if isinstance(exc, HwahapError):
            raise
        raise HwahapError("HW_SCOPE_DRIFT", "could not record scope drift; user decision is still required") from exc
    raise HwahapError("HW_SCOPE_DRIFT", SCOPE_DRIFT_REASON)
