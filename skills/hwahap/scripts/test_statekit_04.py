try:
    from .test_statekit_base import *
except ImportError:
    from test_statekit_base import *

class StateFixtureMixin04:
        def write_report_receipt(self, run_dir: Path) -> None:
            contract = json.loads((run_dir / "contract.json").read_text())
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
            run.setdefault("metrics", {})["test_runs"] = sum(
                len(unit.get("test_receipts", [])) for unit in units if isinstance(unit.get("test_receipts"), list)
            )
            events = hwahap_state.parse_events(run_dir / "events.jsonl")
            completed_events = [event.get("timestamp") for event in events
                                if event.get("entity") == "run" and event.get("from") == "final_review" and event.get("to") == "completed"]
            generated_at = completed_events[-1] if completed_events else run["completed_at"]
            digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
            payload = hwahap_report.build_payload(self.workspace, contract, run, units, events, digests,
                                                  hwahap_state.build_scope_audit(run, contract, units))
            source_digest = hwahap_report.canonical_payload_digest(payload)
            data = hwahap_report.canonical_payload_bytes(payload)
            html = hwahap_report.render_report(payload, source_digest)
            run["report"] = {"schema_version": 3, "status": "completed",
                              "generator": {"name": "hwahap-report", "version": 3, "design_system": "material-design-3"},
                              "source_payload_sha256": source_digest,
                              "data": {"path": "report-data.json", "file_sha256": "sha256:" + hashlib.sha256(data).hexdigest()},
                              "html": {"path": "report.html", "file_sha256": "sha256:" + hashlib.sha256(html).hexdigest()},
                              "generated_at": generated_at, "redaction_policy": "hwahap-report-v3"}
            (run_dir / "report-data.json").write_bytes(data)
            (run_dir / "report.html").write_bytes(html)
            self.write_json(run_path, run)

        def prepare_final_review(self) -> Path:
            run_dir = self.init_run()
            contract = self.lock_contract(run_dir)
            unit = self.passed_unit()
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run.update({"status": "final_review", "goal_link": self.bound_goal_link(),
                        "metrics": {**run["metrics"], "unit_count": 1, "review_rounds": 1}})
            self.write_json(run_dir / "contract.json", contract)
            self.write_json(run_path, run)
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.write_events(run_dir, self.phase_events("passed") + [("run", "reviewing", "final_review")])
            run = json.loads(run_path.read_text())
            run["final_review"] = {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]}
            self.write_json(run_path, run)
            self.validate()
            return run_dir

        def complete_args(self, **overrides: object) -> Namespace:
            values = {"workspace": str(self.workspace), "run_id": "test-goal", "actor": "sol-1",
                      "reason": "final report", "input_digest": self.snapshot["diff_digest"],
                      "evidence_ref": ["report-test"]}
            values.update(overrides)
            return Namespace(**values)

        def candidate_args(self, **overrides: object) -> Namespace:
            values = {"workspace": str(self.workspace), "run_id": "test-goal",
                      "summary": "reduce repeated setup", "expected_effect": "fewer manual steps",
                      "next_action": "review in a new Goal", "evidence_ref": ["final-review"]}
            values.update(overrides)
            return Namespace(**values)
