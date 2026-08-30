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
        def test_sol_ultra_probe_and_fallback_bind_one_diff_digest(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            digest = self.snapshot["diff_digest"]
            run["final_review"]["attempts"] = [
                {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported",
                 "thread_id": "ultra-probe", "evidence": ["probe"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest},
                {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass",
                 "thread_id": "xhigh-fallback", "evidence": ["fallback"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest},
            ]
            self.write_json(run_path, run)
            self.validate()
            run["final_review"] = {"status": "pending", "attempts": [
                {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported",
                 "thread_id": "ultra-pending", "evidence": ["probe"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest},
            ]}
            self.write_json(run_path, run)
            self.validate()
            before = (run_path.read_bytes(), (run_dir / "events.jsonl").read_bytes())
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.transition(self.transition_args(
                    "run", "awaiting_user", failure_code="HW_MODEL_UNAVAILABLE",
                    failure_reason="review unavailable", failure_evidence=["probe"],
                    failure_recovery="use xhigh fallback"))
            self.assertEqual((run_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()), before)
            run["final_review"]["status"] = "pass"
            run["final_review"]["attempts"].append(
                {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass",
                 "thread_id": "xhigh-fallback", "evidence": ["fallback"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest})
            self.write_json(run_path, run)
            self.validate()
            run["final_review"]["attempts"][1]["diff_digest"] = "sha256:" + "b" * 64
            self.write_json(run_path, run)
            self.assert_invalid("share diff digest")

        def test_final_review_requires_verified_git_snapshot(self) -> None:
            run_dir = self.prepare_final_review()
            run_path = run_dir / "run.json"
            original = json.loads(run_path.read_text())
            for field, value in (("diff_digest", "sha256:" + "f" * 64), ("changed_paths", ["other"]),
                                 ("base_tree", "0" * 40), ("target_tree", "1" * 40)):
                with self.subTest(field=field):
                    run = copy.deepcopy(original)
                    run["final_review"]["attempts"][0]["diff_snapshot"][field] = value
                    self.write_json(run_path, run)
                    self.assert_invalid("final_review.attempts[1].diff_snapshot")
            other = self.workspace / "final-review-other"
            other.mkdir()
            def git(*args: str) -> str:
                return subprocess.run(["git", *args], cwd=other, check=True,
                                      stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()
            git("init", "-q")
            git("config", "user.email", "test@example.invalid")
            git("config", "user.name", "Hwahap Test")
            (other / "other").write_text("one\n", encoding="utf-8")
            git("add", "other")
            git("commit", "-qm", "one")
            base = git("rev-parse", "HEAD")
            (other / "other").write_text("two\n", encoding="utf-8")
            git("commit", "-qam", "two")
            target = git("rev-parse", "HEAD")
            foreign = hwahap_state.git_diff_snapshot(other, base, target)
            run = copy.deepcopy(original)
            run["final_review"]["attempts"][0]["diff_snapshot"] = foreign
            run["final_review"]["attempts"][0]["diff_digest"] = foreign["diff_digest"]
            self.write_json(run_path, run)
            self.assert_invalid("final_review.attempts[1].diff_snapshot")
            run = copy.deepcopy(original)
            run["final_review"]["attempts"] = [
                run["final_review"]["attempts"][0], copy.deepcopy(run["final_review"]["attempts"][0])]
            run["final_review"]["attempts"][0]["status"] = "unsupported"
            run["final_review"]["attempts"][0]["effort"] = "ultra"
            run["final_review"]["attempts"][1]["effort"] = "xhigh"
            run["final_review"]["attempts"][1]["diff_snapshot"]["target_tree"] = "0" * 40
            self.write_json(run_path, run)
            self.assert_invalid("share diff snapshot")
            run = copy.deepcopy(original)
            run["final_review"]["attempts"][0].pop("diff_snapshot")
            self.write_json(run_path, run)
            self.assert_invalid("diff_snapshot")
