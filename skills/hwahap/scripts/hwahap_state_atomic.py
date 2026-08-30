"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
_REPORT_RECOVERY_NAME = ".report-recovery.json"
_REPORT_RECOVERY_FILES = ("run.json", "report-data.json", "report.html", "events.jsonl")
_REPORT_RECOVERY_LIMIT = 128 * 1024 * 1024
_REPORT_TEMP_COUNTER = 0


def _report_recovery_path(run_dir: Path) -> Path:
    return run_dir / _REPORT_RECOVERY_NAME


def _json_bytes(value: dict) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _atomic_replace_bytes(path: Path, data: bytes) -> None:
    global _REPORT_TEMP_COUNTER
    _REPORT_TEMP_COUNTER += 1
    temp = path.parent / (f".{path.name}.tmp-{os.getpid()}-{_REPORT_TEMP_COUNTER}")
    fd, created = None, False
    try:
        fd = os.open(str(temp), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        created = True
        offset = 0
        while offset < len(data):
            written = os.write(fd, data[offset:])
            if written <= 0:
                raise OSError
            offset += written
        os.close(fd)
        fd = None
        os.replace(str(temp), str(path))
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            if created and (temp.is_file() or temp.is_symlink()):
                temp.unlink()
        except Exception:
            pass
        raise


def _recovery_record(exists: bool, data: bytes) -> dict:
    return {"exists": exists, "length": len(data),
            "sha256": "sha256:" + hashlib.sha256(data).hexdigest() if exists else None,
            "data": base64.b64encode(data).decode("ascii") if exists else None}


def _recovery_setup(operation: str, originals: dict[str, tuple[bool, bytes]], target: dict[str, bytes]) -> tuple[bytes, bytes]:
    if operation not in {"complete", "terminal", "goal_complete_sync"} or set(originals) != set(_REPORT_RECOVERY_FILES) or set(target) != set(_REPORT_RECOVERY_FILES):
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid")
    identity = operation.encode() + b"".join(originals[name][1] for name in _REPORT_RECOVERY_FILES) + b"".join(target[name] for name in _REPORT_RECOVERY_FILES)
    transaction_id = "sha256:" + hashlib.sha256(identity).hexdigest()
    value = {"schema_version": 2, "transaction_id": transaction_id, "operation": operation,
             "originals": {name: _recovery_record(*originals[name]) for name in _REPORT_RECOVERY_FILES},
             "target": {name: _recovery_record(True, target[name]) for name in _REPORT_RECOVERY_FILES}}
    journal_bytes = _json_bytes(value)
    journal_sha = "sha256:" + hashlib.sha256(journal_bytes).hexdigest()
    marker = {"transaction_id": transaction_id, "operation": operation, "journal_sha256": journal_sha}
    marker_run = json.loads(target["run.json"].decode("utf-8"))
    marker_run["report_transaction"] = marker
    return journal_bytes, _json_bytes(marker_run)


def _write_report_recovery_journal(run_dir: Path, journal_bytes: bytes) -> None:
    path = _report_recovery_path(run_dir)
    if path.is_symlink() or path.exists():
        raise HwahapError("HW_STATE_INVALID", "report recovery journal is invalid")
    fd = None
    try:
        fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        if os.fstat(fd).st_nlink != 1:
            raise OSError
        offset = 0
        while offset < len(journal_bytes):
            offset += os.write(fd, journal_bytes[offset:])
        os.close(fd)
        fd = None
    except Exception:
        if fd is not None:
            try:
                os.close(fd)
            except Exception:
                pass
        try:
            if path.is_file() and not path.is_symlink():
                path.unlink()
        except Exception:
            pass
        raise HwahapError("HW_STATE_INVALID", "could not write report recovery journal") from None
