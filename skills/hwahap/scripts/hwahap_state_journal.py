"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _read_report_recovery_journal(run_dir: Path) -> dict[str, tuple[bool, bytes]] | None:
    path = _report_recovery_path(run_dir)
    try:
        if path.is_symlink():
            raise ValueError
        if not path.exists():
            return None
        if not path.is_file() or path.stat().st_nlink != 1 or path.stat().st_size > _REPORT_RECOVERY_LIMIT:
            raise ValueError
        journal_bytes = path.read_bytes()
        if len(journal_bytes) > _REPORT_RECOVERY_LIMIT:
            raise ValueError
        journal_digest = "sha256:" + hashlib.sha256(journal_bytes).hexdigest()
        value = json.loads(journal_bytes.decode("utf-8"))
        if not isinstance(value, dict) or set(value) != {"schema_version", "transaction_id", "operation", "originals", "target"} or value.get("schema_version") != 2:
            raise ValueError
        if not isinstance(value.get("transaction_id"), str) or not SHA256.fullmatch(value["transaction_id"]):
            raise ValueError
        if value.get("operation") not in {"complete", "terminal", "goal_complete_sync"}:
            raise ValueError
        files = value.get("originals")
        target = value.get("target")
        if not isinstance(files, dict) or not isinstance(target, dict) or set(files) != set(_REPORT_RECOVERY_FILES) or set(target) != set(_REPORT_RECOVERY_FILES):
            raise ValueError
        result: dict[str, tuple[bool, bytes]] = {}
        for name in _REPORT_RECOVERY_FILES:
            for item in (files[name], target[name]):
                if not isinstance(item, dict) or set(item) != {"exists", "length", "sha256", "data"} or not isinstance(item.get("exists"), bool):
                    raise ValueError
                data = base64.b64decode(item["data"], validate=True) if item["exists"] and isinstance(item.get("data"), str) else b""
                if item["exists"] != (item.get("data") is not None) or item.get("length") != len(data) or item.get("sha256") != ("sha256:" + hashlib.sha256(data).hexdigest() if item["exists"] else None):
                    raise ValueError
            result[name] = (bool(files[name]["exists"]), base64.b64decode(files[name]["data"], validate=True) if files[name]["exists"] else b"")
        result["__target__"] = {name: base64.b64decode(target[name]["data"], validate=True) for name in _REPORT_RECOVERY_FILES}  # type: ignore[assignment]
        result["__meta__"] = {"transaction_id": value["transaction_id"], "operation": value["operation"], "journal_sha256": journal_digest}  # type: ignore[assignment]
        if (not result["run.json"][0] or not result["events.jsonl"][0]
                or value["operation"] in {"complete", "terminal"} and (result["report-data.json"][0] or result["report.html"][0])
                or value["operation"] == "goal_complete_sync" and (not result["report-data.json"][0] or not result["report.html"][0])):
            raise ValueError
        return result
    except Exception:
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid") from None


def _restore_report_recovery(run_dir: Path, originals: dict[str, tuple[bool, bytes]], marker_run: bytes | None = None) -> bool:
    complete = True
    for name in _REPORT_RECOVERY_FILES:
        exists, data = originals[name]
        path = run_dir / name
        try:
            if path.is_symlink() or path.is_dir() or (path.exists() and path.stat().st_nlink != 1):
                complete = False
                continue
            if exists:
                if path.exists() and not path.is_file():
                    complete = False
                    continue
                _atomic_replace_bytes(path, data)
            elif path.exists():
                path.unlink()
        except Exception:
            complete = False
    journal = _report_recovery_path(run_dir)
    if not complete and marker_run is not None:
        try:
            _atomic_replace_bytes(run_dir / "run.json", marker_run)
        except Exception:
            pass
    if complete:
        try:
            if journal.is_symlink() or (journal.exists() and (not journal.is_file() or journal.stat().st_nlink != 1)):
                complete = False
            elif journal.exists():
                journal.unlink()
        except Exception:
            complete = False
    return complete


def _clear_report_recovery_journal(run_dir: Path) -> bool:
    journal = _report_recovery_path(run_dir)
    try:
        if journal.is_symlink() or (journal.exists() and (not journal.is_file() or journal.stat().st_nlink != 1)):
            return False
        if journal.exists():
            journal.unlink()
        return True
    except Exception:
        return False
