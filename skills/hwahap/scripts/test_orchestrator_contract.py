import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGENTS = ROOT / "assets" / "agents"


def compact(path: Path) -> str:
    return " ".join(path.read_text(encoding="utf-8").split())


class OrchestratorContractTests(unittest.TestCase):
    def test_exact_six_profiles_are_named_in_orchestrator(self):
        expected = {
            "hwahap-sol-planner", "hwahap-sol-orchestrator",
            "hwahap-luna-implementer", "hwahap-luna-verifier",
            "hwahap-terra-scope-reviewer", "hwahap-sol-final-reviewer",
        }
        files = {path.stem for path in AGENTS.glob("hwahap-*.toml")}
        self.assertEqual(files, expected)
        profile = tomllib.loads((AGENTS / "hwahap-sol-orchestrator.toml").read_text())
        self.assertEqual(profile["name"], "hwahap-sol-orchestrator")
        instructions = profile["developer_instructions"]
        self.assertNotIn("five", instructions.lower())
        for name in expected:
            self.assertIn(name, instructions)

    def test_direct_start_binds_goal_or_stops(self):
        text = compact(AGENTS / "hwahap-sol-orchestrator.toml")
        start = text.index("At every direct implementation start")
        flow = text[start:]
        first_get = flow.index("get_goal")
        create = flow.index("create_goal", first_get)
        second_get = flow.index("get_goal", create + 1)
        self.assertLess(first_get, create)
        self.assertLess(create, second_get)
        self.assertIn("compatible active Goal", flow)
        self.assertIn("conflicting active Goal requires `HW_USER_DECISION_REQUIRED`", flow)
        self.assertIn("failed Goal tooling stops with `HW_GOAL_REQUIRED`", flow)

    def test_direct_request_and_four_slot_lifecycle_are_separate_modes(self):
        profile = compact(AGENTS / "hwahap-sol-orchestrator.toml")
        skill = compact(ROOT / "SKILL.md")
        protocol = compact(ROOT / "references" / "protocol.md")
        self.assertIn("Direct-request mode uses `init-request` and does not require PRFAQ", profile)
        self.assertIn("A direct request does not need a PR/FAQ path; approved PR/FAQ remains a separate mode", skill)
        self.assertIn("Install the exact six project profiles", protocol)
        self.assertIn("With a four-slot limit including the invoking root", protocol)
        self.assertIn("Do not implement source changes directly", profile)

    def test_terminal_reports_precede_external_goal_completion(self):
        profile = compact(AGENTS / "hwahap-sol-orchestrator.toml")
        protocol = compact(ROOT / "references" / "protocol.md")
        self.assertIn("automatically generates and validates `report-data.json` and `report.html`", profile)
        self.assertIn("run `complete` locally and validate before external Goal completion sync", profile)
        self.assertIn("atomically generates the same canonical report artifacts", protocol)


if __name__ == "__main__":
    unittest.main()
