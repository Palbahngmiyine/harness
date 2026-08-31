try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *


class HwahapStateTests(StateFixtureMixin01, unittest.TestCase):
    def _args(self, **changes: object) -> Namespace:
        values = {
            "workspace": str(self.workspace), "run_id": "test-goal",
            "summary": "review drift", "root_cause": "manual step",
            "impact": "late detection", "prevention": "automate check",
            "evidence_explanation": "receipt proves the check runs",
            "evidence": ["test receipt"],
        }
        values.update(changes)
        return Namespace(**values)

    def test_record_deviation_is_exact_v4_and_metric_aligned(self) -> None:
        run_dir = self.init_run()
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_deviation(self._args())
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(set(run["deviations"][0]), {
            "summary", "root_cause", "impact", "prevention",
            "evidence_explanation", "evidence"})
        self.assertEqual(run["metrics"]["scope_deviations"], 1)
        self.validate()

    def test_record_rejects_incomplete_sensitive_and_stale_records(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        original = run_path.read_bytes()
        for args in (self._args(evidence_explanation=""),
                     self._args(evidence=["client-secret=canary"])):
            with self.subTest(args=args):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_deviation(args)
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(run_path.read_bytes(), original)
        run = json.loads(original)
        run["deviations"] = [{"summary": "old", "root_cause": "old",
                               "impact": "old", "prevention": "old",
                               "evidence": ["old"]}]
        run["metrics"]["scope_deviations"] = 1
        self.write_json(run_path, run)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
