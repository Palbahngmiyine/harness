"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _recover_report_transaction(run_dir: Path) -> None:
    journal = _read_report_recovery_journal(run_dir)
    if journal is None:
        run_path = run_dir / "run.json"
        try:
            if run_path.is_file() and not run_path.is_symlink():
                try:
                    marker = json.loads(run_path.read_bytes().decode("utf-8")).get("report_transaction")
                except (UnicodeError, json.JSONDecodeError):
                    return
                if marker is not None:
                    raise HwahapError("HW_STATE_INVALID", "orphan report recovery marker")
        except HwahapError:
            raise
        except Exception:
            raise HwahapError("HW_STATE_INVALID", "could not inspect report recovery marker") from None
        return
    originals = {name: journal[name] for name in _REPORT_RECOVERY_FILES}
    target = journal["__target__"]
    meta = journal["__meta__"]
    current: dict[str, bytes | None] = {}
    for name in _REPORT_RECOVERY_FILES:
        path = run_dir / name
        try:
            if path.is_symlink() or path.is_dir() or (path.exists() and path.stat().st_nlink != 1):
                raise ValueError
            if path.exists() and not path.is_file():
                raise ValueError
            current[name] = path.read_bytes() if path.exists() else None
        except HwahapError:
            raise
        except Exception:
            raise HwahapError("HW_STATE_INVALID", "could not inspect report recovery targets") from None
    original_set = {name: data if exists else None for name, (exists, data) in originals.items()}
    target_set = {name: target[name] for name in _REPORT_RECOVERY_FILES}
    marker = None
    try:
        run_value = json.loads((run_dir / "run.json").read_bytes().decode("utf-8"))
        marker = run_value.get("report_transaction") if isinstance(run_value, dict) else None
    except Exception:
        raise HwahapError("HW_STATE_INVALID", "report recovery marker is invalid") from None
    if marker is not None and (not isinstance(marker, dict) or set(marker) != {"transaction_id", "operation", "journal_sha256"}
                               or marker.get("transaction_id") != meta["transaction_id"]
                               or marker.get("operation") != meta["operation"]
                               or marker.get("journal_sha256") != meta["journal_sha256"]):
        raise HwahapError("HW_STATE_INVALID", "report recovery marker is invalid")
    if marker is None:
        if current in (original_set, target_set):
            if not _clear_report_recovery_journal(run_dir):
                raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")
            return
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is unbound")
    marker_run = json.loads(target["run.json"].decode("utf-8"))
    marker_run["report_transaction"] = marker
    marker_set = dict(target_set, **{"run.json": _json_bytes(marker_run)})
    if current == marker_set:
        _atomic_replace_bytes(run_dir / "run.json", target["run.json"])
        if not _clear_report_recovery_journal(run_dir):
            raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")
        return
    marker_run = _json_bytes(dict(json.loads(target["run.json"].decode("utf-8")), report_transaction=marker))
    if not _restore_report_recovery(run_dir, originals, marker_run):
        raise HwahapError("HW_STATE_INVALID", "report recovery is incomplete")
