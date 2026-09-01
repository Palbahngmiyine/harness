"""Canonical JSON encoding and safety validation."""

import hashlib
import json

from hwahap_report_security import credential_bearing_text
from hwahap_report_handoff import validate_report_handoff
from hwahap_report_types import ABS_PATH, HwahapReportError

DEVIATION_FIELDS = frozenset(("summary", "root_cause", "impact", "prevention",
                              "evidence_explanation", "evidence"))
DEVIATION_TEXT_FIELDS = DEVIATION_FIELDS - {"evidence"}


def validate_deviations(value: object) -> None:
    if not isinstance(value, list):
        raise HwahapReportError("deviations are not an exact v4 list")
    for index, item in enumerate(value, 1):
        label = f"deviations[{index}]"
        if not isinstance(item, dict) or set(item) != DEVIATION_FIELDS:
            raise HwahapReportError(f"{label} is not an exact v4 deviation")
        if any(not isinstance(item[field], str) or not item[field].strip()
               for field in DEVIATION_TEXT_FIELDS):
            raise HwahapReportError(f"{label} has empty v4 causal text")
        evidence = item["evidence"]
        if (not isinstance(evidence, list) or not evidence
                or any(not isinstance(ref, str) or not ref.strip() for ref in evidence)):
            raise HwahapReportError(f"{label}.evidence is incomplete")


def canonical_payload_bytes(payload: dict) -> bytes:
    try:
        if not isinstance(payload, dict):
            raise ValueError
        return json.dumps(payload, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False).encode("utf-8")
    except Exception:
        raise HwahapReportError("report data is invalid") from None


def canonical_payload_digest(payload: dict) -> str:
    return "sha256:" + hashlib.sha256(canonical_payload_bytes(payload)).hexdigest()


def _unsafe_pair(key: str, value: object) -> bool:
    candidate = value if isinstance(value, str) else "value"
    return any(credential_bearing_text(f"{key}{operator}{candidate}")
               for operator in ("=", ":"))


def unsafe_text(value: object) -> bool:
    if isinstance(value, str):
        return credential_bearing_text(value) or ABS_PATH.search(value) is not None
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and (ABS_PATH.search(key) or _unsafe_pair(key, item)):
                return True
            if unsafe_text(item):
                return True
        return False
    if isinstance(value, list):
        return any(unsafe_text(item) for item in value)
    return False


def validate_report_data_bytes(data: bytes, expected_payload: dict,
                               expected_digest: str) -> bool:
    try:
        if not isinstance(data, bytes) or not isinstance(expected_payload, dict):
            raise ValueError
        actual = json.loads(data.decode("utf-8", errors="strict"))
        validate_report_handoff(expected_payload)
        deviations = expected_payload.get("deviations", {}).get("items", [])
        validate_deviations(deviations)
        canonical = canonical_payload_bytes(expected_payload)
        digest = "sha256:" + hashlib.sha256(canonical).hexdigest()
        if (actual != expected_payload or data != canonical or expected_digest != digest
                or unsafe_text(actual)):
            raise ValueError
        return True
    except Exception:
        raise HwahapReportError("report data is invalid") from None


def validate_payload(payload: dict, source_digest: str) -> None:
    try:
        if not isinstance(payload, dict) or canonical_payload_digest(payload) != source_digest:
            raise ValueError
        deviations = payload.get("deviations", {}).get("items", [])
        validate_deviations(deviations)
        validate_report_data_bytes(canonical_payload_bytes(payload), payload, source_digest)
    except Exception:
        raise HwahapReportError("report data is invalid") from None
