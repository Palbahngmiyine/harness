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
        def test_complete_rejects_invalid_or_mismatched_review_input_without_writes(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
            for input_digest in ("not-a-digest", "sha256:" + "b" * 64):
                with self.subTest(input_digest=input_digest):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.complete_run(self.complete_args(input_digest=input_digest))
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(run_path.read_bytes(), original_run)
                    self.assertEqual(events_path.read_bytes(), original_events)
            run = json.loads(run_path.read_text())
            run["final_review"]["attempts"][0].pop("diff_digest")
            self.write_json(run_path, run)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.complete_run(self.complete_args())
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertEqual(events_path.read_bytes(), original_events)

        def test_goal_bound_receipt_cannot_downgrade_and_tampered_history_is_invalid(self) -> None:
            run_dir = self.init_run()
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_sync(self.goal_args(
                    "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
                    receipt_sha256="sha256:" + "b" * 64))
            run_path = run_dir / "run.json"
            original = run_path.read_bytes()
            for mode, receipt in (("no_active_goal", "sha256:" + "c" * 64), ("unavailable", None)):
                with self.subTest(mode=mode):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.goal_sync(self.goal_args(mode, receipt_sha256=receipt))
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(run_path.read_bytes(), original)
            run = json.loads(run_path.read_text())
            downgraded = copy.deepcopy(run["goal_link"]["current"])
            downgraded.update({"mode": "unavailable", "thread_id": None, "objective_sha256": None,
                               "receipt_sha256": None, "external_status": "unknown",
                               "completion_sync": "not_applicable"})
            run["goal_link"]["history"].append(downgraded)
            run["goal_link"]["current"] = downgraded
            self.write_json(run_path, run)
            self.assert_invalid("cannot downgrade")

        def test_terminal_run_rejects_all_unit_mutations(self) -> None:
            run_dir = self.init_run()
            self.lock_contract(run_dir)
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args(
                    "run", "blocked", failure_code="HW_IMPLEMENTATION_BLOCKED",
                    failure_reason="stop", failure_evidence=["test"], failure_recovery="retry"))
            before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
            commands = (
                lambda: hwahap_state.add_unit(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1", title="unit",
                    allowed_path=["src"], acceptance_command=["test"])),
                lambda: hwahap_state.transition(self.transition_args("unit-1", "implementing")),
                lambda: hwahap_state.record_test_receipt(self.record_receipt_args()),
                lambda: hwahap_state.record_improvement(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1")),
            )
            for command in commands:
                with self.subTest(command=command):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        command()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
