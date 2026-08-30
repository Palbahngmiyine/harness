"""Static contract for the six Hwahap agent profiles."""

import argparse
from pathlib import Path

PROFILE_DIR = Path(__file__).resolve().parents[1] / "assets" / "agents"
REQUIRED_FIELDS = ("name", "description", "developer_instructions")
PROFILE_CONTRACT = {
    "hwahap-luna-implementer.toml": (
        "hwahap-luna-implementer", "gpt-5.6-luna", "high", None, None, None),
    "hwahap-luna-verifier.toml": (
        "hwahap-luna-verifier", "gpt-5.6-luna", "xhigh", "read-only", None, None),
    "hwahap-sol-final-reviewer.toml": (
        "hwahap-sol-final-reviewer", "gpt-5.6-sol", None, "read-only", None, None),
    "hwahap-sol-planner.toml": (
        "hwahap-sol-planner", "gpt-5.6-sol", "xhigh", "read-only", None, None),
    "hwahap-sol-orchestrator.toml": (
        "hwahap-sol-orchestrator", "gpt-5.6-sol", "xhigh", None, "fast", True),
    "hwahap-terra-scope-reviewer.toml": (
        "hwahap-terra-scope-reviewer", "gpt-5.6-terra", "xhigh",
        "read-only", None, None),
}
REQUIRED_PROFILE_NAMES = frozenset(PROFILE_CONTRACT)
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
