try:
    from .test_installer_faultkit import InstallerFaultMixin, installer
except ImportError:
    from test_installer_faultkit import InstallerFaultMixin, installer
import tomllib
import unittest


class UpstreamInstallerContractTests(InstallerFaultMixin, unittest.TestCase):
    def test_source_profiles_have_exact_contract_metadata(self):
        expected = {
            "hwahap-luna-implementer.toml": ("hwahap-luna-implementer", "gpt-5.6-luna", "high", "workspace-write", None, None),
            "hwahap-luna-verifier.toml": ("hwahap-luna-verifier", "gpt-5.6-luna", "xhigh", "read-only", None, None),
            "hwahap-sol-final-reviewer.toml": ("hwahap-sol-final-reviewer", "gpt-5.6-sol", None, "read-only", None, None),
            "hwahap-sol-orchestrator.toml": ("hwahap-sol-orchestrator", "gpt-5.6-sol", "xhigh", "workspace-write", "fast", True),
            "hwahap-sol-planner.toml": ("hwahap-sol-planner", "gpt-5.6-sol", "xhigh", "read-only", None, None),
            "hwahap-terra-scope-reviewer.toml": ("hwahap-terra-scope-reviewer", "gpt-5.6-terra", "xhigh", "read-only", None, None),
        }
        profiles = installer.source_profiles()
        self.assertEqual({path.name for path, _ in profiles}, set(expected))
        for path, raw in profiles:
            value = tomllib.loads(raw.decode("utf-8"))
            actual = (value["name"], value.get("model"), value.get("model_reasoning_effort"),
                      value.get("sandbox_mode"), value.get("service_tier"),
                      value.get("features", {}).get("fast_mode"))
            self.assertEqual(actual, expected[path.name])

    def test_source_profiles_describe_snapshot_handoff_contract(self):
        text = {path.name: raw.decode("utf-8") for path, raw in installer.source_profiles()}
        for phrase in ("only the changed paths and bounded", "Do not claim an official digest or `diff_snapshot`", "after the base and target commits"):
            self.assertIn(phrase, text["hwahap-luna-implementer.toml"])
        for phrase in ("actual six-field", "--base-commit", "both reviewers have received"):
            self.assertIn(phrase, text["hwahap-sol-orchestrator.toml"])
        for name in ("hwahap-luna-verifier.toml", "hwahap-terra-scope-reviewer.toml"):
            for phrase in ("full six-field `diff_snapshot`", "actual", "Git", "diff", "`diff_digest`"):
                self.assertIn(phrase, text[name])
        for phrase in ("full six-field `diff_snapshot`", "same full valid final snapshot", "verified digest", "six concrete strings", "why the user owns the decision", "observable success condition"):
            self.assertIn(phrase, text["hwahap-sol-final-reviewer.toml"])
        for phrase in ("--decision-reason", "--evidence-relation", "generic risk warning"):
            self.assertIn(phrase, text["hwahap-sol-orchestrator.toml"])
        self.assertNotIn("evidence and a diff digest", text["hwahap-luna-implementer.toml"])
        self.assertNotIn("contract and diff digest", text["hwahap-luna-verifier.toml"])
        self.assertNotIn("same locked contract and diff digest", text["hwahap-terra-scope-reviewer.toml"])
        self.assertNotIn("exact final `diff_digest`", text["hwahap-sol-final-reviewer.toml"])
        self.assertNotIn("exact final diff digest only", text["hwahap-sol-final-reviewer.toml"])
        self.assertNotIn("Give the final reviewer the exact final diff digest.", text["hwahap-sol-orchestrator.toml"])
        self.assertNotIn("latest Luna verifier thread/digest", text["hwahap-sol-orchestrator.toml"])
