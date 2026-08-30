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
        def test_final_review_rejects_post_unit_commit_without_re_review(self) -> None:
            run_dir = self.prepare_final_review()
            target = self.commit_source("post-unit", "post unit commit")
            final_snapshot = hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, target)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["final_review"]["attempts"][0].update({"diff_snapshot": final_snapshot,
                                                         "diff_digest": final_snapshot["diff_digest"]})
            self.write_json(run_path, run)
            tracked = {path: path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            self.assert_invalid("does not span the passed-unit chain")
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.complete_run(self.complete_args(input_digest=final_snapshot["diff_digest"]))
            self.assertEqual(tracked, {path: path.read_bytes() for path in tracked})

        def test_final_review_rejects_reversed_or_preimplementation_snapshot(self) -> None:
            run_dir = self.prepare_final_review()
            reversed_snapshot = hwahap_state.git_diff_snapshot(self.workspace, self.target_commit, self.base_commit)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["final_review"]["attempts"][0].update({"diff_snapshot": reversed_snapshot,
                                                         "diff_digest": reversed_snapshot["diff_digest"]})
            self.write_json(run_path, run)
            self.assert_invalid("does not span the passed-unit chain")

        def test_final_review_accepts_event_ordered_adjacent_two_unit_chain(self) -> None:
            self.prepare_two_unit_final_review()
            self.validate()

        def test_final_review_rejects_nonadjacent_two_unit_chain(self) -> None:
            self.prepare_two_unit_final_review(gap=True)
            self.assert_invalid("not an adjacent chain")

        def test_final_review_pending_attempts_reject_nonadjacent_chain_and_preserve_transition(self) -> None:
            run_dir = self.prepare_two_unit_final_review(gap=True)
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            run = json.loads(run_path.read_text())
            run.update({"status": "reviewing", "final_review": {"status": "pending", "attempts": []}})
            self.write_json(run_path, run)
            events = hwahap_state.parse_events(events_path)
            events_path.write_text("".join(json.dumps(event) + "\n" for event in events[:-1]), encoding="utf-8")
            self.validate()
            before = {path: path.read_bytes() for path in (run_path, events_path)}
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.transition(self.transition_args("run", "final_review"))
            self.assertEqual(before, {path: path.read_bytes() for path in before})
            run["status"] = "final_review"
            self.write_json(run_path, run)
            self.write_events(run_dir, [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
                ("run", "reviewing", "implementing"), ("unit-0", "planned", "implementing"),
                ("run", "implementing", "reviewing"), ("unit-0", "implementing", "reviewing"),
                ("unit-0", "reviewing", "passed"), ("run", "reviewing", "final_review"),
            ])
            self.assert_invalid("not an adjacent chain")

        def test_final_review_pending_attempts_accept_adjacent_chain(self) -> None:
            run_dir = self.prepare_two_unit_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            run = json.loads(run_path.read_text())
            run.update({"status": "reviewing", "final_review": {"status": "pending", "attempts": []}})
            self.write_json(run_path, run)
            events = hwahap_state.parse_events(events_path)
            events_path.write_text("".join(json.dumps(event) + "\n" for event in events[:-1]), encoding="utf-8")
            self.validate()
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "final_review"))
            self.validate()
