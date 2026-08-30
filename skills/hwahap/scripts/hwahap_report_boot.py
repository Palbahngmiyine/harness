"""Install the lazy verified report graph into its facade."""

import importlib
import json
import re
import sys

_api = None
_root = None
_error = None
_finder_type = None
_reader = None
_manifest_pin = None


def _entries() -> dict:
    value = json.loads(_reader("hwahap_report_manifest.json", _manifest_pin))
    if set(value) != {"schema_version", "modules"} or value["schema_version"] != 1:
        raise ValueError
    entries = {}
    for item in value["modules"]:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError
        name, filename, digest = item
        valid = (isinstance(name, str) and name.startswith("hwahap_report_")
                 and isinstance(filename, str) and "/" not in filename
                 and filename.endswith(".py") and isinstance(digest, str)
                 and re.fullmatch(r"[0-9a-f]{64}", digest))
        if not valid or name in entries:
            raise ValueError
        entries[name] = (filename, digest)
    return entries


def boot():
    global _api
    if _api is not None:
        return _api
    entries, finder = {}, None
    try:
        entries = _entries()
        finder = _finder_type(entries)
        sys.meta_path.insert(0, finder)
        _api = importlib.import_module("hwahap_report_api")
        return _api
    except Exception:
        raise _error("report dependency unavailable") from None
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for name in entries:
            sys.modules.pop(name, None)


def _call(module: str, name: str, *args):
    try:
        return getattr(boot().modules[module], name)(*args)
    except ValueError as error:
        if type(error).__name__ == "HwahapReportError":
            raise _error(str(error)) from None
        raise


def _ensure_credentials() -> None:
    boot()
    _root["_credential_module"] = _api.credential


def _getattr(name: str):
    mapping = {"EVENT_FIELDS": ("types", "EVENT_FIELDS"),
               "CONTRACT_LISTS": ("types", "CONTRACT_LISTS"),
               "IMPROVEMENT_CANDIDATE_FIELDS": ("types", "IMPROVEMENT_CANDIDATE_FIELDS"),
               "STYLE_BLOCK": ("assets", "STYLE_BLOCK")}
    if name not in mapping:
        raise AttributeError(name)
    module, attribute = mapping[name]
    return getattr(boot().modules[module], attribute)


def install(root: dict, error, finder_type, reader, manifest_pin: str) -> None:
    global _root, _error, _finder_type, _reader, _manifest_pin
    _root, _error = root, error
    _finder_type, _reader, _manifest_pin = finder_type, reader, manifest_pin
    root["__getattr__"] = _getattr
    root["_ensure_credentials"] = _ensure_credentials
    root["credential_bearing_text"] = lambda value: (
        _ensure_credentials() or _call("security", "credential_bearing_text", value))
    root["_text"] = lambda *args: _call("security", "text", *args)
    root["build_payload"] = lambda *args: _call("payload", "build_payload", *args)
    root["canonical_payload_bytes"] = lambda value: _call("canonical", "canonical_payload_bytes", value)
    root["canonical_payload_digest"] = lambda value: _call("canonical", "canonical_payload_digest", value)
    root["validate_report_data_bytes"] = lambda *args: _call("canonical", "validate_report_data_bytes", *args)
    root["_payload_ledger_block"] = lambda value: _call("ledger", "payload_ledger_block", value)
    root["render_report"] = lambda *args: _call("render", "render_report", *args)
    root["validate_report_bytes"] = lambda *args: _call("validate", "validate_report_bytes", *args)
