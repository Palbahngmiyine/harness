try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin03:
        def passed_unit(self) -> dict:
            digest = self.snapshot["diff_digest"]
            return {
                "unit_id": "unit-1",
                "title": "observable test change",
                "status": "passed",
                "writer": "hwahap-luna-implementer",
                "allowed_paths": ["src"],
                "acceptance_commands": ["test"],
                "test_receipts": [{
                    "test_id": "test-1-1", "command_index": 1,
                    "command_sha256": "sha256:" + hashlib.sha256(b"test").hexdigest(),
                    "source": "codex.exec_command", "execution_receipt_sha256": "sha256:" + "b" * 64,
                    "observer_role": "verifier", "observer_thread_id": "luna-1",
                    "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest,
                    "started_at": "2026-08-27T00:00:00Z", "ended_at": "2026-08-27T00:00:01Z",
                    "exit_code": 0, "output_sha256": "sha256:" + hashlib.sha256(b"tests pass").hexdigest(),
                    "status": "pass",
                }],
                "improvement_history": [],
                "review_history": [{
                    "round": 1, "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest,
                    "changed_paths": ["src"], "outcome": "pass",
                    "verifier": {"model": "gpt-5.6-luna", "effort": "xhigh", "status": "pass", "thread_id": "luna-1", "diff_digest": digest, "evidence": ["tests pass"]},
                    "scope_reviewer": {"model": "gpt-5.6-terra", "effort": "xhigh", "status": "pass", "thread_id": "terra-1", "diff_digest": digest, "evidence": ["scope matches"]},
                }],
            }

        def commit_source(self, text: str, message: str) -> str:
            (self.workspace / "src").write_text(text + "\n", encoding="utf-8")
            subprocess.run(["git", "add", "src"], cwd=self.workspace, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "commit", "-qm", message], cwd=self.workspace, check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return subprocess.run(["git", "rev-parse", "HEAD"], cwd=self.workspace, check=True,
                                  stdout=subprocess.PIPE, text=True).stdout.strip()

        def prepare_two_unit_final_review(self, *, gap: bool = False) -> Path:
            run_dir = self.prepare_final_review()
            first_target = self.target_commit
            if gap:
                second_base = self.commit_source("gap-base", "gap base")
            else:
                second_base = first_target
            second_target = self.commit_source("unit-two", "unit two")
            second = copy.deepcopy(json.loads((run_dir / "units" / "unit-1.json").read_text()))
            second_snapshot = hwahap_state.git_diff_snapshot(self.workspace, second_base, second_target)
            # Deliberately sort this filename before unit-1; the event log remains authoritative.
            second.update({"unit_id": "unit-0", "title": "second observable change"})
            second["test_receipts"][0].update({"execution_receipt_sha256": "sha256:" + "c" * 64,
                                                "observer_thread_id": "luna-2",
                                                "diff_snapshot": copy.deepcopy(second_snapshot),
                                                "diff_digest": second_snapshot["diff_digest"]})
            review = second["review_history"][-1]
            review.update({"diff_snapshot": copy.deepcopy(second_snapshot), "diff_digest": second_snapshot["diff_digest"]})
            review["verifier"].update({"thread_id": "luna-2", "diff_digest": second_snapshot["diff_digest"]})
            review["scope_reviewer"].update({"thread_id": "terra-2", "diff_digest": second_snapshot["diff_digest"]})
            self.write_json(run_dir / "units" / "unit-0.json", second)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["metrics"].update({"unit_count": 2, "review_rounds": 2})
            final_snapshot = hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, second_target)
            run["final_review"]["attempts"][0].update({"diff_snapshot": final_snapshot,
                                                         "diff_digest": final_snapshot["diff_digest"]})
            self.write_json(run_path, run)
            transitions = [
                ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
                ("run", "reviewing", "implementing"), ("unit-0", "planned", "implementing"),
                ("run", "implementing", "reviewing"), ("unit-0", "implementing", "reviewing"),
                ("unit-0", "reviewing", "passed"), ("run", "reviewing", "final_review"),
            ]
            self.write_events(run_dir, transitions)
            return run_dir
