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
        def test_goal_sync_modes_and_append_only_current(self) -> None:
            run_dir = self.init_run()
            before = (run_dir / "run.json").read_bytes()
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.goal_sync(self.goal_args("no_active_goal"))
            self.assertEqual((run_dir / "run.json").read_bytes(), before)
            for mode, changes in (
                ("no_active_goal", {"receipt_sha256": "sha256:" + "a" * 64}),
                ("unavailable", {}),
                ("bound", {
                    "thread_id": "goal-thread", "objective_sha256": "sha256:" + "b" * 64,
                    "receipt_sha256": "sha256:" + "c" * 64,
                }),
            ):
                args = self.goal_args(mode, **changes)
                with redirect_stdout(io.StringIO()):
                    hwahap_state.goal_sync(args)
                self.validate()
                current = json.loads((run_dir / "run.json").read_text())["goal_link"]["current"]
                self.assertEqual(current["mode"], mode)
                self.assertEqual(current["completion_sync"], "pending" if mode == "bound" else "not_applicable")
            run = json.loads((run_dir / "run.json").read_text())
            run["goal_link"]["current"]["reason"] = "tampered"
            self.write_json(run_dir / "run.json", run)
            self.assert_invalid("current must equal")

        def test_goal_sync_token_receipt_and_agent_runs_receipt(self) -> None:
            run_dir = self.init_run()
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_sync(self.goal_args(
                    "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
                    receipt_sha256="sha256:" + "b" * 64, token_total=17))
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            self.assertEqual(run["metrics"]["token_usage"], {
                "availability": "available", "source": "codex.get_goal", "total": 17, "reason": None})
            self.validate()
            run["metrics"]["token_usage"]["total"] = 18
            self.write_json(run_path, run)
            self.assert_invalid("matching Goal receipt")
            run = json.loads(run_path.read_text())
            run["metrics"]["token_usage"]["total"] = 17
            run["goal_link"]["history"][0]["token_total"] = 18
            self.write_json(run_path, run)
            self.assert_invalid("matching Goal receipt")
            run = json.loads(run_path.read_text())
            run["metrics"]["token_usage"]["total"] = 17
            run["goal_link"]["history"][0]["token_total"] = 17
            run["metrics"]["agent_runs"] = 0
            self.write_json(run_path, run)
            self.assert_invalid("metrics.agent_runs")

        def test_token_receipt_validation_rejects_negative_and_source_mismatch(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            for total in (-1, True):
                run["metrics"]["token_usage"] = {"availability": "available", "source": "codex.get_goal", "total": total, "reason": None}
                self.write_json(run_path, run)
                self.assert_invalid("available token_usage")
            run["metrics"]["token_usage"] = {"availability": "available", "source": "wrong", "total": 1, "reason": None}
            self.write_json(run_path, run)
            self.assert_invalid("available token_usage")
            run["metrics"]["token_usage"] = {"availability": "unavailable", "source": "wrong", "total": None, "reason": "platform aggregate not exposed"}
            self.write_json(run_path, run)
            self.assert_invalid("null source")

        def test_goal_link_empty_history_requires_unobserved_current(self) -> None:
            run_dir = self.init_run()
            run = json.loads((run_dir / "run.json").read_text())
            run["goal_link"]["current"] = self.bound_goal_link()["current"]
            self.write_json(run_dir / "run.json", run)
            self.assert_invalid("must be unobserved when history is empty")
