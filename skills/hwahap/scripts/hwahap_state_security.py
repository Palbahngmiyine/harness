"""Verified Hwahap state responsibility module."""
from __future__ import annotations
from hwahap_state_runtime import *
register(globals())
def _credential_match_is_redacted(match: re.Match[str]) -> bool:
    _ensure_dependencies()
    return _dependency_modules[1].is_redacted(match)


def _normalize_credential_text(value: str) -> str:
    _ensure_dependencies()
    return _dependency_modules[1].normalized_text(value)


def credential_bearing_text(value: object) -> bool:
    """Return whether a state string contains a credential, without exposing it."""
    _ensure_dependencies()
    if not isinstance(value, str):
        return False
    return _dependency_modules[1].credential_bearing_text(value)


def credential_bearing_pair(key: object, value: object) -> bool:
    """Return whether a string dictionary key/value pair forms a credential."""
    if not isinstance(key, str):
        return False
    # A structured object can split the assignment across its key and value,
    # so run the same origin-aware detector against both common separators. A
    # container has no text to inspect, but a sensitive key must still not be
    # allowed to bypass the detector; use a safe placeholder in that case.
    pair_value = value if isinstance(value, str) else "value"
    return credential_bearing_text(f"{key}={pair_value}") or credential_bearing_text(f"{key}:{pair_value}")


def validate_state_strings(value: object, label: str, errors: list[str], *, skip_command_fields: bool = False) -> None:
    """Check every nested JSON string while keeping invalid values out of errors."""
    if isinstance(value, str):
        # Command fields retain their established, command-specific error. They
        # are still checked by safe_test_command below.
        is_contract_command = label.startswith("contract.test_commands[")
        is_unit_command = label.startswith("unit ") and label.count(".") == 1 and ".acceptance_commands[" in label
        if skip_command_fields and (is_contract_command or is_unit_command):
            return
        if credential_bearing_text(value):
            errors.append("state contains credential-bearing text")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            validate_state_strings(item, f"{label}[{index}]", errors, skip_command_fields=skip_command_fields)
    elif isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and credential_bearing_text(key):
                errors.append("state contains credential-bearing text")
            if credential_bearing_pair(key, item):
                errors.append("state contains credential-bearing text")
            validate_state_strings(item, f"{label}.{key}", errors, skip_command_fields=skip_command_fields)


def safe_test_command(value: object) -> bool:
    if (not required_text(value) or SHELL_CONTROL.search(value)
            or "$" in value or "\\" in value):
        return False
    if COMMAND_CREDENTIAL.search(value) or credential_bearing_text(value):
        return False
    try:
        argv = shlex.split(value, posix=True)
    except ValueError:
        return False
    if not argv or any(ASSIGNMENT_TOKEN.match(token) for token in argv):
        return False
    if any(Path(token).name in SHELL_WRAPPERS or Path(token).name == "env"
           or token == "-lc" for token in argv):
        return False
    return True
