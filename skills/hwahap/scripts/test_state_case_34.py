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
        def test_execution_receipts_are_unique_across_units_and_record_rejects_duplicate(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            first = self.passed_unit()
            first["status"], first["review_history"] = "planned", []
            second = copy.deepcopy(first)
            second["unit_id"] = "unit-2"
            self.write_json(run_dir / "units" / "unit-1.json", first)
            self.write_json(run_dir / "units" / "unit-2.json", second)
            self.write_events(run_dir, [("run", "initialized", "contract_locked")])
            self.assert_invalid("duplicate execution receipt across units")

            run = json.loads((run_dir / "run.json").read_text())
            run["status"] = "reviewing"
            run["metrics"]["test_runs"] = 1
            first["status"], first["test_receipts"] = "reviewing", []
            second["status"] = "planned"
            self.write_json(run_dir / "run.json", run)
            self.write_json(run_dir / "units" / "unit-1.json", first)
            self.write_json(run_dir / "units" / "unit-2.json", second)
            self.write_events(run_dir, self.phase_events())
            self.validate()
            before = (run_dir / "units" / "unit-1.json").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_test_receipt(self.record_receipt_args(execution_receipt_sha256="sha256:" + "b" * 64))
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual((run_dir / "units" / "unit-1.json").read_bytes(), before)

        def test_test_receipt_tampering_is_rejected(self) -> None:
            run_dir = self.prepare_test_unit()
            run_path = run_dir / "run.json"
            unit_path = run_dir / "units" / "unit-1.json"
            valid = json.loads(unit_path.read_text())
            command = valid["acceptance_commands"][0]
            valid.update(self.passed_unit())
            valid["acceptance_commands"] = [command]
            valid["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            self.write_json(unit_path, valid)
            self.write_events(run_dir, self.phase_events("passed"))
            self.validate()
            valid = json.loads(unit_path.read_text())
            for field, value in (("test_id", "test-1-2"), ("command_sha256", "sha256:" + "a" * 64),
                                 ("output_sha256", "not-a-digest"), ("status", "fail"), ("exit_code", 2)):
                with self.subTest(field=field):
                    unit = copy.deepcopy(valid)
                    unit["test_receipts"][0][field] = value
                    self.write_json(unit_path, unit)
                    self.assert_invalid("test receipt")

        def test_failure_transition_requires_and_records_evidence(self) -> None:
            run_dir = self.init_run()
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.transition(self.transition_args("run", "blocked"))
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(
                    "run", "blocked", failure_code="HW_IMPLEMENTATION_BLOCKED",
                    failure_reason="dependency missing", failure_evidence=["command output"],
                    failure_recovery="restore dependency",
                ))
            run = json.loads((run_dir / "run.json").read_text())
            self.assertEqual(run["failure"]["code"], "HW_IMPLEMENTATION_BLOCKED")
            self.validate()
