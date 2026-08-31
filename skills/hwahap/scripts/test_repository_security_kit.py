"""Shared repository-security fixtures and scanners."""

from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest

REPOSITORY = Path(__file__).resolve().parents[3]
PRODUCTION_FILES = (*sorted((REPOSITORY / "skills/hwahap/assets/agents").glob("*.toml")),
                    REPOSITORY / "skills/hwahap/scripts/hwahap",
                    REPOSITORY / "skills/hwahap/scripts/hwahap_redaction.py",
                    REPOSITORY / "skills/hwahap/scripts/hwahap_report.py",
                    REPOSITORY / "skills/hwahap/scripts/hwahap_state.py",
                    REPOSITORY / "skills/hwahap/scripts/install_project_agents.py")
PROVIDER_TOKEN = re.compile(r"(?x)(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|npm_[A-Za-z0-9]{20,}|(?:sk|rk)_live_[A-Za-z0-9]{16,}|AIza[0-9A-Za-z_-]{35}|(?:AKIA|ASIA)[A-Z0-9]{16})")
AUTHENTICATION_URL = re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
SENSITIVE_NAME = re.compile(r"(?i)(?:^|_)(?:token|password|secret|api_key|access_key|private_key)(?:$|_)")


def text_findings(text: str) -> list[str]:
    return [label for label, pattern in (("provider token", PROVIDER_TOKEN), ("authentication URL", AUTHENTICATION_URL), ("private key", PRIVATE_KEY)) if pattern.search(text)]


def python_literal_findings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str) and len(node.value.value) >= 8 and any(SENSITIVE_NAME.search(name) for name in names):
                findings.append(f"hardcoded sensitive assignment at line {node.lineno}")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str) and SENSITIVE_NAME.search(key.value) and isinstance(value, ast.Constant) and isinstance(value.value, str) and len(value.value) >= 8:
                    findings.append(f"hardcoded sensitive mapping at line {node.lineno}")
    return findings


__all__ = [name for name in globals() if not name.startswith("__")]
