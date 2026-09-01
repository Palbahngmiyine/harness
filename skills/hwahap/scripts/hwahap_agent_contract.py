"""Static contract for the six Hwahap agent profiles."""

import argparse
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[1] / "assets" / "agents"
REQUIRED_FIELDS = ("name", "description", "developer_instructions")
PROFILE_CONTRACT = {
    "hwahap-luna-implementer.toml": (
        "hwahap-luna-implementer", "gpt-5.6-luna", "high", "workspace-write", None, None),
    "hwahap-luna-verifier.toml": (
        "hwahap-luna-verifier", "gpt-5.6-luna", "xhigh", "read-only", None, None),
    "hwahap-sol-final-reviewer.toml": (
        "hwahap-sol-final-reviewer", "gpt-5.6-sol", None, "read-only", None, None),
    "hwahap-sol-planner.toml": (
        "hwahap-sol-planner", "gpt-5.6-sol", "xhigh", "read-only", None, None),
    "hwahap-sol-orchestrator.toml": (
        "hwahap-sol-orchestrator", "gpt-5.6-sol", "xhigh", "workspace-write", "fast", True),
    "hwahap-terra-scope-reviewer.toml": (
        "hwahap-terra-scope-reviewer", "gpt-5.6-terra", "xhigh",
        "read-only", None, None),
}
REQUIRED_PROFILE_NAMES = frozenset(PROFILE_CONTRACT)
PROFILE_SHA256 = {
    "hwahap-luna-implementer.toml": "f1781d1f33f923ce4f75b485444e3bd3c8779fdd1304c11b515777eb850586ae",
    "hwahap-luna-verifier.toml": "3f78b091ceccd232bd2206587a74259a139ea962d1736189d3ffd1d8b2a45df5",
    "hwahap-sol-final-reviewer.toml": "45b7f0d6961ccec665acc0c738f9506b6e2958b58ff5faff6248e91c6eb79f15",
    "hwahap-sol-orchestrator.toml": "9b17f5d9f78e9a1ecdbad88eb96f9c3232727f11e4ae4b98ae9c80408281077b",
    "hwahap-sol-planner.toml": "1e3f0ff57ccc650b5ae363bd0f65f43d12c6ce19aeaabd95abafcb4d60dbed62",
    "hwahap-terra-scope-reviewer.toml": "4dfd7e5d360eed061097821e3b651236e737966c9b6011ea8e23572cd0eeeff1",
}
PUBLIC_ERROR_MESSAGES = {
    "HW_AGENT_ARGUMENT_INVALID": "invalid installer arguments",
    "HW_AGENT_SOURCE_INVALID": "Hwahap source profiles are invalid",
    "HW_AGENT_PATH_INVALID": "installer path is invalid",
    "HW_AGENT_CONFLICT": "profile installation conflict",
    "HW_AGENT_CONFIG_INVALID": "installed agent configuration is invalid",
    "HW_AGENT_INSTALL_FAILED": "profile installation failed",
}


class InstallError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise InstallError("HW_AGENT_ARGUMENT_INVALID", "invalid installer arguments")


def is_hwahap_profile_name(name: str) -> bool:
    folded = name.casefold()
    return folded.startswith("hwahap-") and folded.endswith(".toml")
