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
        def test_final_review_lifecycle_requires_canonical_events(self) -> None:
            run_dir = self.prepare_final_review()
            run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
            original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
            events = hwahap_state.parse_events(events_path)
            entry = next(index for index, event in enumerate(events) if event.get("to") == "final_review")
            for name, changed in (
                ("omitted", events[:entry]),
                ("duplicate", events + [copy.deepcopy(events[entry])]),
                ("reordered", events[:entry] + [events[entry]] + events[entry + 1:]),
            ):
                with self.subTest(name=name):
                    if name == "reordered":
                        changed[entry - 1], changed[entry] = changed[entry], changed[entry - 1]
                    for sequence, event in enumerate(changed, 1):
                        event["sequence"] = sequence
                    events_path.write_text("".join(json.dumps(event) + "\n" for event in changed))
                    self.assert_invalid("final_review")
                    run_path.write_bytes(original_run)
                    events_path.write_bytes(original_events)
            run = json.loads(run_path.read_text())
            run["status"] = "completed"
            self.write_json(run_path, run)
            self.assert_invalid("completion exit")
            run_path.write_bytes(original_run)
            run = json.loads(run_path.read_text())
            run["failure"] = {"code": "HW_FINAL_REVIEW_FAILED", "reason": "bad", "evidence": ["e"], "recovery": "ask"}
            self.write_json(run_path, run)
            self.assert_invalid("failure requires")

        def test_final_review_fallback_failure_can_await_user(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            digest = self.snapshot["diff_digest"]
            attempt = lambda effort, status, thread: {
                "model": "gpt-5.6-sol", "effort": effort, "status": status, "thread_id": thread,
                "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest}
            run.update({"status": "awaiting_user", "failure": {
                "code": "HW_MODEL_UNAVAILABLE", "reason": "fallback unavailable", "evidence": ["review"], "recovery": "ask user"},
                "final_review": {"status": "fail", "attempts": [attempt("ultra", "unsupported", "u"), attempt("xhigh", "unavailable", "x")]}})
            self.write_json(run_path, run)
            self.write_events(run_dir, self.phase_events("passed") + [
                ("run", "reviewing", "final_review"), ("run", "final_review", "awaiting_user")])
            self.validate()

        def test_run_failure_is_only_allowed_in_failure_states(self) -> None:
            run_dir = self.init_run()
            run_path = run_dir / "run.json"
            base = json.loads(run_path.read_text())
            codes = ("HW_MODEL_UNAVAILABLE", "HW_USER_DECISION_REQUIRED", "HW_SCOPE_DRIFT", "HW_FINAL_REVIEW_FAILED")
            for status in ("initialized", "contract_locked", "implementing", "reviewing", "recovering",
                           "replanning", "final_review", "completed", "cancelled"):
                for code in codes:
                    with self.subTest(status=status, code=code):
                        run = copy.deepcopy(base)
                        run["status"] = status
                        run["failure"] = {"code": code, "reason": "forged", "evidence": ["test"], "recovery": "ask"}
                        self.write_json(run_path, run)
                        self.assert_invalid("non-failure run must not contain failure")
