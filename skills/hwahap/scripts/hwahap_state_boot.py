"""Install the lazy verified state graph into its facade."""

import importlib
import json
import re
import sys
import types

_api = None
_root = None
_error = None
_finder_type = None
_reader = None
_manifest_pin = None


def _entries() -> dict:
    value = json.loads(_reader("hwahap_state_manifest.json", _manifest_pin))
    if set(value) != {"schema_version", "modules"} or value["schema_version"] != 1:
        raise ValueError
    entries = {}
    for item in value["modules"]:
        if not isinstance(item, list) or len(item) != 3:
            raise ValueError
        name, filename, digest = item
        valid = (isinstance(name, str)
                 and name.startswith((
                     "hwahap_state_", "hwahap_credential_", "hwahap_agent_"))
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
        _api = importlib.import_module("hwahap_state_api")
        _api.set_value("HwahapError", _error)
        _root.update(_api.values())
        return _api
    except Exception:
        raise _error("HW_STATE_INVALID", "state dependency unavailable") from None
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for name in entries:
            sys.modules.pop(name, None)


def _getattr(name: str):
    boot()
    try:
        return _root[name]
    except KeyError:
        raise AttributeError(name) from None


class _Facade(types.ModuleType):
    def __setattr__(self, name: str, value: object) -> None:
        super().__setattr__(name, value)
        if _api is not None and _api.has_value(name):
            _api.set_value(name, value)


def install(root: dict, module, error, finder_type, reader, manifest_pin: str) -> None:
    global _root, _error, _finder_type, _reader, _manifest_pin
    _root, _error = root, error
    _finder_type, _reader, _manifest_pin = finder_type, reader, manifest_pin
    root["__getattr__"] = _getattr
    if module is not None:
        module.__class__ = _Facade


def run() -> int:
    try:
        return boot().get_value("main")()
    except _error as exc:
        print(f"{exc.code}: state is invalid", file=sys.stderr)
        return 1
