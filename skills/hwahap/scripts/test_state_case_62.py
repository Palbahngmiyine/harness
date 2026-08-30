try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
    from .test_statekit_02 import *
    from .test_statekit_03 import *
    from .test_statekit_04 import *
    from .test_statekit_05 import *
    from .test_statekit_06 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *
    from test_statekit_02 import *
    from test_statekit_03 import *
    from test_statekit_04 import *
    from test_statekit_05 import *
    from test_statekit_06 import *

class HwahapStateTests(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03, StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06, unittest.TestCase):
        def test_final_snapshot_scope_rejects_malformed_passed_unit_paths_stably(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            unit_path = run_dir / "units" / "unit-1.json"
            original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
            for malformed in (None, "src", {"path": "src"}, ["src", None], ["src", {"path": "src"}]):
                with self.subTest(malformed=malformed):
                    unit = self.passed_unit()
                    unit["allowed_paths"] = malformed
                    self.write_json(unit_path, unit)
                    self.assert_invalid("allowed_paths")
                    stderr = io.StringIO()
                    with redirect_stderr(stderr):
                        self.assertEqual(hwahap_state.main([
                            "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
                    self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.complete_run(self.complete_args())
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(run_path.read_bytes(), original_run)
                    self.assertEqual(events_path.read_bytes(), original_events)
                    self.write_json(unit_path, self.passed_unit())
            errors = []
            hwahap_state.validate_final_review_snapshot_scope(
                {"attempts": [{"diff_snapshot": {"changed_paths": ["src/a"]}}]},
                {"allowed_paths": ["src"], "forbidden_changes": []}, [], errors)
            self.assertTrue(errors)

        def test_scope_audit_is_derived_and_deduplicates_changed_paths(self) -> None:
            run_dir = self.prepare_final_review()
            contract = json.loads((run_dir / "contract.json").read_text())
            run = json.loads((run_dir / "run.json").read_text())
            unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
            snapshot = copy.deepcopy(self.snapshot)
            snapshot["changed_paths"] = ["src", "src", "src/lib"]
            run["final_review"]["attempts"][0]["diff_snapshot"] = snapshot
            audit = hwahap_state.build_scope_audit(run, contract, [unit])
            self.assertEqual([item["path"] for item in audit["paths"]], ["src", "src/lib"])
            self.assertEqual(audit["paths"][0]["matched_contract_rules"], ["src"])
            self.assertEqual(audit["paths"][0]["covering_passed_units"][0]["unit_id"], "unit-1")
            errors: list[str] = []
            hwahap_state.validate_final_review_snapshot_scope(run["final_review"], contract, [unit], errors)
            self.assertFalse(errors)
