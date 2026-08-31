"""Static regression checks for the normative Hwahap contract references."""

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"
AGENTS = ROOT / "assets" / "agents"


class OrchestratorContractDocsTests(unittest.TestCase):
    def test_activation_list_is_the_six_source_roles_and_planner_is_mandatory(self):
        text = (REFS / "execution-review.md").read_text(encoding="utf-8")
        section = text.split("## Roles and units", 1)[1].split("## ", 1)[0]
        listed = re.findall(r"^\d+\. `(hwahap-[a-z-]+)`$", section, re.MULTILINE)
        source = sorted(
            tomllib.loads(path.read_text(encoding="utf-8"))["name"]
            for path in AGENTS.glob("hwahap-*.toml")
        )
        self.assertEqual(len(listed), 6)
        self.assertEqual(len(set(listed)), 6)
        self.assertEqual(sorted(listed), source)
        self.assertIn("planner activation is mandatory", section)
        self.assertIn("cannot be skipped", section)
        self.assertIn("before any Luna writer starts", " ".join(text.split()))

    def test_input_branches_goal_order_and_terminal_reports_are_documented(self):
        text = (REFS / "state-contract.md").read_text(encoding="utf-8")
        compact = " ".join(text.split())
        self.assertIn("approved-spec mode", text)
        self.assertIn("`init --spec`", text)
        self.assertIn("direct-request mode", text)
        self.assertIn("request capsule", compact)
        self.assertIn("`init-request --request`", text)
        prelock = text.split("The exact pre-lock Goal sequence", 1)[1].split("```", 1)[0]
        tokens = re.findall(r"`(get_goal|create_goal|goal-sync|lock)`", prelock)
        self.assertEqual(tokens, ["get_goal", "create_goal", "get_goal", "goal-sync", "lock"])
        outcomes = ("completed", "blocked", "failed", "awaiting_user", "cancelled")
        report = text.split("Every terminal run outcome", 1)[1].split("\n\n", 1)[0]
        self.assertEqual(set(re.findall(r"`([a-z_]+)`", report)), set(outcomes))
        self.assertIn("report-data.json", report)
        self.assertIn("report.html", report)

    def test_reference_line_limits(self):
        for name in ("execution-review.md", "state-contract.md"):
            self.assertLessEqual(len((REFS / name).read_text(encoding="utf-8").splitlines()), 200)


if __name__ == "__main__":
    unittest.main()
