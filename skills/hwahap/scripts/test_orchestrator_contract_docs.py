"""Static semantic regression checks for the normative Hwahap references."""

import re
import tomllib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REFS = ROOT / "references"
AGENTS = ROOT / "assets" / "agents"
ROLES = (
    "hwahap-sol-orchestrator", "hwahap-sol-planner", "hwahap-luna-implementer",
    "hwahap-luna-verifier", "hwahap-terra-scope-reviewer", "hwahap-sol-final-reviewer",
)


class OrchestratorContractDocsTests(unittest.TestCase):
    def _oracle(self, execution, state):
        section = execution.split("## Roles and units", 1)[1].split("## ", 1)[0]
        listed = tuple(re.findall(r"^\d+\. `(hwahap-[a-z-]+)`$", section, re.MULTILINE))
        self.assertEqual(listed, ROLES)
        source = tuple(sorted(tomllib.loads(path.read_text(encoding="utf-8"))["name"]
                             for path in AGENTS.glob("hwahap-*.toml")))
        self.assertEqual(source, tuple(sorted(ROLES)))
        planner = listed.index("hwahap-sol-planner")
        for luna in ("hwahap-luna-implementer", "hwahap-luna-verifier"):
            self.assertLess(planner, listed.index(luna))
        self.assertIn(
            "planner activation is mandatory and cannot be skipped, merged, or deferred past a Luna writer.",
            " ".join(execution.split()),
        )
        compact = " ".join(state.split())
        self.assertIn(
            "approved-spec mode uses an approved PR/FAQ and `init --spec`; direct-request mode first writes a credential-free request capsule, then uses `init-request --request`. Neither branch is interchangeable.",
            compact,
        )
        prelock = compact.split("The exact pre-lock Goal sequence", 1)[1].split("A compatible Goal", 1)[0]
        self.assertIn(
            "is `get_goal` -> conditional `create_goal` (only when no active Goal exists) -> `get_goal` -> `goal-sync` (`--mode bound`) -> `lock`.",
            prelock,
        )
        self.assertEqual(tuple(re.findall(r"`(get_goal|create_goal|goal-sync|lock)`", prelock)),
                         ("get_goal", "create_goal", "get_goal", "goal-sync", "lock"))
        self.assertIn(
            "Every terminal run outcome—`completed`, `blocked`, `failed`, `awaiting_user`, or `cancelled`—automatically publishes both `report-data.json` and `report.html`; artifact publication does not alter the terminal status.",
            compact,
        )

    def _mutate(self, text, source, replacement):
        self.assertEqual(text.count(source), 1)
        mutated = text.replace(source, replacement)
        self.assertNotEqual(mutated, text)
        return mutated

    def test_contract_oracle_rejects_each_semantic_mutant(self):
        execution = (REFS / "execution-review.md").read_text(encoding="utf-8")
        state = (REFS / "state-contract.md").read_text(encoding="utf-8")
        self._oracle(execution, state)
        role_source = ("2. `hwahap-sol-planner`\n3. `hwahap-luna-implementer`")
        mutants = (
            (self._mutate(execution, role_source,
                          "2. `hwahap-luna-implementer`\n3. `hwahap-sol-planner`"), state),
            (execution, self._mutate(state, "conditional\n`create_goal` (only when no active Goal exists)",
                                     "conditional\n`create_goal` (when an active Goal exists)")),
            (execution, self._mutate(state, "automatically publishes both",
                                     "does not automatically publish both")),
            (execution, self._mutate(state, "approved PR/FAQ and\n`init --spec`; direct-request mode first writes a credential-free request\ncapsule, then uses `init-request --request`",
                                     "approved PR/FAQ and\n`init-request --request`; direct-request mode first writes a credential-free request\ncapsule, then uses `init --spec`")),
        )
        for mutated_execution, mutated_state in mutants:
            with self.assertRaises(AssertionError):
                self._oracle(mutated_execution, mutated_state)

    def test_reference_line_limits(self):
        for name in ("execution-review.md", "state-contract.md"):
            self.assertLessEqual(len((REFS / name).read_text(encoding="utf-8").splitlines()), 200)


if __name__ == "__main__":
    unittest.main()
