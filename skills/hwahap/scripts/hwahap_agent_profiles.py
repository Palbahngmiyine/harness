"""Read and validate the exact Hwahap agent profile set."""

import hashlib
import hmac
import tomllib
from pathlib import Path

from hwahap_agent_contract import (
    InstallError, PROFILE_CONTRACT, PROFILE_SHA256, REQUIRED_FIELDS, REQUIRED_PROFILE_NAMES,
    is_hwahap_profile_name,
)


def _metadata(value: dict, expected: tuple) -> bool:
    keys = ("name", "model", "model_reasoning_effort", "sandbox_mode", "service_tier")
    for key, expected_value in zip(keys, expected[:5]):
        if expected_value is None and key in value:
            return False
        if expected_value is not None and value.get(key) != expected_value:
            return False
    features = value.get("features", {})
    if expected[5] is None:
        return not isinstance(features, dict) or "fast_mode" not in features
    return isinstance(features, dict) and features.get("fast_mode") is True


def source_profiles(directory: Path) -> list[tuple[Path, bytes]]:
    if directory.is_symlink() or not directory.is_dir():
        raise InstallError("HW_AGENT_SOURCE_INVALID", "invalid profile directory")
    try:
        paths = list(directory.iterdir())
    except (OSError, UnicodeError):
        raise InstallError(
            "HW_AGENT_SOURCE_INVALID", "cannot inspect Hwahap profile directory") from None
    names = {path.name for path in paths if is_hwahap_profile_name(path.name)}
    if names != REQUIRED_PROFILE_NAMES:
        raise InstallError("HW_AGENT_SOURCE_INVALID", "source profile set is invalid")
    profiles = []
    for name in sorted(REQUIRED_PROFILE_NAMES):
        path = directory / name
        if path.is_symlink() or not path.is_file():
            raise InstallError("HW_AGENT_SOURCE_INVALID", "invalid Hwahap profile")
        try:
            raw = path.read_bytes()
            value = tomllib.loads(raw.decode())
        except (OSError, UnicodeError, tomllib.TOMLDecodeError):
            raise InstallError(
                "HW_AGENT_SOURCE_INVALID", "cannot parse Hwahap profile") from None
        fields_valid = all(isinstance(value.get(field), str) and value[field].strip()
                           for field in REQUIRED_FIELDS)
        if (not isinstance(value, dict) or not fields_valid
                or value["name"] != path.stem
                or not hmac.compare_digest(hashlib.sha256(raw).hexdigest(), PROFILE_SHA256[name])
                or not _metadata(value, PROFILE_CONTRACT[name])):
            raise InstallError(
                "HW_AGENT_SOURCE_INVALID", "Hwahap profile metadata is invalid")
        profiles.append((path, raw))
    return profiles


def lexical_path_has_symlink(path: Path) -> bool:
    current = Path(path.anchor) if path.is_absolute() else Path.cwd()
    for part in path.parts:
        if part in (path.anchor, ""):
            continue
        current /= part
        if current.is_symlink():
            return True
    return False
