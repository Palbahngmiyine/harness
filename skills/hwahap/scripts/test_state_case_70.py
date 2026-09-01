"""Case 70: map each execution unit to one canonical align-goal U/S/A trace."""
try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_handoffkit import write_goal_artifact
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_handoffkit import write_goal_artifact


class HwahapStateCase70(StateFixtureMixin01, StateFixtureMixin02, unittest.TestCase):
    def aligned_run(self) -> Path:
        source = write_goal_artifact(self.workspace)
        with redirect_stdout(io.StringIO()):
            hwahap_state.init_run(Namespace(workspace=str(self.workspace),
                goal_id="aligned-goal", goal_spec=str(source)))
        run_dir = self.workspace / ".hwahap" / "runs" / "aligned-goal"
        contract_path = run_dir / "contract.json"
        contract = json.loads(contract_path.read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else
                               "test" if field == "test_commands" else "entry"]
        self.write_json(contract_path, contract)
        self.bind_goal("aligned-goal")
        with redirect_stdout(io.StringIO()):
            hwahap_state.lock_contract(Namespace(workspace=str(self.workspace),
                run_id="aligned-goal", actor="sol", reason="aligned handoff",
                evidence_ref=["goal.md"]))
        return run_dir

    def add(self, source="U1", unit="unit-1") -> None:
        with redirect_stdout(io.StringIO()):
            hwahap_state.add_unit(Namespace(workspace=str(self.workspace),
                run_id="aligned-goal", unit_id=unit, title="report",
                source_unit_id=source, allowed_path=["src"],
                acceptance_command=["test"]))

    def test_add_unit_derives_exact_source_trace(self) -> None:
        run_dir = self.aligned_run(); self.add()
        unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
        self.assertEqual(unit["source_trace"], {"unit_id": "U1",
            "spec_ids": ["S1"], "acceptance_ids": ["A1"]})
        self.validate("aligned-goal")

    def test_missing_unknown_and_duplicate_source_units_fail_closed(self) -> None:
        run_dir = self.aligned_run()
        for source in (None, "U9"):
            with self.subTest(source=source), self.assertRaises(hwahap_state.HwahapError):
                self.add(source)
        self.add()
        before = {path.name: path.read_bytes() for path in (run_dir / "units").glob("*.json")}
        with self.assertRaises(hwahap_state.HwahapError):
            self.add("U1", "unit-2")
        self.assertEqual(before, {path.name: path.read_bytes()
                                 for path in (run_dir / "units").glob("*.json")})

    def test_final_gate_requires_complete_source_coverage(self) -> None:
        run_dir = self.aligned_run()
        contract = json.loads((run_dir / "contract.json").read_text())
        errors = []
        hwahap_state.validate_handoff_units(contract, [], True, errors)
        self.assertEqual(errors, ["final review requires complete align-goal unit coverage"])


if __name__ == "__main__":
    unittest.main()
