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
        def test_final_snapshot_scope_closes_contract_unit_and_forbidden_paths(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            run = json.loads(run_path.read_text())
            scoped = copy.deepcopy(self.snapshot)
            scoped["changed_paths"] = ["entry", "src"]
            run["final_review"]["attempts"][0]["diff_snapshot"] = scoped
            run["final_review"]["attempts"][0]["diff_digest"] = scoped["diff_digest"]
            self.write_json(run_path, run)
            before = {path: path.read_bytes() for path in (run_path, events_path)}
            with patch.object(hwahap_state, "git_diff_snapshot", return_value=scoped):
                self.assert_invalid("locked contract scope")
                with self.assertRaises(hwahap_state.HwahapError):
                    hwahap_state.complete_run(self.complete_args())
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            self.assertFalse((run_dir / "report.html").exists())

            valid_run = json.loads(run_path.read_text())
            valid_run["final_review"]["attempts"][0]["diff_snapshot"] = copy.deepcopy(self.snapshot)
            self.write_json(run_path, valid_run)
            with patch.object(hwahap_state, "git_diff_snapshot", return_value=self.snapshot):
                with redirect_stdout(io.StringIO()):
                    hwahap_state.complete_run(self.complete_args())
            completed = json.loads(run_path.read_text())
            completed["final_review"]["attempts"][0]["diff_snapshot"] = scoped
            completed["final_review"]["attempts"][0]["diff_digest"] = scoped["diff_digest"]
            self.write_json(run_path, completed)
            with patch.object(hwahap_state, "git_diff_snapshot", return_value=scoped):
                self.assert_invalid("passed-unit scope")

            fallback = copy.deepcopy(completed)
            fallback["status"] = "final_review"
            fallback["final_review"] = {"status": "pass", "attempts": [
                {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported", "thread_id": "u",
                 "evidence": ["review"], "diff_snapshot": scoped, "diff_digest": scoped["diff_digest"]},
                {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass", "thread_id": "x",
                 "evidence": ["review"], "diff_snapshot": scoped, "diff_digest": scoped["diff_digest"]},
            ]}
            self.write_json(run_path, fallback)
            with patch.object(hwahap_state, "git_diff_snapshot", return_value=scoped):
                self.assert_invalid("forbidden_changes")

            errors: list[str] = []
            hwahap_state.validate_final_review_snapshot_scope(
                {"attempts": [{"diff_snapshot": {"changed_paths": ["src/lib/a"]}}]},
                {"allowed_paths": ["src"], "forbidden_changes": ["docs/*"]},
                [{"status": "passed", "allowed_paths": ["src/*"]}], errors)
            self.assertFalse(errors)
            errors = []
            hwahap_state.validate_final_review_snapshot_scope(
                {"attempts": [{"diff_snapshot": {"changed_paths": ["src2/a"]}}]},
                {"allowed_paths": ["src*"], "forbidden_changes": ["src2/*"]},
                [{"status": "passed", "allowed_paths": ["src"]}], errors)
            self.assertTrue(errors)
