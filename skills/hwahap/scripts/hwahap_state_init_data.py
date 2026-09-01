"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _init_input(args: argparse.Namespace) -> tuple[Path, Path, dict, str, dict[str, str], str]:
    input_kind, input_arg, expected_status, error_code = init_input_selection(args)
    workspace_arg = Path(args.workspace).expanduser()
    if lexical_path_has_symlink(workspace_arg):
        raise HwahapError("HW_STATE_INVALID", "workspace must not use symlink components")
    workspace = workspace_arg.resolve()
    spec_arg = Path(input_arg).expanduser()
    if lexical_path_has_symlink(spec_arg):
        raise HwahapError(error_code, "input must not use symlink components")
    spec = spec_arg.resolve()
    if not workspace.is_dir():
        raise HwahapError("HW_STATE_INVALID", "workspace must be a real directory")
    _require_hwahap_ignored(workspace)
    if not spec.is_file():
        raise HwahapError(error_code, "input must be a regular file")
    if input_kind == "request" and spec.suffix.casefold() != ".md":
        raise HwahapError(error_code, "request must be a Markdown file")
    try:
        info = spec.stat()
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise HwahapError(error_code, "input must be a regular non-linked file")
    except HwahapError:
        raise
    except OSError:
        raise HwahapError(error_code, "input cannot be inspected") from None
    try:
        meta = load_goal_spec(spec) if input_kind == "goal_spec" else \
            frontmatter(spec, expected_status=expected_status, error_code=error_code)
        spec_bytes = spec.read_bytes()
    except HwahapError:
        raise
    except (OSError, UnicodeError):
        raise HwahapError(error_code, "input cannot be read as UTF-8")
    return (workspace, spec, meta, hashlib.sha256(spec_bytes).hexdigest(),
            verify_installed_agents(workspace), error_code)


def _initial_state(goal_id: str, meta: dict, source: str, digest: str,
                   agent_profiles: dict[str, str], now: str) -> tuple[dict, dict]:
    contract = {
        "schema_version": 1, "goal_id": goal_id, "goal": meta["title"],
        "spec": input_spec_record(meta, source, digest),
        "locked": False, "lock_sha256": None,
        **{field: [] for field in CONTRACT_LISTS},
    }
    unavailable = {"availability": "unavailable",
                   "reason": "platform aggregate not exposed", "source": None, "total": None}
    run = {
        "schema_version": 1, "goal_id": goal_id, "status": "initialized",
        "started_at": now, "completed_at": None, "roles": ROLE_MAP,
        "agent_profiles": agent_profiles,
        "metrics": {"token_usage": unavailable.copy(), "unit_count": 0,
                    "agent_runs": unavailable.copy(), "review_rounds": 0,
                    "recoveries": 0, "replans": 0, "scope_deviations": 0,
                    "test_runs": 0, "elapsed_seconds": 0},
        "fast_status": "unknown", "deviations": [], "deferred_security": [],
        "improvement_candidates": [], "final_review": {"status": "pending", "attempts": []},
        "report": {"schema_version": REPORT_SCHEMA_VERSION, "status": "pending",
                   "generator": REPORT_GENERATOR.copy(), "source_payload_sha256": None,
                   "data": {"path": "report-data.json", "file_sha256": None},
                   "html": {"path": "report.html", "file_sha256": None},
                   "generated_at": None, "redaction_policy": REPORT_REDACTION_POLICY},
        "goal_link": {"current": {"mode": "unobserved", "source": None,
            "thread_id": None, "external_status": "unknown", "objective_sha256": None,
            "receipt_sha256": None, "reason": "Goal not observed", "evidence": ["init"],
            "observed_at": now, "sync_result": None, "token_total": None,
            "completion_sync": "pending"}, "history": []},
    }
    return contract, run


def _write_initial_state(workspace: Path, run_dir: Path, contract: dict, run: dict) -> None:
    contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
    events_path, units_dir = run_dir / "events.jsonl", run_dir / "units"
    created_dirs = create_state_directories(workspace, run_dir)
    try:
        write_json(contract_path, contract)
        write_json(run_path, run)
        events_path.write_text("", encoding="utf-8")
        events_path.chmod(0o600)
    except Exception as exc:
        for path in (contract_path, run_path, events_path):
            remove_path_best_effort(path)
        for path in reversed(created_dirs):
            remove_path_best_effort(path)
        raise HwahapError("HW_STATE_INVALID", "could not initialize run state") from exc
