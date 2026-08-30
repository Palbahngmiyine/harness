"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def report_module():
    if _report_module is None:
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "report dependency unavailable") from None
    return _report_module


def sha256_file(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def report_state_digests(contract_path: Path, events_path: Path, units_dir: Path) -> dict[str, str]:
    unit_files = read_unit_files(units_dir)
    unit_bytes = b"".join(path.name.encode() + b"\0" + raw for path, raw, _ in unit_files)
    return {
        "contract": sha256_file(contract_path),
        "events": sha256_file(events_path),
        "units": "sha256:" + hashlib.sha256(unit_bytes).hexdigest(),
    }


def prepare_report_artifacts(workspace: Path | str, contract: dict, run: dict,
                             units: list[dict], events: list[dict], digests: dict[str, str]) -> dict[str, Any]:
    try:
        module = report_module()
        payload = module.build_payload(workspace, contract, run, units, events, digests,
                                       build_scope_audit(run, contract, units))
        data_bytes = module.canonical_payload_bytes(payload)
        source_digest = module.canonical_payload_digest(payload)
        module.validate_report_data_bytes(data_bytes, payload, source_digest)
        data_digest = "sha256:" + hashlib.sha256(data_bytes).hexdigest()
        if source_digest != data_digest:
            raise ValueError
        html_bytes = module.render_report(payload, source_digest)
        module.validate_report_bytes(html_bytes, source_digest, payload)
        return {"payload": payload, "data_bytes": data_bytes, "html_bytes": html_bytes,
                "source_payload_sha256": source_digest, "data_file_sha256": data_digest,
                "html_file_sha256": "sha256:" + hashlib.sha256(html_bytes).hexdigest()}
    except Exception:
        raise HwahapError("HW_REPORT_GENERATION_FAILED", "could not prepare report artifacts") from None


def unit_paths_for_read(units_dir: Path) -> list[Path]:
    try:
        paths = sorted(units_dir.iterdir())
        for path in paths:
            if (not _single_regular_file(path) or path.suffix != ".json"
                    or not SLUG.fullmatch(path.stem)):
                raise HwahapError("HW_STATE_INVALID", "units contains an unexpected entry")
        return paths
    except HwahapError:
        raise
    except (OSError, UnicodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "cannot inspect units directory") from exc


def read_unit_files(units_dir: Path) -> list[tuple[Path, bytes, dict]]:
    try:
        files = []
        for path in unit_paths_for_read(units_dir):
            raw = path.read_bytes()
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise HwahapError("HW_STATE_INVALID", "unit JSON must contain an object")
            files.append((path, raw, value))
        return files
    except HwahapError:
        raise
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise HwahapError("HW_STATE_INVALID", "could not read state JSON") from exc


def parse_events(path: Path) -> list[dict]:
    events = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            event = json.loads(line)
            if isinstance(event, dict):
                events.append(event)
    return events
