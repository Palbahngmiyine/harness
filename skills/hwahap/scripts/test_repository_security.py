"""Repository-local regressions for secret and generated-state exposure."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import unittest


REPOSITORY = Path(__file__).resolve().parents[3]
PRODUCTION_FILES = (
    *sorted((REPOSITORY / "skills/hwahap/assets/agents").glob("*.toml")),
    REPOSITORY / "skills/hwahap/scripts/hwahap",
    REPOSITORY / "skills/hwahap/scripts/hwahap_redaction.py",
    REPOSITORY / "skills/hwahap/scripts/hwahap_report.py",
    REPOSITORY / "skills/hwahap/scripts/hwahap_state.py",
    REPOSITORY / "skills/hwahap/scripts/install_project_agents.py",
)
PROVIDER_TOKEN = re.compile(
    r"(?x)(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{20,}|"
    r"sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{20,}|xox[baprs]-[A-Za-z0-9-]{20,}|"
    r"npm_[A-Za-z0-9]{20,}|(?:sk|rk)_live_[A-Za-z0-9]{16,}|"
    r"AIza[0-9A-Za-z_-]{35}|(?:AKIA|ASIA)[A-Z0-9]{16})")
AUTHENTICATION_URL = re.compile(r"(?i)https?://[^/\s:@]+:[^/\s@]+@")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
SENSITIVE_NAME = re.compile(
    r"(?i)(?:^|_)(?:token|password|secret|api_key|access_key|private_key)(?:$|_)")


def text_findings(text: str) -> list[str]:
    findings = []
    for label, pattern in (("provider token", PROVIDER_TOKEN),
                           ("authentication URL", AUTHENTICATION_URL),
                           ("private key", PRIVATE_KEY)):
        if pattern.search(text):
            findings.append(label)
    return findings


def python_literal_findings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=path.name)
    findings = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            value = node.value
            names = [target.id for target in targets if isinstance(target, ast.Name)]
            if (isinstance(value, ast.Constant) and isinstance(value.value, str)
                    and len(value.value) >= 8 and any(SENSITIVE_NAME.search(name) for name in names)):
                findings.append(f"hardcoded sensitive assignment at line {node.lineno}")
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if (isinstance(key, ast.Constant) and isinstance(key.value, str)
                        and SENSITIVE_NAME.search(key.value)
                        and isinstance(value, ast.Constant) and isinstance(value.value, str)
                        and len(value.value) >= 8):
                    findings.append(f"hardcoded sensitive mapping at line {node.lineno}")
    return findings


class RepositorySecurityTests(unittest.TestCase):
    def test_generated_state_and_implementation_prfaq_are_not_tracked(self) -> None:
        git = shutil.which("git", path=os.defpath)
        self.assertIsNotNone(git)
        result = subprocess.run([git, "ls-files", "-z"], cwd=REPOSITORY,
                                capture_output=True, check=True)
        tracked = result.stdout.decode("utf-8").split("\0")
        self.assertFalse(any(path == ".hwahap" or path.startswith(".hwahap/") for path in tracked))
        self.assertFalse(any(path == "docs/prfaq" or path.startswith("docs/prfaq/") for path in tracked))

    def test_production_files_have_no_embedded_authentication_material(self) -> None:
        for path in PRODUCTION_FILES:
            with self.subTest(path=path.relative_to(REPOSITORY)):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text_findings(text), [])
                if path.suffix == ".py":
                    self.assertEqual(python_literal_findings(path), [])

    def test_scanner_detects_constructed_regression_samples(self) -> None:
        samples = (
            "https://" + "user" + ":" + "pass" + "@example.invalid",
            "gh" + "p_" + "A1" * 18,
            "-----BEGIN " + "PRIVATE KEY-----",
        )
        for sample in samples:
            self.assertTrue(text_findings(sample))

    def test_workflows_pin_actions_and_use_read_only_permissions(self) -> None:
        workflows = sorted((REPOSITORY / ".github/workflows").glob("*.yml"))
        self.assertTrue(workflows)
        for path in workflows:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn("pull_request_target:", text)
                self.assertIn("permissions:\n  contents: read\n", text)
                action_refs = re.findall(r"(?m)^\s*uses:\s*[^@\s]+@([^\s#]+)", text)
                self.assertTrue(action_refs)
                self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        self.assertTrue((REPOSITORY / ".github/dependabot.yml").is_file())


if __name__ == "__main__":
    unittest.main()
