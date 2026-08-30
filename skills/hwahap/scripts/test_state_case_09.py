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
        def test_final_review_pending_nonpassing_attempt_must_span_chain(self) -> None:
            run_dir = self.prepare_final_review()
            target = self.commit_source("post-unit", "post unit commit")
            invalid_snapshots = (
                hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, target),
                hwahap_state.git_diff_snapshot(self.workspace, target, self.base_commit),
            )
            run_path = run_dir / "run.json"
            for status, snapshot in zip(("unsupported", "unavailable"), invalid_snapshots):
                with self.subTest(status=status):
                    run = json.loads(run_path.read_text())
                    run["final_review"] = {"status": "pending", "attempts": [{
                        "model": "gpt-5.6-sol", "effort": "ultra", "status": status,
                        "thread_id": "probe", "evidence": ["probe"],
                        "diff_snapshot": snapshot, "diff_digest": snapshot["diff_digest"],
                    }]}
                    self.write_json(run_path, run)
                    self.assert_invalid("does not span the passed-unit chain")

        def test_final_review_awaiting_user_rejects_invalid_fallback_snapshots_without_writes(self) -> None:
            run_dir = self.prepare_final_review()
            target = self.commit_source("post-unit", "post unit commit")
            invalid_snapshots = (
                hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, target),
                hwahap_state.git_diff_snapshot(self.workspace, target, self.base_commit),
            )
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            for snapshot in invalid_snapshots:
                run = json.loads(run_path.read_text())
                run.update({"status": "awaiting_user", "failure": {
                    "code": "HW_MODEL_UNAVAILABLE", "reason": "fallback unavailable",
                    "evidence": ["review"], "recovery": "ask user"},
                    "final_review": {"status": "fail", "attempts": [
                        {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported",
                         "thread_id": "ultra", "evidence": ["probe"],
                         "diff_snapshot": snapshot, "diff_digest": snapshot["diff_digest"]},
                        {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "unavailable",
                         "thread_id": "fallback", "evidence": ["fallback"],
                         "diff_snapshot": snapshot, "diff_digest": snapshot["diff_digest"]},
                    ]}})
                self.write_json(run_path, run)
                self.write_events(run_dir, self.phase_events("passed") + [
                    ("run", "reviewing", "final_review"), ("run", "final_review", "awaiting_user")])
                before = {path: path.read_bytes() for path in (run_path, events_path)}
                self.assert_invalid("does not span the passed-unit chain")
                self.assertEqual(before, {path: path.read_bytes() for path in before})

        def test_final_review_pending_nonpassing_attempt_accepts_adjacent_snapshot(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            for status in ("unsupported", "unavailable"):
                with self.subTest(status=status):
                    run = json.loads(run_path.read_text())
                    run["final_review"] = {"status": "pending", "attempts": [{
                        "model": "gpt-5.6-sol", "effort": "ultra", "status": status,
                        "thread_id": "probe", "evidence": ["probe"],
                        "diff_snapshot": copy.deepcopy(self.snapshot),
                        "diff_digest": self.snapshot["diff_digest"],
                    }]}
                    self.write_json(run_path, run)
                    self.validate()
