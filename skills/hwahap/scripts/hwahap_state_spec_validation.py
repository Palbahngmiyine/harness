"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def validate_approved_spec(workspace: Path, spec: dict, contract: dict, errors: list[str]) -> None:
    source = spec.get("source")
    source_path = Path(source) if isinstance(source, str) else workspace / "<invalid-spec-source>"
    if not source_path.is_absolute():
        source_path = workspace / source_path
    if lexical_path_has_symlink(source_path) or source_path.is_symlink() or not source_path.is_file():
        errors.append("approved spec source is missing or unsafe")
        return
    status = spec.get("status", "prfaq")
    if status not in {"prfaq", "request", "align-goal"}:
        errors.append("approved spec status is invalid")
        return
    try:
        source_info = source_path.stat()
        if not stat.S_ISREG(source_info.st_mode) or source_info.st_nlink != 1:
            errors.append("approved spec source is not a regular file")
            return
        if status in {"request", "align-goal"} and source_path.suffix.casefold() != ".md":
            errors.append("input source must be Markdown")
            return
    except OSError:
        errors.append("approved spec source is invalid or unreadable")
        return
    try:
        actual_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
        metadata = load_goal_spec(source_path) if status == "align-goal" else \
            frontmatter(source_path, expected_status=status,
                        error_code="HW_REQUEST_UNCONFIRMED" if status == "request"
                        else "HW_SPEC_UNCONFIRMED")
    except (OSError, UnicodeError, HwahapError):
        errors.append("approved spec source is invalid or unreadable")
        return
    if actual_digest != spec.get("sha256"):
        errors.append("approved spec source hash does not match")
    if (metadata.get("status") != status
            or metadata.get("confirmed_at") != spec.get("confirmed_at")
            or metadata.get("title") != contract.get("goal")
            or metadata.get("handoff") != spec.get("handoff")):
        errors.append("approved spec frontmatter does not match contract")
