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
        def test_record_test_receipt_write_then_raise_restores_state(self) -> None:
            run_dir = self.prepare_reviewing_test_unit()
            contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
            unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
            state_paths = (contract_path, run_path, unit_path, events_path)
            before = tuple(path.read_bytes() for path in state_paths)
            original_write_text = Path.write_text

            def write_then_raise(path: Path, *args: object, **kwargs: object) -> int:
                result = original_write_text(path, *args, **kwargs)
                if path == run_path:
                    raise OSError("secret receipt write")
                return result

            with patch.object(Path, "write_text", new=write_then_raise):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_test_receipt(self.record_receipt_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("secret receipt write", str(raised.exception))
            self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

        def test_passed_unit_requires_latest_pass_for_every_command(self) -> None:
            run_dir = self.prepare_test_unit()
            contract = json.loads((run_dir / "contract.json").read_text())
            command_two = "python3 -c \"print(2)\""
            contract["test_commands"].append(command_two)
            contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
            self.write_json(run_dir / "contract.json", contract)
            unit_path = run_dir / "units" / "unit-1.json"
            unit = self.passed_unit()
            unit["status"] = "reviewing"
            unit["acceptance_commands"] = [contract["test_commands"][0], command_two]
            unit["test_receipts"] = unit["test_receipts"][:0]
            self.write_json(unit_path, unit)
            self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing")])
            unit["status"] = "passed"
            unit["test_receipts"] = self.passed_unit()["test_receipts"]
            unit["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(contract["test_commands"][0].encode()).hexdigest()
            self.write_json(unit_path, unit)
            self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed")])
            self.assert_invalid("passing latest receipt")

        def test_passed_unit_receipts_bind_to_final_review(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = "reviewing"
            self.write_json(run_path, run)
            unit_path = run_dir / "units" / "unit-1.json"
            base = self.passed_unit()
            self.write_json(unit_path, base)
            self.write_events(run_dir, self.phase_events("passed"))
            self.validate()
            for field, value, message in (("observer_thread_id", "other-verifier", "observer does not match"),
                                          ("diff_digest", "sha256:" + "b" * 64, "diff does not match")):
                with self.subTest(field=field):
                    current = copy.deepcopy(base)
                    current["test_receipts"][0][field] = value
                    self.write_json(unit_path, current)
                    self.assert_invalid(message)
            latest_fail = copy.deepcopy(base["test_receipts"][0])
            latest_fail.update({"test_id": "test-1-2", "execution_receipt_sha256": "sha256:" + "1" * 64,
                                "exit_code": 2, "status": "fail"})
            current = copy.deepcopy(base)
            current["test_receipts"].append(latest_fail)
            self.write_json(unit_path, current)
            self.assert_invalid("passing latest receipt")
