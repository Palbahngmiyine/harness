"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not read state JSON") from exc
    if not isinstance(value, dict):
        raise HwahapError("HW_STATE_INVALID", "state JSON must contain an object")
    return value


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def restore_state_files(originals: tuple[tuple[Path, bytes], ...]) -> None:
    for path, data in originals:
        try:
            path.write_bytes(data)
        except Exception:
            pass

def remove_path_best_effort(path: Path) -> None:
    try:
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            path.rmdir()
    except Exception:
        pass


def canonical_contract_digest(contract: dict) -> str:
    payload = {key: value for key, value in contract.items() if key != "lock_sha256"}
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def frontmatter(path: Path, *, expected_status: str = "prfaq", error_code: str = "HW_SPEC_UNCONFIRMED") -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    match = re.match(r"\A---\n(.*?)\n---(?:\n|\Z)", text, re.DOTALL)
    if not match:
        raise HwahapError(error_code, "spec has no YAML frontmatter" if error_code == "HW_SPEC_UNCONFIRMED" else "request has no YAML frontmatter")
    if credential_bearing_text(match.group(1)):
        raise HwahapError("HW_STATE_INVALID", "frontmatter contains credential-bearing text")
    values: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip().strip('"\'')
    if values.get("status") != expected_status or not values.get("confirmed_at"):
        label = "spec" if error_code == "HW_SPEC_UNCONFIRMED" else "request"
        raise HwahapError(
            error_code,
            f"{label} must have status={expected_status} and confirmed_at",
        )
    if not values.get("title"):
        raise HwahapError(error_code, "spec title is required" if error_code == "HW_SPEC_UNCONFIRMED" else "request title is required")
    return values


def state_paths(workspace: Path, run_id: str) -> tuple[Path, Path]:
    if not SLUG.fullmatch(run_id):
        raise HwahapError("HW_STATE_INVALID", "unsafe run ID")
    hwahap = workspace / ".hwahap"
    runs_dir = hwahap / "runs"
    run_dir = runs_dir / run_id
    for label, path in ((".hwahap", hwahap), ("runs", runs_dir), ("run", run_dir)):
        if path.is_symlink() or (path.exists() and not path.is_dir()):
            raise HwahapError("HW_STATE_INVALID", f"{label} must be a real directory")
    return hwahap, run_dir


def _single_regular_file(path: Path) -> bool:
    try:
        return not path.is_symlink() and path.is_file() and path.stat().st_nlink == 1
    except (OSError, UnicodeError):
        raise HwahapError("HW_STATE_INVALID", "state file is invalid") from None


def lexical_path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts:
        if part in (path.anchor, ""):
            continue
        current /= part
        if current.is_symlink():
            return True
    return False
