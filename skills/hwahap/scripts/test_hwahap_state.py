"""Unit tests for the Hwahap state contract."""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).with_name("hwahap_state.py")
MODULE_SPEC = importlib.util.spec_from_file_location("hwahap_state", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
hwahap_state = importlib.util.module_from_spec(MODULE_SPEC)
MODULE_SPEC.loader.exec_module(hwahap_state)
REPORT_SPEC = importlib.util.spec_from_file_location("hwahap_report", Path(__file__).with_name("hwahap_report.py"))
assert REPORT_SPEC and REPORT_SPEC.loader
hwahap_report = importlib.util.module_from_spec(REPORT_SPEC)
REPORT_SPEC.loader.exec_module(hwahap_report)
INSTALLER_PATH = Path(__file__).with_name("install_project_agents.py")
INSTALLER_SPEC = importlib.util.spec_from_file_location("install_project_agents", INSTALLER_PATH)
assert INSTALLER_SPEC and INSTALLER_SPEC.loader
installer = importlib.util.module_from_spec(INSTALLER_SPEC)
INSTALLER_SPEC.loader.exec_module(installer)


class HwahapStateTests(unittest.TestCase):
    def setUp(self) -> None:
        temp_root = "/private/tmp" if Path("/private/tmp").is_dir() else None
        self.tempdir = tempfile.TemporaryDirectory(dir=temp_root)
        self.workspace = Path(self.tempdir.name)
        self.spec = self.workspace / "spec.md"
        self.spec.write_text(
            "---\ntitle: Test goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
            encoding="utf-8",
        )
        (self.workspace / ".gitignore").write_text(".hwahap/\n", encoding="utf-8")
        self.install_agents(self.workspace)
        (self.workspace / "src").write_text("base\n", encoding="utf-8")
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=self.workspace, check=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True).stdout.strip()
        git("init", "-q"); git("config", "user.email", "test@example.invalid"); git("config", "user.name", "Hwahap Test")
        git("add", "-A"); git("commit", "-qm", "base")
        self.base_commit = git("rev-parse", "HEAD")
        (self.workspace / "src").write_text("target\n", encoding="utf-8")
        git("add", "src"); git("commit", "-qm", "target")
        self.target_commit = git("rev-parse", "HEAD")
        self.snapshot = hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def init_run(self, goal_id: str = "test-goal") -> Path:
        args = Namespace(workspace=str(self.workspace), goal_id=goal_id, spec=str(self.spec))
        with redirect_stdout(io.StringIO()):
            hwahap_state.init_run(args)
        return self.workspace / ".hwahap" / "runs" / goal_id

    def install_agents(self, workspace: Path) -> None:
        with redirect_stdout(io.StringIO()):
            installer.install(str(workspace))

    def fail_atomic_once(self, target: Path, message: str, *, write_first: bool = False):
        original = hwahap_state._atomic_replace_bytes
        fired = False
        def injected(path: Path, data: bytes) -> None:
            nonlocal fired
            if path == target and not fired:
                fired = True
                if write_first:
                    original(path, data)
                raise OSError(message)
            original(path, data)
        return patch.object(hwahap_state, "_atomic_replace_bytes", new=injected)

    def validate(self, goal_id: str = "test-goal") -> None:
        args = Namespace(workspace=str(self.workspace), run_id=goal_id)
        with redirect_stdout(io.StringIO()):
            hwahap_state.validate_run(args)

    def validate_at(self, workspace: Path, goal_id: str = "test-goal") -> None:
        args = Namespace(workspace=str(workspace), run_id=goal_id)
        with redirect_stdout(io.StringIO()):
            hwahap_state.validate_run(args)

    def write_json(self, path: Path, value: dict) -> None:
        hwahap_state._atomic_replace_bytes(
            path, (json.dumps(value, indent=2) + "\n").encode("utf-8"))

    def write_events(self, run_dir: Path, transitions: list[tuple[str, str, str]]) -> None:
        events = []
        for sequence, (entity, source, target) in enumerate(transitions, 1):
            events.append({
                "timestamp": "2026-08-27T00:00:00Z", "type": "state_transition",
                "sequence": sequence, "entity": entity, "from": source, "to": target,
                "actor": "sol-1", "role": "orchestrator", "reason": "test transition",
                "input_digest": "sha256:" + "a" * 64, "evidence_refs": ["test"], "review_round": 0,
            })
        hwahap_state._atomic_replace_bytes(
            run_dir / "events.jsonl",
            "".join(json.dumps(event) + "\n" for event in events).encode("utf-8"))

    def bind_last_event_digest(self, run_dir: Path) -> None:
        path = run_dir / "events.jsonl"
        events = hwahap_state.parse_events(path)
        events[-1]["input_digest"] = self.snapshot["diff_digest"]
        hwahap_state._atomic_replace_bytes(
            path, "".join(json.dumps(event) + "\n" for event in events).encode("utf-8"))

    @staticmethod
    def phase_events(unit_status: str = "reviewing", run_status: str | None = None) -> list[tuple[str, str, str]]:
        run_status = run_status or ("reviewing" if unit_status in {"reviewing", "passed"} else unit_status)
        events = [("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
                  ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
                  ("unit-1", "implementing", "reviewing")]
        if run_status == "recovering":
            events.append(("run", "reviewing", "recovering"))
        elif run_status == "replanning":
            events.append(("run", "reviewing", "replanning"))
        if unit_status != "reviewing":
            events.append(("unit-1", "reviewing", unit_status))
        return events

    def lock_contract(self, run_dir: Path) -> dict:
        path = run_dir / "contract.json"
        contract = json.loads(path.read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
        contract["locked"] = True
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(path, contract)
        return contract

    def transition_args(self, entity: str, target: str, **overrides: object) -> Namespace:
        values = {
            "workspace": str(self.workspace), "run_id": "test-goal", "entity": entity,
            "to": target, "actor": "sol-1", "role": "orchestrator",
            "reason": "test transition", "input_digest": "sha256:" + "a" * 64,
            "evidence_ref": ["test"], "review_round": 0, "failure_code": None,
            "failure_reason": None, "failure_evidence": None, "failure_recovery": None,
        }
        values.update(overrides)
        return Namespace(**values)

    def goal_args(self, mode: str, **overrides: object) -> Namespace:
        values = {
            "workspace": str(self.workspace), "run_id": "test-goal", "mode": mode,
            "thread_id": None, "objective_sha256": None, "receipt_sha256": None,
            "reason": "observed Goal state", "evidence_ref": ["goal receipt"],
        }
        values.update(overrides)
        return Namespace(**values)

    @staticmethod
    def bound_goal_link() -> dict:
        record = {
            "mode": "bound", "source": "codex.get_goal", "thread_id": "goal-thread",
            "external_status": "active", "objective_sha256": "sha256:" + "a" * 64,
            "receipt_sha256": "sha256:" + "b" * 64, "reason": "observed Goal state",
            "evidence": ["goal receipt"], "observed_at": "2026-08-27T00:00:00Z",
            "completion_sync": "pending", "sync_result": None, "token_total": None,
        }
        return {"current": copy.deepcopy(record), "history": [record]}

    def assert_invalid(self, message: str = "") -> None:
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        if message:
            self.assertIn(message, str(raised.exception))

    def assert_invalid_at(self, workspace: Path, message: str = "") -> None:
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate_at(workspace)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        if message:
            self.assertIn(message, str(raised.exception))

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
        run["report"] = {"schema_version": 4, "status": "completed",
                          "generator": {"name": "hwahap-report", "version": 5, "design_system": "material-design-3",
                                        "theme_source": "m3-foundations@2026-08-29"},
                          "source_payload_sha256": source_digest,
                          "data": {"path": "report-data.json", "file_sha256": "sha256:" + hashlib.sha256(data).hexdigest()},
                          "html": {"path": "report.html", "file_sha256": "sha256:" + hashlib.sha256(html).hexdigest()},
                          "generated_at": generated_at, "redaction_policy": "hwahap-report-v4"}
        hwahap_state._atomic_replace_bytes(run_dir / "report-data.json", data)
        hwahap_state._atomic_replace_bytes(run_dir / "report.html", html)
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

    def test_prepare_report_artifacts_is_canonical_and_repeatable(self) -> None:
        run_dir = self.prepare_final_review()
        contract = json.loads((run_dir / "contract.json").read_text())
        run = json.loads((run_dir / "run.json").read_text())
        units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
        events = hwahap_state.parse_events(run_dir / "events.jsonl")
        digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
        first = hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
        second = hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
        self.assertEqual(first, second)
        self.assertEqual(first["data_bytes"], hwahap_report.canonical_payload_bytes(first["payload"]))
        self.assertEqual(first["source_payload_sha256"], first["data_file_sha256"])
        self.assertEqual(first["html_file_sha256"], "sha256:" + hashlib.sha256(first["html_bytes"]).hexdigest())
        self.assertNotIn("report-data.json", {path.name for path in run_dir.iterdir()})

    def test_prepare_report_artifacts_normalizes_dependency_failures(self) -> None:
        run_dir = self.prepare_final_review()
        contract = json.loads((run_dir / "contract.json").read_text())
        run = json.loads((run_dir / "run.json").read_text())
        units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
        events = hwahap_state.parse_events(run_dir / "events.jsonl")
        digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
        payload = {"safe": "value"}
        encoded = b'{"safe":"value"}'
        digest = "sha256:" + hashlib.sha256(encoded).hexdigest()
        for broken in ("build_payload", "canonical_payload_bytes", "canonical_payload_digest",
                       "validate_report_data_bytes", "render_report", "validate_report_bytes"):
            with self.subTest(broken=broken):
                class BrokenReport:
                    def build_payload(self, *args): return (_ for _ in ()).throw(RuntimeError("/private/tmp/credential-canary")) if broken == "build_payload" else payload
                    def canonical_payload_bytes(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "canonical_payload_bytes" else encoded
                    def canonical_payload_digest(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "canonical_payload_digest" else digest
                    def validate_report_data_bytes(self, *args):
                        if broken == "validate_report_data_bytes": raise RuntimeError("credential-canary")
                        return True
                    def render_report(self, *args): return (_ for _ in ()).throw(RuntimeError("credential-canary")) if broken == "render_report" else b"html"
                    def validate_report_bytes(self, *args):
                        if broken == "validate_report_bytes": raise RuntimeError("credential-canary")
                        return True
                with patch.object(hwahap_state, "report_module", return_value=BrokenReport()):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
                self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                self.assertEqual(str(raised.exception), "could not prepare report artifacts")
        with patch.object(hwahap_state, "report_module", return_value=object()):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.prepare_report_artifacts(self.workspace, contract, run, units, events, digests)
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual(str(raised.exception), "could not prepare report artifacts")


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

    def prepare_test_unit(self, command: str = "python3 -m unittest") -> Path:
        run_dir = self.init_run()
        contract = self.lock_contract(run_dir)
        contract["test_commands"] = [command]
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(run_dir / "contract.json", contract)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "contract_locked"
        self.write_json(run_path, run)
        self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing")])
        unit = self.passed_unit()
        unit.update({"title": "test unit", "status": "implementing", "review_history": [], "test_receipts": []})
        unit["acceptance_commands"] = [command]
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        run["metrics"]["unit_count"] = 1
        self.write_json(run_path, run)
        return run_dir

    def prepare_reviewing_test_unit(self, command: str = "test") -> Path:
        run_dir = self.prepare_test_unit(command)
        run_path, unit_path = run_dir / "run.json", run_dir / "units" / "unit-1.json"
        run = json.loads(run_path.read_text())
        unit = json.loads(unit_path.read_text())
        run["status"], unit["status"] = "reviewing", "reviewing"
        self.write_json(run_path, run)
        self.write_json(unit_path, unit)
        self.write_events(run_dir, self.phase_events())
        self.validate()
        return run_dir

    def run_test_args(self, **overrides: object) -> Namespace:
        values = {"workspace": str(self.workspace), "run_id": "test-goal", "unit_id": "unit-1",
                  "command_index": 1, "timeout_seconds": 5}
        values.update(overrides)
        return Namespace(**values)

    def record_receipt_args(self, **overrides: object) -> Namespace:
        values = {
            "workspace": str(self.workspace), "run_id": "test-goal", "unit_id": "unit-1",
            "command_index": 1, "execution_receipt_sha256": "sha256:" + "d" * 64,
            "observer_thread_id": "verifier-thread", "diff_digest": self.snapshot["diff_digest"],
            "base_commit": self.base_commit, "target_commit": self.target_commit,
            "started_at": "2026-08-27T00:00:00Z", "ended_at": "2026-08-27T00:00:01Z",
            "output_sha256": "sha256:" + "f" * 64, "exit_code": 0, "timed_out": False,
        }
        values.update(overrides)
        return Namespace(**values)

    def goal_complete_args(self, result: str = "completed") -> Namespace:
        return Namespace(workspace=str(self.workspace), run_id="test-goal", sync_result=result,
                         receipt_sha256="sha256:" + "c" * 64, reason="Goal completion observed",
                         evidence_ref=["goal-update"], token_total=None if result == "failed" else 123)

    def test_complete_generates_receipt_and_completed_event(self) -> None:
        run_dir = self.prepare_final_review()
        events_path = run_dir / "events.jsonl"
        events_path.write_bytes(events_path.read_bytes().rstrip(b"\n"))
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run = json.loads((run_dir / "run.json").read_text())
        receipt = run["report"]
        self.assertEqual(run["status"], "completed")
        self.assertEqual(receipt["status"], "completed")
        self.assertTrue(receipt["source_payload_sha256"].startswith("sha256:"))
        self.assertTrue(receipt["data"]["file_sha256"].startswith("sha256:"))
        self.assertTrue(receipt["html"]["file_sha256"].startswith("sha256:"))
        self.assertTrue((run_dir / "report-data.json").read_bytes().startswith(b"{"))
        self.assertTrue((run_dir / "report.html").read_bytes().startswith(b"<!doctype html>"))
        self.assertEqual(run["metrics"]["unit_count"], 1)
        self.assertGreaterEqual(run["metrics"]["elapsed_seconds"], 0)
        self.assertEqual(run["metrics"]["test_runs"], 1)
        self.validate()
        self.assertEqual(hwahap_state.parse_events(run_dir / "events.jsonl")[-1]["to"], "completed")

    def test_report_v4_pending_has_no_physical_artifacts(self) -> None:
        run_dir = self.init_run()
        receipt = json.loads((run_dir / "run.json").read_text())["report"]
        self.assertEqual(receipt, {"schema_version": 4, "status": "pending",
                          "generator": {"name": "hwahap-report", "version": 5, "design_system": "material-design-3",
                          "theme_source": "m3-foundations@2026-08-29"},
            "source_payload_sha256": None, "data": {"path": "report-data.json", "file_sha256": None},
            "html": {"path": "report.html", "file_sha256": None}, "generated_at": None,
            "redaction_policy": "hwahap-report-v4"})
        self.assertFalse((run_dir / "report-data.json").exists())
        self.assertFalse((run_dir / "report.html").exists())

    def test_fast_status_stays_unknown_without_platform_receipt(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        baseline_run = run_path.read_bytes()
        for forged in ("enabled", "disabled"):
            with self.subTest(fast_status=forged):
                run = json.loads(baseline_run)
                run["fast_status"] = forged
                self.write_json(run_path, run)
                original = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
                for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        operation()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                for name, data in original.items():
                    self.assertEqual((run_dir / name).read_bytes(), data)
                self.assertFalse((run_dir / "report-data.json").exists())
                self.assertFalse((run_dir / "report.html").exists())
                run_path.write_bytes(baseline_run)
        self.assertEqual(json.loads((run_dir / "run.json").read_text())["fast_status"], "unknown")
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        self.assertEqual(json.loads((run_dir / "report-data.json").read_text())["provenance"]["fast_status"], "unknown")
        self.assertIn("unknown", (run_dir / "report.html").read_text())

    def test_v3_report_receipt_is_rejected_without_migration(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["report"] = {"schema_version": 3, "status": "pending",
                          "generator": {"name": "hwahap-report", "version": 3,
                                        "design_system": "material-design-3"},
                          "source_payload_sha256": None,
                          "data": {"path": "report-data.json", "file_sha256": None},
                          "html": {"path": "report.html", "file_sha256": None},
                          "generated_at": None, "redaction_policy": "hwahap-report-v3"}
        self.write_json(run_path, run)
        self.assert_invalid("report receipt")

    def test_report_v4_data_and_receipt_tampering_are_rejected(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        data_path, run_path = run_dir / "report-data.json", run_dir / "run.json"
        original = data_path.read_bytes()
        data_path.write_bytes(original + b"\n")
        self.assert_invalid("report data digest")
        data_path.write_bytes(original)
        run = json.loads(run_path.read_text())
        run["report"]["data"]["file_sha256"] = "sha256:" + "a" * 64
        self.write_json(run_path, run)
        self.assert_invalid("report data digest")

    def test_report_v4_pending_artifact_and_goal_sync_require_data(self) -> None:
        run_dir = self.init_run()
        (run_dir / "report-data.json").write_bytes(b"{}")
        self.assert_invalid("pending report must not have report artifacts")
        (run_dir / "report-data.json").unlink()
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        (run_dir / "report-data.json").unlink()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.goal_complete_sync(self.goal_complete_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_report_artifact_write_and_final_validate_failures_roll_back(self) -> None:
        for target in ("report-data.json", "report.html", "run.json", "events.jsonl", "validate"):
            with self.subTest(command="complete", target=target):
                run_dir = self.prepare_final_review()
                run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
                before = (run_path.read_bytes(), events_path.read_bytes())
                original_atomic = hwahap_state._atomic_replace_bytes
                def fail_bytes(path: Path, data: bytes) -> None:
                    if path.name == target:
                        raise OSError("report-artifact-canary")
                    return original_atomic(path, data)
                original_validate = hwahap_state.validate_run
                calls = 0
                def fail_validate(args: Namespace) -> None:
                    nonlocal calls
                    calls += 1
                    if calls > 1:
                        raise hwahap_state.HwahapError("HW_STATE_INVALID", "report-artifact-canary")
                    original_validate(args)
                try:
                    with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_bytes), patch.object(hwahap_state, "validate_run", new=fail_validate if target == "validate" else original_validate):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.complete_run(self.complete_args())
                finally:
                    hwahap_state.validate_run = original_validate
                if (run_dir / ".report-recovery.json").exists():
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                self.assertEqual(before, (run_path.read_bytes(), events_path.read_bytes()))
                self.assertFalse((run_dir / "report-data.json").exists())
                self.assertFalse((run_dir / "report.html").exists())

        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        for target in ("report-data.json", "report.html", "run.json", "validate"):
            with self.subTest(command="goal_sync", target=target):
                run_path, data_path, report_path = run_dir / "run.json", run_dir / "report-data.json", run_dir / "report.html"
                before = (run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes())
                original_atomic, original_validate = hwahap_state._atomic_replace_bytes, hwahap_state.validate_run
                def fail_bytes(path: Path, data: bytes) -> None:
                    if path.name == target:
                        raise OSError("goal-artifact-canary")
                    return original_atomic(path, data)
                calls = 0
                def fail_validate(args: Namespace) -> None:
                    nonlocal calls
                    calls += 1
                    if calls > 1:
                        raise hwahap_state.HwahapError("HW_STATE_INVALID", "goal-artifact-canary")
                    original_validate(args)
                try:
                    with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_bytes), patch.object(hwahap_state, "validate_run", new=fail_validate if target == "validate" else original_validate):
                        with self.assertRaises(hwahap_state.HwahapError) as raised:
                            hwahap_state.goal_complete_sync(self.goal_complete_args())
                finally:
                    hwahap_state.validate_run = original_validate
                if (run_dir / ".report-recovery.json").exists():
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
                self.assertEqual(before, (run_path.read_bytes(), data_path.read_bytes(), report_path.read_bytes()))

    def test_report_recovery_journal_retries_incomplete_restore_on_next_validate(self) -> None:
        run_dir = self.prepare_final_review()
        data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
        original_write, original_unlink = hwahap_state._atomic_replace_bytes, Path.unlink
        writes = {"restore_failed": False}

        def fault(path: Path, data: bytes, **kwargs: object) -> int:
            if path == report_path:
                raise OSError("journal-report-canary")
            return original_write(path, data)

        def fault_unlink(path: Path, **kwargs: object) -> None:
            if path == data_path and not writes["restore_failed"]:
                writes["restore_failed"] = True
                raise OSError("journal-restore-canary")
            return original_unlink(path, **kwargs)

        try:
            with patch.object(hwahap_state, "_atomic_replace_bytes", new=fault), patch.object(Path, "unlink", new=fault_unlink):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.complete_run(self.complete_args())
        finally:
            hwahap_state._atomic_replace_bytes, Path.unlink = original_write, original_unlink
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        journal = run_dir / ".report-recovery.json"
        self.assertTrue(journal.is_file())
        self.assertTrue(data_path.is_file())
        self.assertFalse(report_path.exists())
        self.validate()
        self.assertFalse(journal.exists())
        self.assertFalse(data_path.exists())
        self.assertFalse(report_path.exists())

    def test_malformed_report_recovery_journal_is_rejected(self) -> None:
        run_dir = self.init_run()
        (run_dir / ".report-recovery.json").write_text("{}", encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_unbound_recovery_journal_only_clears_exact_original_set(self) -> None:
        run_dir = self.prepare_final_review()
        files = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        originals = {"run.json": (True, files["run.json"]), "report-data.json": (False, b""),
                     "report.html": (False, b""), "events.jsonl": (True, files["events.jsonl"])}
        target = {name: (run_dir / name).read_bytes() if (run_dir / name).exists() else b"target"
                  for name in hwahap_state._REPORT_RECOVERY_FILES}
        journal, _ = hwahap_state._recovery_setup("complete", originals, target)
        journal_path = run_dir / ".report-recovery.json"
        journal_path.write_bytes(journal)
        self.validate()
        self.assertFalse(journal_path.exists())
        journal_path.write_bytes(journal)
        (run_dir / "report-data.json").write_bytes(b"unexpected")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual((run_dir / "report-data.json").read_bytes(), b"unexpected")

    def test_unbound_recovery_cleanup_failure_and_orphan_marker_are_invalid(self) -> None:
        run_dir = self.prepare_final_review()
        files = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        originals = {"run.json": (True, files["run.json"]), "report-data.json": (False, b""),
                     "report.html": (False, b""), "events.jsonl": (True, files["events.jsonl"])}
        target = {name: (run_dir / name).read_bytes() if (run_dir / name).exists() else b"target"
                  for name in hwahap_state._REPORT_RECOVERY_FILES}
        journal, _ = hwahap_state._recovery_setup("complete", originals, target)
        journal_path = run_dir / ".report-recovery.json"
        journal_path.write_bytes(journal)
        with patch.object(hwahap_state, "_clear_report_recovery_journal", return_value=False):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertTrue(journal_path.exists())
        journal_path.unlink()
        run = json.loads((run_dir / "run.json").read_text())
        run["report_transaction"] = {"transaction_id": "sha256:" + "a" * 64}
        self.write_json(run_dir / "run.json", run)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_complete_rejects_raw_curl_credential_before_writing_anything(self) -> None:
        run_dir = self.prepare_final_review()
        run_path, events_path, report_path = (run_dir / "run.json", run_dir / "events.jsonl", run_dir / "report.html")
        run = json.loads(run_path.read_text())
        raw = "curl " + chr(92) + "\n  --user audit:linecase URL"
        run["deviations"] = [{"summary": raw, "root_cause": "cause", "impact": "impact",
                               "prevention": "prevention", "evidence": ["evidence"]}]
        self.write_json(run_path, run)
        before = {path: path.read_bytes() for path in (run_path, events_path)}
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.complete_run(self.complete_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("audit:linecase", str(raised.exception))
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.assertFalse(report_path.exists())
        run["deviations"][0]["summary"] = "curlish --user documentation"
        self.write_json(run_path, run)
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        self.assertIn("curlish --user documentation", report_path.read_text(encoding="utf-8"))

    def test_improvement_candidate_appends_only_to_final_review_run(self) -> None:
        run_dir = self.prepare_final_review()
        run_path, unit_path, events_path = (run_dir / "run.json", run_dir / "units" / "unit-1.json", run_dir / "events.jsonl")
        before = {path: path.read_bytes() for path in (unit_path, events_path)}
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement_candidate(self.candidate_args())
        run = json.loads(run_path.read_text())
        self.assertEqual(run["improvement_candidates"], [{
            "status": "proposed", "summary": "reduce repeated setup",
            "evidence": ["final-review"], "expected_effect": "fewer manual steps",
            "next_action": "review in a new Goal",
        }])
        self.assertEqual({path: path.read_bytes() for path in before}, before)
        self.validate()

    def test_improvement_candidate_wrong_state_is_byte_identical(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        before = run_path.read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_improvement_candidate(self.candidate_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(run_path.read_bytes(), before)

    def test_improvement_candidate_requires_passing_final_review(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        for final in (
            {"status": "pending", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported",
                "thread_id": "ultra-pending", "evidence": ["probe"],
                "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"],
            }]},
            {"status": "fail", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail",
                "thread_id": "ultra-fail", "evidence": ["review"],
                "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"],
            }]},
        ):
            with self.subTest(final=final):
                run = json.loads(run_path.read_text())
                run["final_review"] = final
                self.write_json(run_path, run)
                before = run_path.read_bytes()
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_improvement_candidate(self.candidate_args())
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(run_path.read_bytes(), before)
                run["improvement_candidates"] = [{
                    "status": "proposed", "summary": "candidate", "evidence": ["review"],
                    "expected_effect": "effect", "next_action": "inspect",
                }]
                self.write_json(run_path, run)
                self.assert_invalid("improvement_candidates require")

    def test_improvement_candidate_credentials_are_rejected_without_echo_or_write(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        before = run_path.read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_improvement_candidate(
                self.candidate_args(summary="OPENAI_API_KEY:=candidate-secret"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("candidate-secret", str(raised.exception))
        self.assertEqual(run_path.read_bytes(), before)

    def test_improvement_candidate_rollback_failure_is_generic(self) -> None:
        run_dir = self.prepare_final_review()
        original_validate = hwahap_state.validate_run
        original_atomic = hwahap_state._atomic_replace_bytes
        validations = 0
        rollback = False
        def fail_after_write(args: Namespace) -> None:
            nonlocal validations, rollback
            validations += 1
            if validations > 1:
                rollback = True
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/Proxy-Authorization: Digest rollback-canary")
            original_validate(args)
        def fail_rollback(path: Path, data: bytes) -> None:
            if rollback:
                raise OSError("/private/tmp/path-canary")
            original_atomic(path, data)
        hwahap_state.validate_run = fail_after_write
        try:
            with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_rollback):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.record_improvement_candidate(self.candidate_args())
        finally:
            hwahap_state.validate_run = original_validate
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(str(raised.exception), "could not record improvement candidate")
        self.assertNotIn("canary", str(raised.exception))

    def test_improvement_candidate_schema_rejects_missing_extra_and_executable_fields(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement_candidate(self.candidate_args())
        run_path = run_dir / "run.json"
        original = json.loads(run_path.read_text())
        for name, mutate in (
            ("missing", lambda item: item.pop("summary")),
            ("extra", lambda item: item.update({"command": "run candidate"})),
            ("path", lambda item: item.update({"path": "src"})),
            ("unit", lambda item: item.update({"unit_id": "unit-1"})),
        ):
            with self.subTest(name=name):
                current = copy.deepcopy(original)
                mutate(current["improvement_candidates"][0])
                self.write_json(run_path, current)
                self.assert_invalid("improvement_candidates")

    def test_completion_preserves_proposed_candidate_and_does_not_execute_it(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement_candidate(self.candidate_args())
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run["improvement_candidates"][0]["status"], "proposed")
        self.assertEqual(run["improvement_candidates"][0]["summary"], "reduce repeated setup")
        self.validate()

    def test_generic_completed_transition_is_rejected(self) -> None:
        run_dir = self.prepare_final_review()
        before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("run", "completed"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})

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
        git("init", "-q"); git("config", "user.email", "test@example.invalid"); git("config", "user.name", "Hwahap Test")
        (other / "other").write_text("one\n", encoding="utf-8")
        git("add", "other"); git("commit", "-qm", "one"); base = git("rev-parse", "HEAD")
        (other / "other").write_text("two\n", encoding="utf-8")
        git("commit", "-qam", "two"); target = git("rev-parse", "HEAD")
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

    def test_final_review_aggregate_matrix_is_enforced_before_completion(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        digest = self.snapshot["diff_digest"]

        def attempt(effort: str, status: str, thread: str) -> dict:
            return {"model": "gpt-5.6-sol", "effort": effort, "status": status,
                    "thread_id": thread, "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                    "diff_digest": digest}

        valid = (
            {"status": "pending", "attempts": []},
            {"status": "pending", "attempts": [attempt("ultra", "unsupported", "b")]},
            {"status": "pass", "attempts": [attempt("ultra", "pass", "c")]},
            {"status": "pass", "attempts": [attempt("ultra", "unavailable", "d"), attempt("xhigh", "pass", "e")]},
            {"status": "fail", "attempts": [attempt("ultra", "fail", "f")]},
            {"status": "fail", "attempts": [attempt("ultra", "unsupported", "g"), attempt("xhigh", "unavailable", "h")]},
        )
        for final in valid:
            with self.subTest(final=final):
                self.write_json(run_path, {**json.loads(run_path.read_text()), "final_review": final})
                self.validate()

        invalid = (
            {"status": "done", "attempts": []},
            {"status": "pending", "attempts": [attempt("ultra", "fail", "i")]},
            {"status": "pass", "attempts": [attempt("xhigh", "pass", "j")]},
            {"status": "fail", "attempts": [attempt("ultra", "pass", "k")]},
            {"status": "pass", "attempts": [attempt("ultra", "unavailable", "l"), attempt("xhigh", "fail", "m")]},
            {"status": "fail", "attempts": [attempt("ultra", "fail", "n"), attempt("xhigh", "fail", "o"), attempt("xhigh", "fail", "p")]},
        )
        for final in invalid:
            with self.subTest(final=final):
                self.write_json(run_path, {**json.loads(run_path.read_text()), "final_review": final})
                self.assert_invalid("aggregate matrix")

    def test_final_review_failure_transition_requires_matching_code(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["final_review"] = {"status": "fail", "attempts": [{
            "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail",
            "thread_id": "final-fail", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
            "diff_digest": self.snapshot["diff_digest"],
        }]}
        self.write_json(run_path, run)
        self.validate()
        before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.transition(self.transition_args(
                "run", "awaiting_user", failure_code="HW_MODEL_UNAVAILABLE",
                failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
        self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args(
                "run", "awaiting_user", failure_code="HW_FINAL_REVIEW_FAILED",
                failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
        self.validate()

    def test_final_review_rejects_blocked_and_failed_successors(self) -> None:
        run_dir = self.prepare_final_review()
        for target in ("blocked", "failed"):
            with self.subTest(target=target):
                with self.assertRaises(hwahap_state.HwahapError):
                    hwahap_state.transition(self.transition_args(
                        "run", target, failure_code="HW_FINAL_REVIEW_FAILED",
                        failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))

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

    def test_terminal_run_rejects_unit_successor_in_event_history(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run.update({"status": "blocked", "failure": {
            "code": "HW_IMPLEMENTATION_BLOCKED", "reason": "stop",
            "evidence": ["test"], "recovery": "retry"}})
        self.write_json(run_path, run)
        self.write_json(run_dir / "units" / "unit-1.json", {
            "unit_id": "unit-1", "status": "implementing", "writer": "hwahap-luna-implementer",
            "allowed_paths": ["src"], "acceptance_commands": ["test"], "test_receipts": [],
            "replan_count": 0, "review_history": [], "improvement_history": [],
            "recovery": None, "failure": None,
        })
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "blocked"),
            ("unit-1", "planned", "implementing"),
        ])
        self.assert_invalid("terminal run cannot have unit successors")

    def test_final_review_transition_requires_ready_passed_units_and_preserves_state(self) -> None:
        run_dir = self.init_run()
        contract = self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("run", "implementing", "reviewing"),
        ])
        before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("run", "final_review"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})

        unit = self.passed_unit()
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        run["metrics"]["unit_count"] = 1
        self.write_json(run_path, run)
        self.write_events(run_dir, self.phase_events("passed"))
        self.validate()
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args("run", "final_review"))
        self.validate()
        self.assertEqual(json.loads(run_path.read_text())["status"], "final_review")

    def test_complete_generation_failure_rolls_back_without_report(self) -> None:
        run_dir = self.prepare_final_review()
        before = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        original = hwahap_state.report_module
        class BrokenReport:
            def build_payload(self, *args): return {}
            def canonical_payload_digest(self, payload): return "sha256:" + "b" * 64
            def render_report(self, *args): raise ValueError("forced report failure")
        hwahap_state.report_module = lambda: BrokenReport()
        try:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.complete_run(self.complete_args())
        finally:
            hwahap_state.report_module = original
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual(before, {name: (run_dir / name).read_bytes() for name in before})
        self.assertFalse((run_dir / "report.html").exists())

    def test_complete_event_write_failure_restores_run_and_removes_report(self) -> None:
        run_dir = self.prepare_final_review()
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        report_path = run_dir / "report.html"
        run_before, events_before = run_path.read_bytes(), events_path.read_bytes()
        original_atomic = hwahap_state._atomic_replace_bytes

        def fail_events(path: Path, data: bytes) -> None:
            if path == events_path:
                raise OSError("secret event write")
            return original_atomic(path, data)

        with patch.object(hwahap_state, "_atomic_replace_bytes", new=fail_events):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.complete_run(self.complete_args())
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertNotIn("secret event write", str(raised.exception))
        self.validate()
        self.assertEqual(run_path.read_bytes(), run_before)
        self.assertEqual(events_path.read_bytes(), events_before)
        self.assertFalse(report_path.exists())

    def test_complete_existing_or_symlink_report_does_not_write(self) -> None:
        for symlink in (False, True):
            with self.subTest(symlink=symlink):
                run_dir = self.prepare_final_review()
                report_path = run_dir / "report.html"
                if symlink:
                    target = self.workspace / "outside.html"
                    target.write_text("outside", encoding="utf-8")
                    report_path.symlink_to(target)
                else:
                    report_path.write_text("existing", encoding="utf-8")
                before = (run_dir / "run.json").read_bytes()
                with self.assertRaises(hwahap_state.HwahapError):
                    hwahap_state.complete_run(self.complete_args())
                self.assertEqual((run_dir / "run.json").read_bytes(), before)
                report_path.unlink()

    def test_completed_report_tamper_and_missing_receipt_are_rejected(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        events_path = run_dir / "events.jsonl"
        original_events = events_path.read_bytes()
        events = hwahap_state.parse_events(events_path)
        events[-1]["reason"] = "tampered source"
        events_path.write_text("".join(json.dumps(event) + "\n" for event in events), encoding="utf-8")
        self.assert_invalid("report source digest does not match state")
        events_path.write_bytes(original_events)
        report_path = run_dir / "report.html"
        report_path.write_bytes(report_path.read_bytes() + b"tamper")
        self.assert_invalid("report file digest")
        run = json.loads((run_dir / "run.json").read_text())
        run.pop("report")
        self.write_json(run_dir / "run.json", run)
        self.assert_invalid("report receipt")

    def test_completed_report_rejects_canonical_html_tamper_with_coordinated_hash(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        report_path, data_path, run_path = (run_dir / "report.html", run_dir / "report-data.json", run_dir / "run.json")
        original_html, original_data, original_run = report_path.read_bytes(), data_path.read_bytes(), run_path.read_bytes()
        for replacement in (b"</main>", b"aggregate status: pass"):
            with self.subTest(replacement=replacement):
                if replacement == b"</main>":
                    tampered_html = original_html.replace(replacement, b'<p>extra-canonical-markup</p></main>', 1)
                else:
                    tampered_html = original_html.replace(replacement, b"aggregate status: fail", 1)
                self.assertNotEqual(tampered_html, original_html)
                report_path.write_bytes(tampered_html)
                run = json.loads(original_run)
                run["report"]["html"]["file_sha256"] = "sha256:" + hashlib.sha256(tampered_html).hexdigest()
                self.write_json(run_path, run)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertIn("report HTML does not match canonical renderer", str(raised.exception))
                self.assertEqual(data_path.read_bytes(), original_data)
                report_path.write_bytes(original_html)
                run_path.write_bytes(original_run)

    def test_hardlinked_state_files_are_rejected_without_canary_change(self) -> None:
        for name in ("contract.json", "unit-1.json", "events.jsonl", "run.json"):
            with self.subTest(name=name):
                run_dir = self.prepare_final_review()
                path = run_dir / "units" / name if name == "unit-1.json" else run_dir / name
                before = path.read_bytes()
                victim = self.workspace / ("hardlink-" + name)
                victim.write_bytes(before)
                path.unlink()
                os.link(victim, path)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    if name == "run.json":
                        hwahap_state.complete_run(self.complete_args())
                    else:
                        self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(victim.read_bytes(), before)
                path.unlink()
                hwahap_state._atomic_replace_bytes(path, before)

        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run_path = run_dir / "run.json"
        before = run_path.read_bytes()
        victim = self.workspace / "hardlink-goal-run.json"
        victim.write_bytes(before)
        run_path.unlink()
        os.link(victim, run_path)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.goal_complete_sync(self.goal_complete_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(victim.read_bytes(), before)

    def test_atomic_report_replace_is_safe_if_target_becomes_hardlink(self) -> None:
        run_dir = self.prepare_final_review()
        targets = {run_dir / name for name in hwahap_state._REPORT_RECOVERY_FILES}
        victims: dict[Path, Path] = {}
        original_replace = os.replace

        def race(source: str, destination: str) -> None:
            path = Path(destination)
            if path in targets:
                victim = victims.setdefault(path, self.workspace / ("replace-victim-" + path.name))
                if not victim.exists():
                    victim.write_bytes(b"external-replace-canary")
                if path.exists():
                    path.unlink()
                os.link(victim, path)
            original_replace(source, destination)

        with patch.object(hwahap_state.os, "replace", new=race):
            with redirect_stdout(io.StringIO()):
                hwahap_state.complete_run(self.complete_args())
            with redirect_stdout(io.StringIO()):
                hwahap_state.goal_complete_sync(self.goal_complete_args())
        for victim in victims.values():
            self.assertEqual(victim.read_bytes(), b"external-replace-canary")
        self.validate()

    def test_atomic_report_temp_collision_preserves_preexisting_temp(self) -> None:
        run_dir = self.prepare_final_review()
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        before = (run_path.read_bytes(), events_path.read_bytes())
        old_counter = hwahap_state._REPORT_TEMP_COUNTER
        hwahap_state._REPORT_TEMP_COUNTER = 0
        temp = run_dir / f".run.json.tmp-{os.getpid()}-1"
        temp.write_bytes(b"preexisting-temp-canary")
        try:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.complete_run(self.complete_args())
        finally:
            hwahap_state._REPORT_TEMP_COUNTER = old_counter
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual(temp.read_bytes(), b"preexisting-temp-canary")
        self.assertEqual(before, (run_path.read_bytes(), events_path.read_bytes()))

    def test_report_generated_at_is_bound_to_event_or_goal_receipt(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["report"]["generated_at"] = "tampered-generated-at"
        self.write_json(run_path, run)
        self.assert_invalid("generated_at")

    def test_physical_report_data_preserves_large_histories(self) -> None:
        run_dir = self.prepare_final_review()
        contract = json.loads((run_dir / "contract.json").read_text())
        run = json.loads((run_dir / "run.json").read_text())
        units = [json.loads(path.read_text()) for path in sorted((run_dir / "units").glob("*.json"))]
        events = [{"timestamp": str(index), "type": "state_transition", "sequence": index,
                   "entity": "run", "from": "reviewing", "to": "reviewing", "actor": "stress",
                   "role": "verifier", "reason": f"event-{index}", "input_digest": "sha256:" + "a" * 64,
                   "evidence_refs": [f"event-{index}"], "review_round": 0} for index in range(1, 502)]
        unit = units[0]
        unit["test_receipts"] = [{"test_id": f"receipt-{index}"} for index in range(1, 102)]
        unit["review_history"] = [{"round": index, "changed_paths": [f"review-{index}"]} for index in range(1, 102)]
        unit["improvement_history"] = [{"after_round": index, "action": f"improvement-{index}"} for index in range(1, 102)]
        run["goal_link"]["history"] = [{"reason": f"goal-{index}"} for index in range(1, 102)]
        run["improvement_candidates"] = [{"summary": f"candidate-{index}"} for index in range(1, 102)]
        digests = hwahap_state.report_state_digests(run_dir / "contract.json", run_dir / "events.jsonl", run_dir / "units")
        payload = hwahap_report.build_payload(self.workspace, contract, run, units, events, digests,
                                              hwahap_state.build_scope_audit(run, contract, units))
        data = hwahap_report.canonical_payload_bytes(payload)
        html = hwahap_report.render_report(payload, hwahap_report.canonical_payload_digest(payload))
        (run_dir / "report-data.json").write_bytes(data)
        (run_dir / "report.html").write_bytes(html)
        parsed = json.loads((run_dir / "report-data.json").read_bytes())
        self.assertEqual(len(parsed["timeline"]), 501)
        self.assertEqual(len(parsed["units"][0]["test_receipts"]), 101)
        for sentinel in ("event-501", "receipt-101", "review-101", "improvement-101", "goal-101", "candidate-101"):
            self.assertIn(sentinel, (run_dir / "report-data.json").read_text())
            self.assertIn(sentinel, (run_dir / "report.html").read_text())

    def test_completed_lifecycle_persists_101_valid_improvement_candidates(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        candidates = [{
            "status": "proposed", "summary": f"candidate-{index}",
            "evidence": [f"candidate-evidence-{index}"],
            "expected_effect": f"candidate-effect-{index}",
            "next_action": f"candidate-action-{index}",
        } for index in range(1, 102)]
        run["improvement_candidates"] = candidates
        self.write_json(run_path, run)
        self.validate()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        data_path, report_path = run_dir / "report-data.json", run_dir / "report.html"
        receipt = json.loads(run_path.read_text())["report"]
        data = data_path.read_bytes()
        html = report_path.read_bytes()
        self.assertTrue(data_path.is_file() and not data_path.is_symlink() and data_path.stat().st_nlink == 1)
        self.assertTrue(report_path.is_file() and not report_path.is_symlink() and report_path.stat().st_nlink == 1)
        self.assertEqual(receipt["source_payload_sha256"], "sha256:" + hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt["data"]["file_sha256"], "sha256:" + hashlib.sha256(data).hexdigest())
        self.assertEqual(receipt["html"]["file_sha256"], "sha256:" + hashlib.sha256(html).hexdigest())
        parsed = json.loads(data)
        self.assertEqual(parsed["improvement-candidates"], candidates)
        html_text = html.decode("utf-8")
        for index, summary in ((0, "candidate-1"), (100, "candidate-101")):
            row = (f'<tr><td>/improvement-candidates/{index}/summary</td><td>string</td>'
                   f'<td>&quot;{summary}&quot;</td></tr>')
            self.assertEqual(html_text.count(row), 1)
        self.validate()

    def test_goal_complete_sync_success_updates_provenance_without_event(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        events_before = (run_dir / "events.jsonl").read_bytes()
        report_before = (run_dir / "report.html").read_bytes()
        with redirect_stdout(io.StringIO()):
            hwahap_state.goal_complete_sync(self.goal_complete_args())
        run = json.loads((run_dir / "run.json").read_text())
        current = run["goal_link"]["current"]
        self.assertEqual(current["source"], "codex.update_goal")
        self.assertEqual(current["external_status"], "completed")
        self.assertEqual(current["completion_sync"], "completed")
        self.assertEqual(current["sync_result"], "completed")
        self.assertEqual(len(run["goal_link"]["history"]), 2)
        self.assertEqual(run["metrics"]["token_usage"], {
            "availability": "available", "source": "codex.update_goal", "total": 123, "reason": None})
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), events_before)
        self.assertNotEqual((run_dir / "report.html").read_bytes(), report_before)
        self.assertIn(b"Goal sync result", (run_dir / "report.html").read_bytes())
        self.validate()

    def test_goal_complete_sync_failure_is_not_local_goal_completion(self) -> None:
        run_dir = self.prepare_final_review()
        before_token = json.loads((run_dir / "run.json").read_text())["metrics"]["token_usage"]
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        bad = self.goal_complete_args("failed")
        bad.token_total = 1
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.goal_complete_sync(bad)
        with redirect_stdout(io.StringIO()):
            hwahap_state.goal_complete_sync(self.goal_complete_args("failed"))
        current = json.loads((run_dir / "run.json").read_text())["goal_link"]["current"]
        self.assertEqual(current["external_status"], "active")
        self.assertEqual(current["completion_sync"], "failed")
        self.assertEqual(current["sync_result"], "failed")
        self.assertEqual(json.loads((run_dir / "run.json").read_text())["metrics"]["token_usage"], before_token)
        self.validate()

    def test_goal_complete_sync_already_completed_and_invalid_result(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
            hwahap_state.goal_complete_sync(self.goal_complete_args("already_completed"))
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        self.assertEqual(run["goal_link"]["current"]["sync_result"], "already_completed")
        self.assertIn("already_completed", (run_dir / "report.html").read_text())
        run["goal_link"]["current"]["sync_result"] = "bogus"
        run["goal_link"]["history"][-1]["sync_result"] = "bogus"
        self.write_json(run_path, run)
        self.assert_invalid("sync_result")
        run["goal_link"]["current"].update({"sync_result": "failed", "completion_sync": "completed", "external_status": "completed"})
        run["goal_link"]["history"][-1] = copy.deepcopy(run["goal_link"]["current"])
        self.write_json(run_path, run)
        self.assert_invalid("completion Goal receipt")

    def test_goal_history_rejects_changed_bound_pair_and_update_first(self) -> None:
        run_dir = self.init_run()
        with redirect_stdout(io.StringIO()):
            hwahap_state.goal_sync(self.goal_args("bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64, receipt_sha256="sha256:" + "b" * 64))
            hwahap_state.goal_sync(self.goal_args("bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64, receipt_sha256="sha256:" + "c" * 64))
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["goal_link"]["history"][0]["thread_id"] = "other-thread"
        self.write_json(run_path, run)
        self.assert_invalid("bound thread/objective")
        record = copy.deepcopy(run["goal_link"]["current"])
        record.update({"source": "codex.update_goal", "completion_sync": "failed", "sync_result": "failed", "external_status": "active"})
        run["goal_link"] = {"current": record, "history": [record]}
        self.write_json(run_path, run)
        self.assert_invalid("prior get_goal")

    def test_goal_complete_sync_rejects_wrong_state_or_tampered_report(self) -> None:
        run_dir = self.prepare_final_review()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.goal_complete_sync(self.goal_complete_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        report_path = run_dir / "report.html"
        report_path.write_bytes(report_path.read_bytes() + b"tamper")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.goal_complete_sync(self.goal_complete_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_goal_complete_sync_rolls_back_run_and_report_on_generation_failure(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run_before = (run_dir / "run.json").read_bytes()
        report_before = (run_dir / "report.html").read_bytes()
        events_before = (run_dir / "events.jsonl").read_bytes()
        original = hwahap_state.validate_run
        calls = 0
        def fail_after_write(args: Namespace) -> None:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/credential-canary forced sync failure")
            original(args)
        hwahap_state.validate_run = fail_after_write
        try:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_complete_sync(self.goal_complete_args())
        finally:
            hwahap_state.validate_run = original
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual(str(raised.exception), "Goal completion report generation failed")
        self.assertNotIn("credential-canary", str(raised.exception))
        self.assertNotIn("/private/tmp", str(raised.exception))
        self.assertEqual((run_dir / "run.json").read_bytes(), run_before)
        self.assertEqual((run_dir / "report.html").read_bytes(), report_before)
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), events_before)

    def test_goal_complete_sync_rollback_failure_is_generic_and_attempts_all_files(self) -> None:
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        run_path, report_path = run_dir / "run.json", run_dir / "report.html"
        run_before, report_before = run_path.read_bytes(), report_path.read_bytes()
        original_atomic = hwahap_state._atomic_replace_bytes
        calls: list[Path] = []
        def flaky_write(path: Path, data: bytes) -> None:
            calls.append(path)
            if path == run_path:
                raise OSError("/private/tmp/Authorization: Bearer rollback-canary")
            return original_atomic(path, data)
        original_validate = hwahap_state.validate_run
        validations = 0
        def fail_after_write(args: Namespace) -> None:
            nonlocal validations
            validations += 1
            if validations > 1:
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "/private/tmp/auth-canary")
            original_validate(args)
        hwahap_state.validate_run = fail_after_write
        try:
            with patch.object(hwahap_state, "_atomic_replace_bytes", new=flaky_write):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.goal_complete_sync(self.goal_complete_args())
        finally:
            hwahap_state.validate_run = original_validate
        self.assertEqual(raised.exception.code, "HW_REPORT_GENERATION_FAILED")
        self.assertEqual(str(raised.exception), "Goal completion report generation failed")
        self.assertNotIn("canary", str(raised.exception))
        self.assertIn(run_path, calls)
        self.assertIn(report_path, calls)
        self.assertEqual(report_path.read_bytes(), report_before)
        self.assertEqual(run_path.read_bytes(), run_before)

    def review_round(self, number: int, outcome: str = "fail") -> dict:
        digest = self.snapshot["diff_digest"]
        return {
            "round": number, "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": digest,
            "changed_paths": ["src"], "outcome": outcome,
            "verifier": {"model": "gpt-5.6-luna", "effort": "xhigh", "status": outcome, "thread_id": f"luna-{number}", "diff_digest": digest, "evidence": ["verify"]},
            "scope_reviewer": {"model": "gpt-5.6-terra", "effort": "xhigh", "status": outcome, "thread_id": f"terra-{number}", "diff_digest": digest, "evidence": ["scope"]},
        }

    @staticmethod
    def improvement_record(number: int, kind: str) -> dict:
        return {
            "after_round": number, "kind": kind,
            "failure_signature": "sha256:" + str(number) * 64,
            "root_cause": "failure", "hypothesis": "new strategy", "action": "apply strategy",
            "strategy_digest": "sha256:" + chr(96 + number) * 64,
            "scope_status": "within_contract", "evidence": [f"round-{number}"],
        }

    def test_approved_spec_init_and_validate(self) -> None:
        run_dir = self.init_run()
        self.validate()
        goal_link = json.loads((run_dir / "run.json").read_text())["goal_link"]
        self.assertEqual(goal_link["current"]["mode"], "unobserved")
        self.assertEqual(goal_link["history"], [])
        self.assertEqual(json.loads((run_dir / "contract.json").read_text())["locked"], False)
        self.assertEqual(json.loads((run_dir / "run.json").read_text())["status"], "initialized")
        for directory in (self.workspace / ".hwahap", self.workspace / ".hwahap" / "runs",
                          run_dir, run_dir / "units"):
            self.assertEqual(stat.S_IMODE(directory.stat().st_mode), 0o700)
        for state_file in (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl"):
            self.assertEqual(stat.S_IMODE(state_file.stat().st_mode), 0o600)

    def test_init_requires_git_ignore_and_validation_rejects_public_state(self) -> None:
        (self.workspace / ".gitignore").unlink()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.init_run()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        (self.workspace / ".gitignore").write_text(".hwahap/\n", encoding="utf-8")
        run_dir = self.init_run()
        (run_dir / "run.json").chmod(0o644)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_git_diff_snapshot_binds_exact_commits_trees_bytes_and_paths(self) -> None:
        repo = self.workspace / "snapshot-repo"
        repo.mkdir()
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "Hwahap Test")
        (repo / "src").write_text("base\n", encoding="utf-8")
        git("add", "src")
        git("commit", "-qm", "base")
        base = git("rev-parse", "HEAD")
        (repo / "src").write_text("target\n", encoding="utf-8")
        git("commit", "-qam", "target")
        target = git("rev-parse", "HEAD")
        snapshot = hwahap_state.git_diff_snapshot(repo, base, target)
        self.assertEqual(snapshot["base_commit"], base)
        self.assertEqual(snapshot["target_commit"], target)
        self.assertEqual(snapshot["changed_paths"], ["src"])
        self.assertEqual(snapshot["base_tree"], git("rev-parse", f"{base}^{{tree}}"))
        self.assertEqual(snapshot["target_tree"], git("rev-parse", f"{target}^{{tree}}"))
        self.assertTrue(hwahap_state.SHA256.fullmatch(snapshot["diff_digest"]))
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.git_diff_snapshot(self.workspace, base, target)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_git_diff_snapshot_rejects_tampered_fields_and_refs(self) -> None:
        repo = self.workspace / "snapshot-tamper"
        repo.mkdir()
        def git(*args: str) -> str:
            return subprocess.run(["git", *args], cwd=repo, check=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True).stdout.strip()
        git("init", "-q")
        git("config", "user.email", "test@example.invalid")
        git("config", "user.name", "Hwahap Test")
        (repo / "src").write_text("one\n", encoding="utf-8")
        git("add", "src"); git("commit", "-qm", "one"); base = git("rev-parse", "HEAD")
        (repo / "src").write_text("two\n", encoding="utf-8")
        git("commit", "-qam", "two"); target = git("rev-parse", "HEAD")
        snapshot = hwahap_state.git_diff_snapshot(repo, base, target)
        for field, value in (("diff_digest", "sha256:" + "f" * 64), ("changed_paths", ["other"]),
                             ("base_tree", "0" * 40), ("target_commit", "1" * 40)):
            tampered = {**snapshot, field: value}
            errors: list[str] = []
            hwahap_state.validate_diff_snapshot(tampered, repo, "snapshot", errors)
            self.assertTrue(errors)

    def test_bounded_process_output_rejects_large_or_stalled_processes(self) -> None:
        command = [sys.executable, "-c", "print('x' * 4096)"]
        with self.assertRaises(ValueError):
            hwahap_state._bounded_process_output(command, self.workspace, {"PATH": os.defpath}, 64, 1)
        stalled = [sys.executable, "-c", "import time; time.sleep(2)"]
        with self.assertRaises(subprocess.TimeoutExpired):
            hwahap_state._bounded_process_output(stalled, self.workspace, {"PATH": os.defpath}, 64, 0.05)

    def test_git_snapshot_ignores_redirects_replace_dirty_tree_and_diff_config(self) -> None:
        expected = self.snapshot
        fake_dir = self.workspace / "fake-bin"
        fake_dir.mkdir()
        marker = self.workspace / "fake-git-called"
        fake = fake_dir / "git"
        fake.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n", encoding="utf-8")
        fake.chmod(0o755)
        other = self.workspace / "other-repo"
        other.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=other, check=True, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        with patch.dict(os.environ, {"GIT_DIR": str(other / ".git"), "GIT_WORK_TREE": str(other), "GIT_INDEX_FILE": "bad"}):
            self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
        with patch.dict(os.environ, {"PATH": str(fake_dir) + os.pathsep + os.environ.get("PATH", "")}):
            self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
        self.assertFalse(marker.exists())
        nested = self.workspace / "nested"
        nested.mkdir()
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.git_diff_snapshot(nested, self.base_commit, self.target_commit)
        src = self.workspace / "src"
        src.write_text("dirty\n", encoding="utf-8")
        try:
            subprocess.run(["git", "config", "diff.renames", "true"], cwd=self.workspace, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            subprocess.run(["git", "replace", self.base_commit, self.target_commit], cwd=self.workspace, check=True,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            self.assertEqual(hwahap_state.git_diff_snapshot(self.workspace, self.base_commit, self.target_commit), expected)
        finally:
            subprocess.run(["git", "replace", "-d", self.base_commit], cwd=self.workspace, check=False,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

    def test_init_event_write_failure_removes_only_new_state(self) -> None:
        hwahap_dir, runs_dir = self.workspace / ".hwahap", self.workspace / ".hwahap" / "runs"
        hwahap_dir.mkdir(mode=0o700)
        runs_dir.mkdir(mode=0o700)
        run_dir = runs_dir / "test-goal"
        events_path = run_dir / "events.jsonl"
        with self.fail_atomic_once(events_path, "secret init event write"):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec)))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("secret init event write", str(raised.exception))
        self.assertTrue(hwahap_dir.is_dir())
        self.assertTrue(runs_dir.is_dir())
        self.assertFalse(run_dir.exists())

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

    def test_goal_sync_rejects_rebind_and_rolls_back(self) -> None:
        run_dir = self.init_run()
        first = self.goal_args(
            "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
            receipt_sha256="sha256:" + "b" * 64,
        )
        with redirect_stdout(io.StringIO()):
            hwahap_state.goal_sync(first)
        before = (run_dir / "run.json").read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.goal_sync(self.goal_args(
                "bound", thread_id="other-thread", objective_sha256="sha256:" + "c" * 64,
                receipt_sha256="sha256:" + "d" * 64,
            ))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual((run_dir / "run.json").read_bytes(), before)

        original_validate = hwahap_state.validate_run
        calls = 0
        def fail_after_write(args: Namespace) -> None:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced validation failure")
            original_validate(args)
        hwahap_state.validate_run = fail_after_write
        try:
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.goal_sync(self.goal_args(
                    "no_active_goal", receipt_sha256="sha256:" + "e" * 64,
                ))
        finally:
            hwahap_state.validate_run = original_validate
        self.assertEqual((run_dir / "run.json").read_bytes(), before)

    def test_goal_sync_write_then_raise_restores_state(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        before = run_path.read_bytes()
        with self.fail_atomic_once(run_path, "secret Goal write", write_first=True):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.goal_sync(self.goal_args(
                    "no_active_goal", receipt_sha256="sha256:" + "a" * 64))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("secret Goal write", str(raised.exception))
        self.assertEqual(run_path.read_bytes(), before)

    def test_completed_run_requires_observed_goal_but_allows_bound_pending(self) -> None:
        run_dir = self.init_run()
        contract = self.lock_contract(run_dir)
        unit = self.passed_unit()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run.update({
            "status": "final_review", "completed_at": None,
            "metrics": {**run["metrics"], "unit_count": 1, "review_rounds": 1},
        })
        self.write_json(run_dir / "contract.json", contract)
        self.write_json(run_path, run)
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        transitions = self.phase_events("passed") + [("run", "reviewing", "final_review")]
        self.write_events(run_dir, transitions)
        run["status"] = "completed"
        run["completed_at"] = "2026-08-27T00:00:00Z"
        run["final_review"] = {"status": "pass", "attempts": [{
            "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
            "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
            "diff_digest": self.snapshot["diff_digest"],
        }]}
        self.write_json(run_path, run)
        self.write_events(run_dir, transitions + [("run", "final_review", "completed")])
        self.bind_last_event_digest(run_dir)
        self.assert_invalid("observed Goal")
        run["status"] = "final_review"
        run["completed_at"] = None
        run["final_review"] = {"status": "pending", "attempts": []}
        self.write_json(run_path, run)
        self.write_events(run_dir, transitions)
        with redirect_stdout(io.StringIO()):
            hwahap_state.goal_sync(self.goal_args(
                "bound", thread_id="goal-thread", objective_sha256="sha256:" + "a" * 64,
                receipt_sha256="sha256:" + "b" * 64,
            ))
        run = json.loads(run_path.read_text())
        run["status"] = "completed"
        run["completed_at"] = "2026-08-27T00:00:00Z"
        run["final_review"] = {"status": "pass", "attempts": [{
            "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
            "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
            "diff_digest": self.snapshot["diff_digest"],
        }]}
        self.write_json(run_path, run)
        self.write_events(run_dir, transitions + [("run", "final_review", "completed")])
        self.bind_last_event_digest(run_dir)
        self.write_report_receipt(run_dir)
        self.validate()

    def test_same_spec_init_is_idempotent(self) -> None:
        run_dir = self.init_run()
        before = {name: (run_dir / name).read_bytes() for name in ("contract.json", "run.json")}
        self.init_run()
        after = {name: (run_dir / name).read_bytes() for name in before}
        self.assertEqual(before, after)

    def test_unconfirmed_spec_is_rejected(self) -> None:
        self.spec.write_text("---\ntitle: Test goal\nstatus: draft\n---\n", encoding="utf-8")
        args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")

    def test_invalid_utf8_spec_is_a_stable_spec_error(self) -> None:
        self.spec.write_bytes(b"\xff\xfe\xfd")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id="bad-utf8", spec=str(self.spec)))
        self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
        self.assertIn("spec cannot be read", str(raised.exception))

    def test_spec_read_oserror_does_not_echo_secret_or_create_state(self) -> None:
        sentinel = "SECRET_PATH=/private/tmp/do-not-echo"
        with patch.object(hwahap_state.Path, "read_bytes", side_effect=OSError(sentinel)):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="read-error", spec=str(self.spec)))
        self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
        self.assertEqual(str(raised.exception), "spec cannot be read as approved UTF-8")
        self.assertNotIn(sentinel, str(raised.exception))
        self.assertFalse((self.workspace / ".hwahap").exists())

    def test_installed_agent_read_failures_are_generic_before_run_creation(self) -> None:
        agents = self.workspace / ".codex" / "agents"
        target = agents / "hwahap-luna-verifier.toml"
        original_iterdir, original_read = Path.iterdir, Path.read_bytes
        for kind in ("iterdir", "read"):
            with self.subTest(kind=kind):
                marker = f"Proxy-Authorization: Digest /private/tmp/{kind}-canary"
                def fail_iterdir(path: Path):
                    if path == agents:
                        raise OSError(marker)
                    return original_iterdir(path)
                def fail_read(path: Path, *args: object, **kwargs: object):
                    if path == target:
                        raise OSError(marker)
                    return original_read(path, *args, **kwargs)
                patcher = patch.object(Path, "iterdir", new=fail_iterdir) if kind == "iterdir" else patch.object(Path, "read_bytes", new=fail_read)
                with patcher:
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id=f"bad-{kind}", spec=str(self.spec)))
                self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
                self.assertNotIn(marker, str(raised.exception))
                self.assertFalse((self.workspace / ".hwahap" / "runs" / f"bad-{kind}").exists())

    def test_approved_spec_and_report_validation_failures_are_generic(self) -> None:
        self.init_run()
        marker = "Authorization: Bearer /private/tmp/spec-canary"
        original_read = Path.read_bytes
        def fail_spec(path: Path, *args: object, **kwargs: object):
            if path == self.spec:
                raise OSError(marker)
            return original_read(path, *args, **kwargs)
        with patch.object(Path, "read_bytes", new=fail_spec):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn(marker, str(raised.exception))
        run_dir = self.prepare_final_review()
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        marker = "Proxy-Authorization: Digest /private/tmp/report-canary"
        original_module = hwahap_state.report_module
        class BrokenReport:
            def build_payload(self, *args: object): raise ValueError(marker)
        hwahap_state.report_module = lambda: BrokenReport()
        try:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
        finally:
            hwahap_state.report_module = original_module
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn(marker, str(raised.exception))
        stderr = io.StringIO()
        hwahap_state.report_module = lambda: BrokenReport()
        try:
            with patch.object(sys, "argv", ["hwahap_state.py", "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]):
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main(), 1)
        finally:
            hwahap_state.report_module = original_module
        self.assertNotIn(marker, stderr.getvalue())

    def test_installed_agent_verification_rejects_codex_ancestor_alias(self) -> None:
        project = self.workspace / "alias-project"
        project.mkdir()
        spec = project / "spec.md"
        spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
        external = self.workspace / "external-agents"
        external.mkdir()
        self.install_agents(external)
        (project / ".codex").symlink_to(external / ".codex", target_is_directory=True)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(workspace=str(project), goal_id="alias", spec=str(spec)))
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")

    def test_changed_spec_for_existing_goal_is_rejected(self) -> None:
        self.init_run()
        self.spec.write_text(
            "---\ntitle: Changed goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
            encoding="utf-8",
        )
        args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_RUN_EXISTS")

    def test_agent_profiles_are_required_and_pinned(self) -> None:
        missing = self.workspace / "missing-agents"
        missing.mkdir()
        spec = missing / "spec.md"
        spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(workspace=str(missing), goal_id="test-goal", spec=str(spec)))
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")

        self.init_run()
        profile = self.workspace / ".codex" / "agents" / "hwahap-luna-verifier.toml"
        profile.write_text("name = 'changed'\n", encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
        self.assertIn("agent profile differs", str(raised.exception))

    def test_state_rejects_one_file_hwahap_source_before_init(self) -> None:
        source = self.workspace / "one-profile-source"
        source.mkdir()
        source.joinpath("hwahap-luna-implementer.toml").write_bytes(
            installer.source_profiles()[0][1])
        with patch.object(hwahap_state, "AGENT_PROFILE_DIR", source):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.init_run(Namespace(
                    workspace=str(self.workspace), goal_id="one-source", spec=str(self.spec)))
        self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
        self.assertFalse((self.workspace / ".hwahap").exists())

    def test_state_rejects_extra_hwahap_but_preserves_unrelated_profile(self) -> None:
        agents = self.workspace / ".codex" / "agents"
        for index, name in enumerate(("HWAHAP-extra.toml", "HWAHAP-extra.TOML")):
            (agents / name).write_text('name = "hwahap-extra"\n', encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.init_run(f"extra-{index}")
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
            self.assertFalse((self.workspace / ".hwahap" / "runs" / f"extra-{index}").exists())
            (agents / name).unlink()
        self.init_run()
        unrelated = agents / "user-agent.toml"
        unrelated.write_text('name = "user-agent"\n', encoding="utf-8")
        for name in ("HWAHAP-extra.toml", "HWAHAP-extra.TOML"):
            (agents / name).write_text('name = "hwahap-extra"\n', encoding="utf-8")
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_AGENT_CONFIG_INVALID")
            (agents / name).unlink()
        self.assertEqual(unrelated.read_text(encoding="utf-8"), 'name = "user-agent"\n')

    def test_symlinked_hwahap_is_rejected(self) -> None:
        target = self.workspace / "state-target"
        target.mkdir()
        os.symlink(target, self.workspace / ".hwahap")
        args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_symlink_workspace_is_rejected_before_resolve(self) -> None:
        target = self.workspace / "real-workspace"
        target.mkdir()
        link = self.workspace / "workspace-link"
        link.symlink_to(target, target_is_directory=True)
        args = Namespace(workspace=str(link), goal_id="test-goal", spec=str(self.spec))
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_init_distinguishes_workspace_and_spec_types(self) -> None:
        cases = (
            (self.workspace / "missing-workspace", self.spec, "HW_STATE_INVALID"),
            (self.workspace / "workspace-file", self.spec, "HW_STATE_INVALID"),
            (self.workspace, self.workspace / "spec-directory", "HW_SPEC_UNCONFIRMED"),
        )
        cases[1][0].write_text("not a workspace\n", encoding="utf-8")
        cases[2][1].mkdir()
        for index, (workspace, spec, code) in enumerate(cases):
            with self.subTest(index=index):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.init_run(Namespace(
                        workspace=str(workspace), goal_id=f"type-{index}", spec=str(spec)))
                self.assertEqual(raised.exception.code, code)

    def test_workspace_ancestor_symlink_rejected_by_all_entrypoints_without_writes(self) -> None:
        target_parent = self.workspace / "target-parent"
        real = target_parent / "project"
        real.mkdir(parents=True)
        spec = real / "spec.md"
        spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
        self.install_agents(real)
        hwahap_state.init_run(Namespace(workspace=str(real), goal_id="test-goal", spec=str(spec)))
        run_dir = real / ".hwahap" / "runs" / "test-goal"
        before = {path.relative_to(real): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
        alias_parent = self.workspace / "alias-parent"
        alias_parent.symlink_to(target_parent, target_is_directory=True)
        alias = alias_parent / "project"
        calls = [
            ("init", lambda: hwahap_state.init_run(Namespace(workspace=str(alias), goal_id="test-goal", spec=str(spec)))),
            ("validate", lambda: hwahap_state.validate_run(Namespace(workspace=str(alias), run_id="test-goal"))),
            ("lock", lambda: hwahap_state.lock_contract(Namespace(workspace=str(alias), run_id="test-goal", actor="sol", reason="lock", evidence_ref=["spec.md"]))),
            ("add-unit", lambda: hwahap_state.add_unit(Namespace(workspace=str(alias), run_id="test-goal", unit_id="u", title="u", allowed_path=["src"], acceptance_command=["test"]))),
        ]
        move = self.transition_args("run", "implementing")
        move.workspace = str(alias)
        calls.append(("transition", lambda: hwahap_state.transition(move)))
        for name, call in calls:
            try:
                with redirect_stdout(io.StringIO()):
                    call()
            except hwahap_state.HwahapError as raised:
                self.assertEqual(raised.code, "HW_STATE_INVALID", name)
            else:
                self.fail(name)
            after = {path.relative_to(real): path.read_bytes() for path in run_dir.rglob("*") if path.is_file()}
            self.assertEqual(after, before)

    def test_symlink_spec_and_windows_drive_relative_path_are_rejected(self) -> None:
        source = self.workspace / "real-spec.md"
        source.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
        link = self.workspace / "spec-link.md"
        link.symlink_to(source)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(workspace=str(self.workspace), goal_id="link-spec", spec=str(link)))
        self.assertEqual(raised.exception.code, "HW_SPEC_UNCONFIRMED")
        self.assertFalse((self.workspace / ".hwahap").exists())
        self.assertFalse(hwahap_state.safe_relative_path("C:foo"))

    def test_validate_rechecks_spec_hash_and_frontmatter(self) -> None:
        self.init_run()
        self.spec.write_text(
            "---\ntitle: Test goal\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\nchanged body\n",
            encoding="utf-8",
        )
        self.assert_invalid("approved spec source hash does not match")

    def test_persisted_spec_source_rejects_symlink_before_and_after_lock(self) -> None:
        run_dir = self.init_run()
        original = self.spec.read_bytes()
        target = self.workspace / "spec-target.md"
        target.write_bytes(original)
        for locked in (False, True):
            with self.subTest(locked=locked):
                if self.spec.exists() or self.spec.is_symlink():
                    self.spec.unlink()
                self.spec.symlink_to(target)
                contract_path = run_dir / "contract.json"
                contract = json.loads(contract_path.read_text())
                if locked:
                    for field in hwahap_state.CONTRACT_LISTS:
                        contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
                    contract["locked"] = True
                    contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
                self.write_json(contract_path, contract)
                self.assert_invalid("approved spec source")
                self.spec.unlink()
                self.spec.write_bytes(original)

    def test_persisted_spec_source_rejects_symlinked_ancestor_before_and_after_lock(self) -> None:
        run_dir = self.init_run()
        target = self.workspace / "spec-target"
        target.mkdir()
        (target / "spec.md").write_bytes(self.spec.read_bytes())
        alias = self.workspace / "alias"
        contract_path = run_dir / "contract.json"
        original_contract = json.loads(contract_path.read_text())
        for locked in (False, True):
            with self.subTest(locked=locked):
                if alias.exists() or alias.is_symlink():
                    alias.unlink()
                alias.symlink_to(target, target_is_directory=True)
                contract = copy.deepcopy(original_contract)
                contract["spec"]["source"] = "alias/spec.md"
                if locked:
                    for field in hwahap_state.CONTRACT_LISTS:
                        contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
                    contract["locked"] = True
                    contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
                self.write_json(contract_path, contract)
                self.assert_invalid("approved spec source")

    def test_backslash_paths_are_not_canonical(self) -> None:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        contract = self.lock_contract(run_dir)
        contract["allowed_paths"] = ["src\\file"]
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(contract_path, contract)
        self.assert_invalid("unsafe path")
        contract = self.lock_contract(run_dir)
        unit = self.passed_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        unit["allowed_paths"] = ["src"]
        unit["review_history"][0]["changed_paths"] = ["src\\file"]
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed")])
        self.assert_invalid("diff fields")
        unit["review_history"][0]["changed_paths"] = ["src"]
        unit["allowed_paths"] = ["src\\file"]
        self.write_json(unit_path, unit)
        self.assert_invalid("unsafe allowed path")
        contract["forbidden_changes"] = ["src\\private"]
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(contract_path, contract)
        self.assert_invalid("unsafe path")

    def test_paths_reject_traversal_and_forbidden_overlap(self) -> None:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        contract = self.lock_contract(run_dir)
        for value in ("/absolute", "", ".", "../escape", "src/../escape", "src\\file",
                      "src\x00file", "src\x01file", "src\x1ffile", "src\x7ffile"):
            with self.subTest(contract_path=value):
                current = copy.deepcopy(contract)
                current["allowed_paths"] = [value]
                current["lock_sha256"] = hwahap_state.canonical_contract_digest(current)
                self.write_json(contract_path, current)
                self.assert_invalid("unsafe path")
        contract = self.lock_contract(run_dir)
        unit = self.passed_unit()
        unit["allowed_paths"] = ["src\\file"]
        unit_path = run_dir / "units" / "unit-1.json"
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed")])
        self.assert_invalid("unsafe allowed path")
        unit["allowed_paths"] = ["src"]
        contract["forbidden_changes"] = ["src/private"]
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(contract_path, contract)
        unit["review_history"][0]["changed_paths"] = ["src/private/file"]
        self.write_json(unit_path, unit)
        self.assert_invalid("forbidden_changes")

    def test_same_spec_idempotence_validates_entire_existing_run(self) -> None:
        run_dir = self.init_run()
        args = Namespace(workspace=str(self.workspace), goal_id="test-goal", spec=str(self.spec))
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = []
        self.write_json(run_path, run)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        run["status"] = "initialized"
        self.write_json(run_path, run)
        (run_dir / "events.jsonl").write_text("{bad}\n", encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_all_state_paths_require_real_expected_types(self) -> None:
        init_symlinks = {"hwahap", "runs", "run"}
        for name in ("hwahap", "runs", "run", "units", "contract", "run.json", "events", "unit"):
            with self.subTest(path=name):
                workspace = self.workspace / name
                workspace.mkdir()
                self.install_agents(workspace)
                spec = workspace / "spec.md"
                spec.write_text(self.spec.read_text(encoding="utf-8"), encoding="utf-8")
                hwahap = workspace / ".hwahap"
                if name == "hwahap":
                    target = workspace / "hwahap-target"
                    target.mkdir()
                    os.symlink(target, hwahap)
                elif name == "runs":
                    hwahap.mkdir()
                    target = workspace / "runs-target"
                    target.mkdir()
                    os.symlink(target, hwahap / "runs")
                elif name == "run":
                    (hwahap / "runs").mkdir(parents=True)
                    target = workspace / "run-target"
                    target.mkdir()
                    os.symlink(target, hwahap / "runs" / "test-goal")
                else:
                    args = Namespace(workspace=str(workspace), goal_id="test-goal", spec=str(spec))
                    with redirect_stdout(io.StringIO()):
                        hwahap_state.init_run(args)
                    run_dir = hwahap / "runs" / "test-goal"
                    if name == "units":
                        units = run_dir / "units"
                        units.rmdir()
                        target = workspace / "units-target"
                        target.mkdir()
                        os.symlink(target, units)
                    else:
                        path = {
                            "contract": run_dir / "contract.json",
                            "run.json": run_dir / "run.json",
                            "events": run_dir / "events.jsonl",
                            "unit": run_dir / "units" / "unit-1.json",
                        }[name]
                        target = workspace / f"{name}-target"
                        target.write_text("{}\n", encoding="utf-8")
                        if path.exists():
                            path.unlink()
                        os.symlink(target, path)
                args = Namespace(workspace=str(workspace), goal_id="test-goal", spec=str(spec))
                if name in init_symlinks:
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.init_run(args)
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                else:
                    self.assert_invalid_at(workspace)

    def test_locked_contract_digest_rejects_mutation(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        self.validate()
        contract_path = run_dir / "contract.json"
        contract = json.loads(contract_path.read_text())
        contract["goals"] = ["mutated"]
        self.write_json(contract_path, contract)
        self.assert_invalid("lock_sha256")

    def test_lock_add_unit_and_transition_commands(self) -> None:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        contract = json.loads(contract_path.read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
        self.write_json(contract_path, contract)
        with redirect_stdout(io.StringIO()):
            hwahap_state.lock_contract(Namespace(
                workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                reason="approved contract", evidence_ref=["spec.md"],
            ))
            hwahap_state.add_unit(Namespace(
                workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                title="one observable change", allowed_path=["src"], acceptance_command=["test"],
            ))
            hwahap_state.transition(self.transition_args("run", "implementing"))
            hwahap_state.transition(self.transition_args("unit-1", "implementing"))
            hwahap_state.transition(self.transition_args("run", "reviewing"))
            hwahap_state.transition(self.transition_args("unit-1", "reviewing", review_round=1))
        self.validate()
        self.assertEqual(json.loads((run_dir / "run.json").read_text())["metrics"]["unit_count"], 1)
        self.assertTrue(json.loads(contract_path.read_text())["lock_sha256"].startswith("sha256:"))
        self.assertEqual(json.loads((run_dir / "units" / "unit-1.json").read_text())["improvement_history"], [])
        event_lines = (run_dir / "events.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(line)["sequence"] for line in event_lines], [1, 2, 3, 4, 5])

        unit_path = run_dir / "units" / "unit-1.json"
        before_unit, before_events = unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()
        with self.assertRaises(hwahap_state.HwahapError):
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("unit-1", "passed", review_round=1))
        self.assertEqual(unit_path.read_bytes(), before_unit)
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), before_events)

    def test_lock_restores_all_state_on_event_write_error(self) -> None:
        run_dir = self.init_run()
        contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        contract = json.loads(contract_path.read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
        self.write_json(contract_path, contract)
        state_paths = (contract_path, run_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(events_path, "injected event write"):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.lock_contract(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                    reason="lock", evidence_ref=["contract.json"]))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("injected event write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def prepare_locked_run_for_add_unit(self) -> Path:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        contract = json.loads(contract_path.read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
        self.write_json(contract_path, contract)
        with redirect_stdout(io.StringIO()):
            hwahap_state.lock_contract(Namespace(
                workspace=str(self.workspace), run_id="test-goal", actor="sol-1",
                reason="approved contract", evidence_ref=["spec.md"],
            ))
        return run_dir

    def test_add_unit_path_drift_waits_for_user_and_creates_no_unit(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                         title="outside path", allowed_path=["docs"], acceptance_command=["test"])
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.add_unit(args)
        self.assertEqual(raised.exception.code, "HW_SCOPE_DRIFT")
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "awaiting_user")
        self.assertEqual(run["failure"]["code"], "HW_SCOPE_DRIFT")
        self.assertIn("docs", run["failure"]["evidence"][0])
        self.assertIn("user", run["failure"]["recovery"])
        self.assertIn("Goal", run["failure"]["recovery"])
        self.assertFalse((run_dir / "units" / "unit-1.json").exists())
        event = json.loads((run_dir / "events.jsonl").read_text().splitlines()[-1])
        self.assertEqual({event["entity"], event["from"], event["to"], event["actor"], event["role"]},
                         {"run", "contract_locked", "awaiting_user", "hwahap-sol-orchestrator", "orchestrator"})
        self.validate()

    def test_add_unit_command_drift_records_only_command_digest(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        command = "pytest -k command-drift"
        args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                         title="outside command", allowed_path=["src"], acceptance_command=[command])
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.add_unit(args)
        self.assertEqual(raised.exception.code, "HW_SCOPE_DRIFT")
        run_bytes = (run_dir / "run.json").read_text()
        events_bytes = (run_dir / "events.jsonl").read_text()
        digest = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
        self.assertIn(digest, run_bytes)
        self.assertIn(digest, events_bytes)
        self.assertNotIn(command, run_bytes)
        self.assertNotIn(command, events_bytes)
        self.validate()

    def test_add_unit_scope_drift_rolls_back_run_and_events_on_validation_failure(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        state_paths = (run_dir / "run.json", run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        original_validate = hwahap_state.validate_run
        calls = 0

        def fail_after_initial(namespace: Namespace) -> None:
            nonlocal calls
            calls += 1
            if calls == 2:
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced validation failure")
            original_validate(namespace)

        args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                         title="outside path", allowed_path=["docs"], acceptance_command=["test"])
        with patch.object(hwahap_state, "validate_run", side_effect=fail_after_initial):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
        self.assertFalse((run_dir / "units" / "unit-1.json").exists())

    def test_add_unit_scope_drift_event_write_failure_restores_run(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        state_paths = (contract_path, run_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(events_path, "secret drift event write"):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                    title="outside path", allowed_path=["docs"], acceptance_command=["test"]))
        self.assertEqual(raised.exception.code, "HW_SCOPE_DRIFT")
        self.assertNotIn("secret drift event write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
        self.assertFalse((run_dir / "units" / "unit-1.json").exists())

    def test_add_unit_write_then_raise_restores_state_and_removes_unit(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        contract_path, run_path, events_path = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        unit_path = run_dir / "units" / "unit-1.json"
        state_paths = (contract_path, run_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(run_path, "secret add-unit write", write_first=True):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.add_unit(Namespace(
                    workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                    title="unit", allowed_path=["src"], acceptance_command=["test"]))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("secret add-unit write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
        self.assertFalse(unit_path.exists())

    def test_add_unit_unsafe_inputs_preserve_state_and_terminal_repeat_is_read_only(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        for allowed_path, command in ((["../outside"], "test"), (["src"], "TOKEN=secret test")):
            with self.subTest(allowed_path=allowed_path, command=command):
                args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                                 title="unsafe", allowed_path=allowed_path, acceptance_command=[command])
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(args)
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

        drift_args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                               title="outside path", allowed_path=["docs"], acceptance_command=["test"])
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.add_unit(drift_args)
        terminal = tuple(path.read_bytes() for path in state_paths)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.add_unit(drift_args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), terminal)
        self.validate()

    def test_run_test_is_disabled_before_any_state_or_command_access(self) -> None:
        run_dir = self.prepare_test_unit()
        unit_path, events_path, run_path = (run_dir / "units" / "unit-1.json",
                                            run_dir / "events.jsonl", run_dir / "run.json")
        canary = self.workspace.parent / f"run-test-disabled-canary-{self.workspace.name}"
        canary.mkdir()
        marker = canary / "marker"
        marker.write_text("must-survive", encoding="utf-8")
        commands = (f"rm -rf {canary}", "/bin/sh -c 'touch disabled-canary'",
                    "python3 external-script.py", "TOKEN=secret python3 -c 'print(1)'")
        original_run = subprocess.run
        def unexpected(*args: object, **kwargs: object) -> None:
            raise AssertionError("subprocess.run must not be called")
        subprocess.run = unexpected  # type: ignore[assignment]
        try:
            for command in commands:
                with self.subTest(command=command):
                    unit = json.loads(unit_path.read_text())
                    unit["acceptance_commands"] = [command]
                    self.write_json(unit_path, unit)
                    before = {path: path.read_bytes() for path in (unit_path, events_path, run_path)}
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        hwahap_state.run_test(self.run_test_args())
                    self.assertEqual(raised.exception.code, "HW_TEST_EXECUTION_DISABLED")
                    self.assertEqual(str(raised.exception), "test execution is disabled; use an authorized Luna verifier and record-test-receipt")
                    self.assertEqual({path: path.read_bytes() for path in before}, before)
                    self.assertEqual(marker.read_text(encoding="utf-8"), "must-survive")
        finally:
            subprocess.run = original_run  # type: ignore[assignment]
            marker.unlink(missing_ok=True)
            canary.rmdir()

    def test_record_test_receipt_computes_pass_fail_timeout_fields(self) -> None:
        run_dir = self.prepare_reviewing_test_unit()
        for outcome, overrides in (("pass", {"exit_code": 0}), ("fail", {"execution_receipt_sha256": "sha256:" + "1" * 64, "exit_code": 7}),
                                   ("timeout", {"execution_receipt_sha256": "sha256:" + "2" * 64, "exit_code": None, "timed_out": True})):
            with self.subTest(outcome=outcome), redirect_stdout(io.StringIO()) as output:
                hwahap_state.record_test_receipt(self.record_receipt_args(**overrides))
                self.assertIn(f"status={outcome}", output.getvalue())
        receipt = json.loads((run_dir / "units" / "unit-1.json").read_text())["test_receipts"]
        self.assertEqual([item["test_id"] for item in receipt], ["test-1-1", "test-1-2", "test-1-3"])
        self.assertEqual([item["status"] for item in receipt], ["pass", "fail", "timeout"])
        self.assertTrue(all(item["source"] == "codex.exec_command" and item["observer_role"] == "verifier" for item in receipt))
        self.validate()

    def test_record_test_receipt_rejects_invalid_duplicate_and_wrong_state(self) -> None:
        run_dir = self.prepare_reviewing_test_unit()
        args = self.record_receipt_args()
        bad = (self.record_receipt_args(exit_code=0, timed_out=True),
               self.record_receipt_args(execution_receipt_sha256="bad"),
               self.record_receipt_args(observer_thread_id=""))
        for invalid in bad:
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_test_receipt(invalid)
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_test_receipt(args)
        before = (run_dir / "units" / "unit-1.json").read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_test_receipt(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual((run_dir / "units" / "unit-1.json").read_bytes(), before)
        run = json.loads((run_dir / "run.json").read_text())
        unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
        run["status"], unit["status"] = "implementing", "implementing"
        self.write_json(run_dir / "run.json", run)
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"),
        ])
        self.validate()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_test_receipt(self.record_receipt_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")

    def test_record_test_receipt_rolls_back_and_cli_help_is_available(self) -> None:
        run_dir = self.prepare_reviewing_test_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        run_path = run_dir / "run.json"
        before, run_before = unit_path.read_bytes(), run_path.read_bytes()
        original = hwahap_state.validate_run
        calls = 0
        def fail_after_write(args: Namespace) -> None:
            nonlocal calls
            calls += 1
            if calls > 1:
                raise hwahap_state.HwahapError("HW_STATE_INVALID", "forced receipt validation failure")
            original(args)
        hwahap_state.validate_run = fail_after_write
        try:
            with self.assertRaises(hwahap_state.HwahapError):
                hwahap_state.record_test_receipt(self.record_receipt_args())
        finally:
            hwahap_state.validate_run = original
        self.assertEqual(unit_path.read_bytes(), before)
        self.assertEqual(run_path.read_bytes(), run_before)
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
            hwahap_state.parser().parse_args(["record-test-receipt", "--help"])
        self.assertIn("--execution-receipt-sha256", output.getvalue())
        self.assertIn("--timed-out", output.getvalue())
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()) as output:
            hwahap_state.parser().parse_args(["run-test", "--help"])
        self.assertIn("execution is disabled", output.getvalue())

    def test_record_test_receipt_write_then_raise_restores_state(self) -> None:
        run_dir = self.prepare_reviewing_test_unit()
        contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
        unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
        state_paths = (contract_path, run_path, unit_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(run_path, "secret receipt write", write_first=True):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_test_receipt(self.record_receipt_args())
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("secret receipt write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def test_passed_unit_requires_latest_pass_for_every_command(self) -> None:
        run_dir = self.prepare_test_unit()
        contract = json.loads((run_dir / "contract.json").read_text())
        command_two = "python3 -c \"print(2)\""
        contract["test_commands"].append(command_two)
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(run_dir / "contract.json", contract)
        unit_path = run_dir / "units" / "unit-1.json"
        unit = self.passed_unit()
        unit["status"] = "reviewing"
        unit["acceptance_commands"] = [contract["test_commands"][0], command_two]
        unit["test_receipts"] = unit["test_receipts"][:0]
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing")])
        unit["status"] = "passed"
        unit["test_receipts"] = self.passed_unit()["test_receipts"]
        unit["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(contract["test_commands"][0].encode()).hexdigest()
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed")])
        self.assert_invalid("passing latest receipt")

    def test_passed_unit_receipts_bind_to_final_review(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        unit_path = run_dir / "units" / "unit-1.json"
        base = self.passed_unit()
        self.write_json(unit_path, base)
        self.write_events(run_dir, self.phase_events("passed"))
        self.validate()
        for field, value, message in (("observer_thread_id", "other-verifier", "observer does not match"),
                                      ("diff_digest", "sha256:" + "b" * 64, "diff does not match")):
            with self.subTest(field=field):
                current = copy.deepcopy(base)
                current["test_receipts"][0][field] = value
                self.write_json(unit_path, current)
                self.assert_invalid(message)
        latest_fail = copy.deepcopy(base["test_receipts"][0])
        latest_fail.update({"test_id": "test-1-2", "execution_receipt_sha256": "sha256:" + "1" * 64,
                            "exit_code": 2, "status": "fail"})
        current = copy.deepcopy(base)
        current["test_receipts"].append(latest_fail)
        self.write_json(unit_path, current)
        self.assert_invalid("passing latest receipt")

    def test_execution_receipts_are_unique_across_units_and_record_rejects_duplicate(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        first = self.passed_unit()
        first["status"], first["review_history"] = "planned", []
        second = copy.deepcopy(first)
        second["unit_id"] = "unit-2"
        self.write_json(run_dir / "units" / "unit-1.json", first)
        self.write_json(run_dir / "units" / "unit-2.json", second)
        self.write_events(run_dir, [("run", "initialized", "contract_locked")])
        self.assert_invalid("duplicate execution receipt across units")

        run = json.loads((run_dir / "run.json").read_text())
        run["status"] = "reviewing"
        run["metrics"]["test_runs"] = 1
        first["status"], first["test_receipts"] = "reviewing", []
        second["status"] = "planned"
        self.write_json(run_dir / "run.json", run)
        self.write_json(run_dir / "units" / "unit-1.json", first)
        self.write_json(run_dir / "units" / "unit-2.json", second)
        self.write_events(run_dir, self.phase_events())
        self.validate()
        before = (run_dir / "units" / "unit-1.json").read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_test_receipt(self.record_receipt_args(execution_receipt_sha256="sha256:" + "b" * 64))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual((run_dir / "units" / "unit-1.json").read_bytes(), before)

    def test_test_receipt_tampering_is_rejected(self) -> None:
        run_dir = self.prepare_test_unit()
        run_path = run_dir / "run.json"
        unit_path = run_dir / "units" / "unit-1.json"
        valid = json.loads(unit_path.read_text())
        command = valid["acceptance_commands"][0]
        valid.update(self.passed_unit())
        valid["acceptance_commands"] = [command]
        valid["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        self.write_json(unit_path, valid)
        self.write_events(run_dir, self.phase_events("passed"))
        self.validate()
        valid = json.loads(unit_path.read_text())
        for field, value in (("test_id", "test-1-2"), ("command_sha256", "sha256:" + "a" * 64),
                             ("output_sha256", "not-a-digest"), ("status", "fail"), ("exit_code", 2)):
            with self.subTest(field=field):
                unit = copy.deepcopy(valid)
                unit["test_receipts"][0][field] = value
                self.write_json(unit_path, unit)
                self.assert_invalid("test receipt")

    def test_failure_transition_requires_and_records_evidence(self) -> None:
        run_dir = self.init_run()
        with self.assertRaises(hwahap_state.HwahapError):
            hwahap_state.transition(self.transition_args("run", "blocked"))
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args(
                "run", "blocked", failure_code="HW_IMPLEMENTATION_BLOCKED",
                failure_reason="dependency missing", failure_evidence=["command output"],
                failure_recovery="restore dependency",
            ))
        run = json.loads((run_dir / "run.json").read_text())
        self.assertEqual(run["failure"]["code"], "HW_IMPLEMENTATION_BLOCKED")
        self.validate()

    def test_events_reject_illegal_terminal_and_current_mismatch(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        for name, status, transitions, expected in (
            ("illegal", "contract_locked", [("run", "initialized", "completed")], "illegal transition"),
            ("terminal", "blocked", [("run", "initialized", "blocked"), ("run", "blocked", "implementing")], "terminal state"),
            ("mismatch", "implementing", [("run", "initialized", "contract_locked"), ("run", "initialized", "implementing")], "current state mismatch"),
        ):
            with self.subTest(case=name):
                current = copy.deepcopy(run)
                current["status"] = status
                if status == "blocked":
                    current["failure"] = {"code": "HW_IMPLEMENTATION_BLOCKED", "reason": "test", "evidence": ["test"], "recovery": "retry"}
                self.write_json(run_path, current)
                self.write_events(run_dir, transitions)
                self.assert_invalid(expected)

    def test_review_rejects_wrong_reviewer_digest_and_scope(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        unit = self.passed_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        self.write_json(unit_path, unit)
        self.write_events(run_dir, self.phase_events("passed"))
        self.validate()
        for field, value, expected in (
            ("model", "gpt-5.6-sol", "model or effort"),
            ("diff_digest", "sha256:" + "b" * 64, "diff digest"),
            ("changed_paths", ["outside/file"], "outside unit scope"),
        ):
            with self.subTest(field=field):
                current = copy.deepcopy(unit)
                if field == "changed_paths":
                    current["review_history"][0][field] = value
                else:
                    current["review_history"][0]["verifier"][field] = value
                self.write_json(unit_path, current)
                self.assert_invalid("diff fields" if field == "changed_paths" else expected)

    def test_recursive_improvement_history_allows_recovery_and_rejects_reuse(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        unit_path = run_dir / "units" / "unit-1.json"
        cases = (
            (["fail", "pass"], "passed", 0, ["terra_recovery", ""]),
            (["fail", "fail", "pass"], "passed", 1, ["terra_recovery", "sol_replan", ""]),
            (["fail", "fail", "fail", "pass"], "passed", 2, ["terra_recovery", "sol_replan", "recursive_improvement", ""]),
            (["fail", "fail", "fail", "fail", "pass"], "passed", 3, ["terra_recovery", "sol_replan", "recursive_improvement", "recursive_improvement", ""]),
            (["fail"], "recovery", 0, ["terra_recovery"]),
            (["fail", "fail"], "recovery", 1, ["terra_recovery", "sol_replan"]),
            (["fail"], "awaiting_user", 0, []),
            (["fail"], "reviewing", 0, ["terra_recovery"]),
            (["fail", "pass", "fail"], "replan_required", 1, ["terra_recovery", "sol_replan"]),
        )
        for outcomes, status, replan_count, kinds in cases:
            with self.subTest(outcomes=outcomes, status=status):
                unit = self.passed_unit()
                unit["status"] = status
                unit["review_history"] = [self.review_round(index, outcome) for index, outcome in enumerate(outcomes, 1)]
                unit["replan_count"] = replan_count
                unit["improvement_history"] = [
                    self.improvement_record(index, kind) for index, kind in enumerate(kinds, 1) if kind
                ]
                if status == "passed":
                    final_review = unit["review_history"][-1]
                    unit["test_receipts"][0]["observer_thread_id"] = final_review["verifier"]["thread_id"]
                    unit["test_receipts"][0]["diff_digest"] = final_review["diff_digest"]
                if status == "awaiting_user":
                    unit["failure"] = {
                        "code": "HW_USER_DECISION_REQUIRED", "reason": "need user decision",
                        "evidence": ["review"], "recovery": "ask user",
                    }
                run = json.loads(run_path.read_text())
                run["status"] = {
                    "recovery": "recovering", "replan_required": "replanning",
                    "passed": "reviewing", "reviewing": "reviewing", "awaiting_user": "reviewing",
                }[status]
                run["metrics"]["unit_count"] = 1
                self.write_json(run_path, run)
                self.write_json(unit_path, unit)
                transitions = self.phase_events(status, run["status"])
                self.write_events(run_dir, transitions)
                if status in {"reviewing", "recovery"} and outcomes == ["fail", "fail"]:
                    self.assert_invalid("recovery requires")
                elif status == "reviewing":
                    self.assert_invalid("reviewing cannot end")
                elif status == "replan_required" and outcomes == ["fail", "pass", "fail"]:
                    self.assert_invalid("failed review cannot follow")
                else:
                    self.validate()

        duplicate = self.passed_unit()
        duplicate["review_history"] = [self.review_round(1, "fail"), self.review_round(2, "pass")]
        duplicate["improvement_history"] = [self.improvement_record(1, "terra_recovery")] * 2
        self.write_json(unit_path, duplicate)
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"),
            ("unit-1", "reviewing", "passed"),
        ])
        self.assert_invalid("reused")

    def test_record_improvement_command_rolls_back_invalid_append(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        unit_path = run_dir / "units" / "unit-1.json"
        record = self.improvement_record(1, "terra_recovery")
        args = Namespace(
            workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
            after_round=record["after_round"], kind=record["kind"],
            failure_signature=record["failure_signature"], root_cause=record["root_cause"],
            hypothesis=record["hypothesis"], action=record["action"],
            strategy_digest="not-a-digest", scope_status=record["scope_status"],
            evidence_ref=record["evidence"], actor="sol-1",
        )
        before = unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()
        with self.assertRaises(hwahap_state.HwahapError):
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement(args)
        self.assertEqual((unit_path.read_bytes(), (run_dir / "events.jsonl").read_bytes()), before)
        args.strategy_digest = record["strategy_digest"]
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement(args)
        self.validate()
        current = json.loads(unit_path.read_text())
        self.assertEqual(current["status"], "recovery")
        events = [json.loads(line) for line in (run_dir / "events.jsonl").read_text().splitlines()]
        self.assertEqual(events[-1]["to"], "recovery")

        current["status"] = "reviewing"
        current["review_history"].append(self.review_round(2, "fail"))
        run = json.loads((run_dir / "run.json").read_text())
        run["status"] = "reviewing"
        self.write_json(run_dir / "run.json", run)
        self.write_json(unit_path, current)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
            ("unit-1", "reviewing", "recovery"), ("run", "recovering", "implementing"),
            ("unit-1", "recovery", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"),
        ])
        second = self.improvement_record(2, "sol_replan")
        args.after_round = second["after_round"]
        args.kind = second["kind"]
        args.failure_signature = second["failure_signature"]
        args.root_cause = second["root_cause"]
        args.hypothesis = second["hypothesis"]
        args.action = second["action"]
        args.strategy_digest = second["strategy_digest"]
        args.evidence_ref = second["evidence"]
        with redirect_stdout(io.StringIO()):
            hwahap_state.record_improvement(args)
        self.validate()
        current = json.loads(unit_path.read_text())
        self.assertEqual(current["status"], "replan_required")
        self.assertEqual(current["failure"]["code"], "HW_REPLAN_REQUIRED")
        self.assertEqual(json.loads((run_dir / "events.jsonl").read_text().splitlines()[-1])["to"], "replan_required")

    def test_record_improvement_rejects_traversal_before_external_access(self) -> None:
        run_dir = self.init_run()
        victim_id = f"hwahap-victim-{self.workspace.name}"
        victim = self.workspace.parent / f"{victim_id}.json"
        victim.write_bytes(b"do not modify\n")
        victim_mtime = victim.stat().st_mtime_ns
        state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        traversal = f"../../../../../{victim_id}"
        legacy_unit_path = (run_dir / "units" / f"{traversal}.json").resolve()
        self.assertEqual(legacy_unit_path, victim.resolve())
        args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id=traversal)

        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.record_improvement(args)

        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(victim.read_bytes(), b"do not modify\n")
        self.assertEqual(victim.stat().st_mtime_ns, victim_mtime)
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def test_record_improvement_rejects_preexisting_events_symlink_before_write(self) -> None:
        run_dir = self.init_run()
        unit_path = run_dir / "units" / "unit-1.json"
        unit = self.passed_unit()
        unit["status"] = "reviewing"
        unit["review_history"] = [self.review_round(1, "fail")]
        unit["improvement_history"] = []
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [
            ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"),
        ])
        events_path = run_dir / "events.jsonl"
        victim = self.workspace.parent / f"hwahap-events-victim-{self.workspace.name}.jsonl"
        victim.write_bytes(events_path.read_bytes())
        victim_mtime = victim.stat().st_mtime_ns
        events_path.unlink()
        events_path.symlink_to(victim)
        record = self.improvement_record(1, "terra_recovery")
        args = Namespace(
            workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
            after_round=record["after_round"], kind=record["kind"],
            failure_signature=record["failure_signature"], root_cause=record["root_cause"],
            hypothesis=record["hypothesis"], action=record["action"],
            strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
            evidence_ref=record["evidence"], actor="sol-1",
        )
        before_unit = unit_path.read_bytes()
        before_run = (run_dir / "run.json").read_bytes()
        before_victim = victim.read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            with redirect_stdout(io.StringIO()):
                hwahap_state.record_improvement(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(unit_path.read_bytes(), before_unit)
        self.assertEqual((run_dir / "run.json").read_bytes(), before_run)
        self.assertEqual(victim.read_bytes(), before_victim)
        self.assertEqual(victim.stat().st_mtime_ns, victim_mtime)
        self.assertTrue(events_path.is_symlink())
        self.assertEqual(len(victim.read_bytes().splitlines()), 2)

    def test_transition_restores_all_state_on_event_write_error(self) -> None:
        run_dir = self.prepare_locked_planned_unit()
        contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
        unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
        state_paths = (contract_path, run_path, unit_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(events_path, "injected event write"):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.transition(self.transition_args("unit-1", "implementing"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("injected event write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def test_record_improvement_restores_all_state_on_event_write_error(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        contract_path, run_path = run_dir / "contract.json", run_dir / "run.json"
        unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
        record = self.improvement_record(1, "terra_recovery")
        args = Namespace(
            workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
            after_round=record["after_round"], kind=record["kind"],
            failure_signature=record["failure_signature"], root_cause=record["root_cause"],
            hypothesis=record["hypothesis"], action=record["action"],
            strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
            evidence_ref=record["evidence"], actor="sol-1",
        )
        state_paths = (contract_path, run_path, unit_path, events_path)
        before = tuple(path.read_bytes() for path in state_paths)
        with self.fail_atomic_once(events_path, "injected event write"):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_improvement(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("injected event write", str(raised.exception))
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def test_record_improvement_read_error_is_generic(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        events_path = run_dir / "events.jsonl"
        record = self.improvement_record(1, "terra_recovery")
        args = Namespace(
            workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
            after_round=record["after_round"], kind=record["kind"],
            failure_signature=record["failure_signature"], root_cause=record["root_cause"],
            hypothesis=record["hypothesis"], action=record["action"],
            strategy_digest=record["strategy_digest"], scope_status=record["scope_status"],
            evidence_ref=record["evidence"], actor="sol-1",
        )
        original_read_bytes = Path.read_bytes

        def fail_events(path: Path, *args: object, **kwargs: object) -> bytes:
            if path == events_path:
                raise OSError("secret read detail")
            return original_read_bytes(path, *args, **kwargs)

        with patch.object(Path, "read_bytes", new=fail_events):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                hwahap_state.record_improvement(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("secret read detail", str(raised.exception))

    def prepare_pending_improvement_run(self) -> Path:
        run_dir = self.prepare_reviewing_test_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        unit = json.loads(unit_path.read_text())
        unit["review_history"] = [self.review_round(1, "fail")]
        self.write_json(unit_path, unit)
        self.validate()
        return run_dir

    def test_pending_improvement_blocks_run_replanning_without_writes(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        before = run_path.read_bytes(), events_path.read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            with redirect_stdout(io.StringIO()):
                hwahap_state.transition(self.transition_args("run", "replanning"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertIn("pending improvement", str(raised.exception))
        self.assertEqual((run_path.read_bytes(), events_path.read_bytes()), before)

    def test_pending_improvement_rejects_hand_edited_run_replanning(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "replanning"
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"),
            ("run", "contract_locked", "implementing"),
            ("run", "implementing", "reviewing"),
            ("run", "reviewing", "replanning"),
            ("unit-1", "planned", "implementing"),
            ("unit-1", "implementing", "reviewing"),
        ])
        self.assert_invalid("pending improvement")

    def test_pending_improvement_allows_terminal_failure_with_evidence(self) -> None:
        run_dir = self.prepare_pending_improvement_run()
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args(
                "run", "blocked", failure_code="HW_IMPLEMENTATION_BLOCKED",
                failure_reason="stop", failure_evidence=["review failed"], failure_recovery="ask user"))
        self.validate()

    def prepare_locked_planned_unit(self) -> Path:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        unit = self.passed_unit()
        unit.update({"status": "planned", "review_history": [], "test_receipts": []})
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        self.write_events(run_dir, [("run", "initialized", "contract_locked")])
        return run_dir

    def test_validate_rejects_unit_filename_internal_id_mismatch(self) -> None:
        run_dir = self.prepare_locked_planned_unit()
        unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
        (run_dir / "units" / "unit-1.json").unlink()
        self.write_json(run_dir / "units" / "other-unit.json", unit)
        self.assert_invalid()

    def test_validate_rejects_unsafe_unit_filename_and_internal_id(self) -> None:
        run_dir = self.prepare_locked_planned_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        unit = json.loads(unit_path.read_text())
        unit_path.unlink()
        unsafe_filename = run_dir / "units" / "unit_1.json"
        self.write_json(unsafe_filename, unit)
        self.assert_invalid()

        unsafe_filename.unlink()
        unit["unit_id"] = "../victim"
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        self.assert_invalid()

    def test_validate_rejects_every_unexpected_units_entry(self) -> None:
        run_dir = self.prepare_locked_planned_unit()
        units = run_dir / "units"
        unit_bytes = (units / "unit-1.json").read_bytes()
        entries = (
            ("notes.txt", lambda path: path.write_bytes(b"ignored")),
            ("unsafe_name.json", lambda path: path.write_bytes(unit_bytes)),
            ("link.json", lambda path: path.symlink_to(units / "unit-1.json")),
            ("nested", lambda path: path.mkdir()),
        )
        for name, create in entries:
            with self.subTest(name=name):
                path = units / name
                create(path)
                self.assert_invalid("units contains an unexpected entry")
                path.unlink() if path.is_symlink() or path.is_file() else path.rmdir()

    def test_units_entry_errors_do_not_echo_names_on_validate_or_reinit(self) -> None:
        run_dir = self.init_run()
        for name in ("secret_key=credential-canary.txt", "unsafe_name.json"):
            with self.subTest(name=name):
                path = run_dir / "units" / name
                path.write_bytes(b"canary")
                for action in (lambda: self.validate(), lambda: self.init_run()):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        action()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(name, str(raised.exception))
                    self.assertNotIn(str(self.workspace), str(raised.exception))
                path.unlink()

    def test_validate_events_rejects_unit_phase_before_run_phase(self) -> None:
        for index, (run_status, unit_status, transitions) in enumerate((
            ("implementing", "implementing", [
                ("run", "initialized", "contract_locked"),
                ("unit-1", "planned", "implementing"),
                ("run", "contract_locked", "implementing"),
            ]),
            ("reviewing", "reviewing", [
                ("run", "initialized", "contract_locked"),
                ("run", "contract_locked", "implementing"),
                ("unit-1", "planned", "implementing"),
                ("unit-1", "implementing", "reviewing"),
                ("run", "implementing", "reviewing"),
            ]),
        )):
            run_dir = self.init_run(f"phase-{index}")
            self.lock_contract(run_dir)
            run_path = run_dir / "run.json"
            run = json.loads(run_path.read_text())
            run["status"] = run_status
            run["metrics"]["unit_count"] = 1
            unit = self.passed_unit()
            unit["status"] = unit_status
            self.write_json(run_path, run)
            self.write_json(run_dir / "units" / "unit-1.json", unit)
            self.write_events(run_dir, transitions)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate_at(self.workspace, f"phase-{index}")
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertIn("unit transition requires run status", str(raised.exception))

    def test_recovery_and_replan_can_resume_implementing_and_history_is_required(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "recovering"
        self.write_json(run_path, run)
        unit_path = run_dir / "units" / "unit-1.json"
        unit = self.passed_unit()
        unit["status"] = "recovery"
        unit["review_history"] = [self.review_round(1, "fail")]
        unit["improvement_history"] = [self.improvement_record(1, "terra_recovery")]
        self.write_json(unit_path, unit)
        self.write_events(run_dir, self.phase_events("recovery", "recovering"))
        self.validate()
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args("run", "implementing"))
            hwahap_state.transition(self.transition_args("unit-1", "implementing"))
        self.validate()

        unit["status"] = "implementing"
        unit["improvement_history"] = []
        self.write_json(unit_path, unit)
        self.assert_invalid("requires improvement")

        unit["status"] = "replan_required"
        unit["review_history"] = [self.review_round(1, "fail"), self.review_round(2, "fail")]
        unit["improvement_history"] = [
            self.improvement_record(1, "terra_recovery"), self.improvement_record(2, "sol_replan")
        ]
        unit["replan_count"] = 1
        unit["failure"] = {
            "code": "HW_REPLAN_REQUIRED", "reason": "replan", "evidence": ["review"], "recovery": "retry",
        }
        self.write_json(unit_path, unit)
        run["status"] = "replanning"
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
            ("unit-1", "reviewing", "recovery"), ("run", "recovering", "implementing"),
            ("unit-1", "recovery", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
            ("unit-1", "reviewing", "replan_required"),
        ])
        self.validate()
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args("run", "implementing"))
            hwahap_state.transition(self.transition_args("unit-1", "implementing"))
        self.validate()

    def test_unresolved_unit_blocks_new_unit_but_allows_same_unit_resume(self) -> None:
        run_dir = self.prepare_test_unit()
        run_path = run_dir / "run.json"
        unit_one_path = run_dir / "units" / "unit-1.json"
        unit_two_path = run_dir / "units" / "unit-2.json"
        unit_one = json.loads(unit_one_path.read_text())
        unit_one["status"] = "recovery"
        unit_one["review_history"] = [self.review_round(1, "fail")]
        unit_one["improvement_history"] = [self.improvement_record(1, "terra_recovery")]
        unit_two = copy.deepcopy(unit_one)
        unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [],
                         "improvement_history": [], "replan_count": 0})
        run = json.loads(run_path.read_text())
        run["status"] = "recovering"
        run["metrics"]["unit_count"] = 2
        self.write_json(run_path, run)
        self.write_json(unit_one_path, unit_one)
        self.write_json(unit_two_path, unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "recovering"),
            ("unit-1", "reviewing", "recovery"),
        ])
        self.validate()
        state_paths = (run_path, unit_one_path, unit_two_path, run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("unit-2", "implementing"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args("run", "implementing"))
            hwahap_state.transition(self.transition_args("unit-1", "implementing"))
        self.validate()

        passed = self.passed_unit()
        command = unit_one["acceptance_commands"][0]
        passed["acceptance_commands"] = [command]
        passed["test_receipts"][0]["command_sha256"] = "sha256:" + hashlib.sha256(command.encode()).hexdigest()
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        self.write_json(unit_one_path, passed)
        self.write_events(run_dir, self.phase_events("passed"))
        self.validate()
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args("run", "implementing"))
            hwahap_state.transition(self.transition_args("unit-2", "implementing"))
        self.validate()

    def test_single_writer_rejects_second_activation_and_hand_edited_cardinality(self) -> None:
        run_dir = self.prepare_test_unit()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "implementing"
        self.write_json(run_path, run)
        unit_two = copy.deepcopy(json.loads((run_dir / "units" / "unit-1.json").read_text()))
        unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [], "test_receipts": []})
        self.write_json(run_dir / "units" / "unit-2.json", unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"),
            ("run", "contract_locked", "implementing"), ("unit-1", "planned", "implementing"),
        ])
        # A planned -> implementing command must fail before either state or the event log changes.
        before = {path: path.read_bytes() for path in (
            run_dir / "run.json", run_dir / "units" / "unit-1.json",
            run_dir / "units" / "unit-2.json", run_dir / "events.jsonl")}
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("unit-2", "implementing"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertIn("only one unit", str(raised.exception))
        self.assertEqual({path: path.read_bytes() for path in before}, before)

        # A hand-edited second active unit and matching event must also fail validation.
        unit_two["status"] = "implementing"
        self.write_json(run_dir / "units" / "unit-2.json", unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"),
            ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("unit-2", "planned", "implementing"),
        ])
        self.assert_invalid("only one unit")

    def test_next_unit_waits_for_review_gate_and_overlap_is_invalid(self) -> None:
        run_dir = self.prepare_test_unit()
        run_path = run_dir / "run.json"
        unit_one_path = run_dir / "units" / "unit-1.json"
        unit_two_path = run_dir / "units" / "unit-2.json"
        unit_one = json.loads(unit_one_path.read_text())
        unit_two = copy.deepcopy(unit_one)
        unit_one["status"] = "reviewing"
        unit_two.update({"unit_id": "unit-2", "status": "planned", "review_history": [], "test_receipts": []})
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        run["metrics"]["unit_count"] = 2
        self.write_json(run_path, run)
        self.write_json(unit_one_path, unit_one)
        self.write_json(unit_two_path, unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"),
        ])
        self.validate()
        before = {path: path.read_bytes() for path in (run_path, unit_one_path, unit_two_path, run_dir / "events.jsonl")}
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("unit-2", "implementing"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertIn("only one unit", str(raised.exception))
        self.assertEqual({path: path.read_bytes() for path in before}, before)

        unit_one["status"] = "implementing"
        unit_two["status"] = "reviewing"
        self.write_json(unit_one_path, unit_one)
        self.write_json(unit_two_path, unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("run", "implementing", "reviewing"), ("unit-1", "planned", "implementing"),
            ("unit-2", "planned", "implementing"), ("unit-2", "implementing", "reviewing"),
        ])
        self.assert_invalid("only one unit")

        unit_one["status"] = unit_two["status"] = "reviewing"
        self.write_json(unit_one_path, unit_one)
        self.write_json(unit_two_path, unit_two)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("run", "implementing", "reviewing"), ("unit-1", "planned", "implementing"),
            ("unit-1", "implementing", "reviewing"), ("unit-2", "planned", "implementing"),
            ("unit-2", "implementing", "reviewing"),
        ])
        self.assert_invalid("only one unit")

    def test_final_review_freezes_unit_transition(self) -> None:
        run_dir = self.prepare_final_review()
        unit_path, events_path = run_dir / "units" / "unit-1.json", run_dir / "events.jsonl"
        before = unit_path.read_bytes(), events_path.read_bytes()
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.transition(self.transition_args("unit-1", "reviewing"))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertIn("unit mutation is forbidden", str(raised.exception))
        self.assertEqual((unit_path.read_bytes(), events_path.read_bytes()), before)

    def test_final_review_requires_at_least_one_unit(self) -> None:
        run_dir = self.prepare_final_review()
        (run_dir / "units" / "unit-1.json").unlink()
        self.assert_invalid("final_review requires at least one passed unit")

    def test_final_review_rejects_nonpassed_unit(self) -> None:
        run_dir = self.prepare_final_review()
        unit_path = run_dir / "units" / "unit-1.json"
        unit = json.loads(unit_path.read_text())
        unit["status"] = "reviewing"
        self.write_json(unit_path, unit)
        self.write_events(run_dir, [
            ("unit-1", "planned", "implementing"), ("unit-1", "implementing", "reviewing"),
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("run", "implementing", "reviewing"), ("run", "reviewing", "final_review"),
        ])
        self.assert_invalid("final_review requires a passed unit")

    def test_completed_metrics_include_recursive_review_history(self) -> None:
        run_dir = self.init_run()
        contract = self.lock_contract(run_dir)
        unit = self.passed_unit()
        unit["review_history"] = [
            self.review_round(1, "fail"), self.review_round(2, "fail"), self.review_round(3, "pass")
        ]
        unit["improvement_history"] = [
            self.improvement_record(1, "terra_recovery"), self.improvement_record(2, "sol_replan")
        ]
        unit["replan_count"] = 1
        unit["test_receipts"][0]["observer_thread_id"] = "luna-3"
        unit["test_receipts"][0]["diff_digest"] = self.snapshot["diff_digest"]
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run.update({
            "status": "completed", "completed_at": "2026-08-27T00:00:00Z",
            "final_review": {"status": "pass", "attempts": [{
                "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass",
                "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": self.snapshot["diff_digest"],
            }]},
        })
        run["goal_link"] = self.bound_goal_link()
        run["metrics"].update({
            "unit_count": 1, "review_rounds": 3, "recoveries": 1, "replans": 1,
            "scope_deviations": 0,
        })
        self.write_json(run_dir / "contract.json", contract)
        self.write_json(run_path, run)
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
            ("run", "reviewing", "final_review"),
            ("run", "final_review", "completed"),
        ])
        self.bind_last_event_digest(run_dir)
        self.write_report_receipt(run_dir)
        self.validate()

    def test_locked_contract_requires_all_six_lists(self) -> None:
        run_dir = self.init_run()
        base = json.loads((run_dir / "contract.json").read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            with self.subTest(field=field):
                contract = copy.deepcopy(base)
                contract["locked"] = True
                for name in hwahap_state.CONTRACT_LISTS:
                    contract[name] = ["entry"]
                contract[field] = []
                self.write_json(run_dir / "contract.json", contract)
                self.assert_invalid("locked contract fields must be nonempty")

    def test_passed_unit_requires_distinct_threads_and_same_nonempty_digest(self) -> None:
        run_dir = self.init_run()
        self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        unit_path = run_dir / "units" / "unit-1.json"
        base = self.passed_unit()
        self.write_json(unit_path, base)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
        ])
        self.validate()
        cases = {
            "same thread IDs": {"verifier": {"thread_id": "terra-1"}},
            "empty Terra thread ID": {"scope_reviewer": {"thread_id": ""}},
            "empty Luna digest": {"verifier": {"diff_digest": ""}},
            "different digests": {"scope_reviewer": {"diff_digest": "sha256:" + "b" * 64}},
        }
        for name, changes in cases.items():
            with self.subTest(case=name):
                unit = copy.deepcopy(base)
                for reviewer, values in changes.items():
                    unit["review_history"][0][reviewer].update(values)
                self.write_json(unit_path, unit)
                self.assert_invalid("review" if "thread" in name or "IDs" in name else "diff digest")

    def test_replan_required_needs_review_round_and_failure_evidence(self) -> None:
        run_dir = self.init_run()
        unit_path = run_dir / "units" / "unit-1.json"
        digest = self.snapshot["diff_digest"]
        def failed_round(round_number: int) -> dict:
            return {
                "round": round_number, "diff_snapshot": copy.deepcopy(self.snapshot),
                "diff_digest": digest, "changed_paths": ["src"], "outcome": "fail",
                "verifier": {"model": "gpt-5.6-luna", "effort": "xhigh", "status": "fail", "thread_id": f"luna-{round_number}", "diff_digest": digest, "evidence": ["verify failed"]},
                "scope_reviewer": {"model": "gpt-5.6-terra", "effort": "xhigh", "status": "fail", "thread_id": f"terra-{round_number}", "diff_digest": digest, "evidence": ["scope failed"]},
            }
        def improvement(round_number: int, kind: str) -> dict:
            return {
                "after_round": round_number, "kind": kind,
                "failure_signature": "sha256:" + str(round_number) * 64,
                "root_cause": "review failure", "hypothesis": "new strategy helps",
                "action": "apply bounded recovery", "strategy_digest": "sha256:" + chr(96 + round_number) * 64,
                "scope_status": "within_contract", "evidence": [f"review-{round_number}"],
            }
        base = {
            "unit_id": "unit-1",
            "title": "observable replan change",
            "status": "replan_required",
            "writer": "hwahap-luna-implementer",
            "allowed_paths": ["src"],
            "acceptance_commands": ["test"],
            "test_receipts": copy.deepcopy(self.passed_unit()["test_receipts"]),
            "replan_count": 1,
            "review_history": [failed_round(1), failed_round(2)],
            "improvement_history": [improvement(1, "terra_recovery"), improvement(2, "sol_replan")],
            "failure": {
                "code": "HW_REPLAN_REQUIRED",
                "reason": "scope needs a decision",
                "evidence": ["review-1"],
                "recovery": "ask for replanning",
            },
            "recovery": {"reason": "review failed", "evidence": ["review-1"], "action": "retry once"},
        }
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "replanning"
        self.write_json(run_path, run)
        self.write_json(unit_path, base)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
            ("unit-1", "reviewing", "replan_required"),
        ])
        self.validate()
        recovered = copy.deepcopy(base)
        recovered["status"] = "passed"
        recovered["replan_count"] = 1
        recovered["review_history"].append(failed_round(3))
        recovered["review_history"][2]["outcome"] = "pass"
        recovered["review_history"][2]["verifier"]["status"] = "pass"
        recovered["review_history"][2]["scope_reviewer"]["status"] = "pass"
        recovered["test_receipts"][0]["observer_thread_id"] = "luna-3"
        recovered["test_receipts"][0]["diff_digest"] = self.snapshot["diff_digest"]
        recovered["recovery"] = {"reason": "replanned", "evidence": ["review-2"], "action": "retry"}
        self.write_json(unit_path, recovered)
        run["status"] = "reviewing"
        self.write_json(run_path, run)
        self.write_events(run_dir, [
            ("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"),
            ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("run", "reviewing", "replanning"),
            ("unit-1", "reviewing", "replan_required"), ("run", "replanning", "implementing"),
            ("unit-1", "replan_required", "implementing"), ("run", "implementing", "reviewing"),
            ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"),
        ])
        self.validate()
        for name, changes, expected in (
            ("review round", {"review_history": [failed_round(1)]}, "two failed rounds"),
            ("evidence", {"failure": {"evidence": []}}, "failure evidence"),
            ("recovery", {"failure": {"recovery": ""}}, "failure evidence"),
        ):
            with self.subTest(case=name):
                unit = copy.deepcopy(base)
                if "failure" in changes:
                    unit["failure"].update(changes["failure"])
                else:
                    unit.update(changes)
                self.write_json(unit_path, unit)
                self.assert_invalid(expected)

    def test_completed_run_requires_all_completion_evidence(self) -> None:
        run_dir = self.init_run()
        contract = json.loads((run_dir / "contract.json").read_text())
        for field in hwahap_state.CONTRACT_LISTS:
            contract[field] = ["src" if field == "allowed_paths" else "test" if field == "test_commands" else "entry"]
        contract["locked"] = True
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        run = json.loads((run_dir / "run.json").read_text())
        run.update({
            "status": "completed",
            "completed_at": "2026-08-27T00:00:00Z",
            "final_review": {"status": "pass", "attempts": [{"model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]}]},
        })
        run["goal_link"] = self.bound_goal_link()
        unit = self.passed_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        self.write_json(run_dir / "contract.json", contract)
        self.write_json(run_dir / "run.json", run)
        self.write_json(unit_path, unit)
        run["metrics"].update({"unit_count": 1, "review_rounds": 1})
        self.write_json(run_dir / "run.json", run)
        self.write_events(run_dir, [("run", "initialized", "contract_locked"), ("run", "contract_locked", "implementing"), ("unit-1", "planned", "implementing"), ("run", "implementing", "reviewing"), ("unit-1", "implementing", "reviewing"), ("unit-1", "reviewing", "passed"), ("run", "reviewing", "final_review"), ("run", "final_review", "completed")])
        self.bind_last_event_digest(run_dir)
        self.write_report_receipt(run_dir)
        self.validate()
        fallback = copy.deepcopy(run)
        fallback["final_review"]["attempts"] = [
            {"model": "gpt-5.6-sol", "effort": "ultra", "status": "unsupported", "thread_id": "ultra-1", "evidence": ["unsupported"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]},
            {"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass", "thread_id": "fallback-1", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]},
        ]
        self.write_json(run_dir / "run.json", fallback)
        self.write_report_receipt(run_dir)
        self.validate()
        for name, expected in (
            ("unlocked", "completed run requires"),
            ("no passed unit", "completed run requires"),
            ("final review", "completed run requires"),
            ("completed_at", "completed run requires"),
            ("invalid attempts", "completed final review attempts"),
            ("metrics", "metrics.unit_count"),
            ("deviation", "deviations[1] is incomplete"),
            ("deferred security", "deferred_security[1] is incomplete"),
        ):
            with self.subTest(case=name):
                current_contract = copy.deepcopy(contract)
                current_run = copy.deepcopy(run)
                current_unit = copy.deepcopy(unit)
                if name == "unlocked":
                    current_contract["locked"] = False
                elif name == "no passed unit":
                    current_unit["status"] = "planned"
                elif name == "final review":
                    current_run["final_review"]["status"] = "pending"
                elif name == "completed_at":
                    current_run["completed_at"] = None
                elif name == "invalid attempts":
                    current_run["final_review"]["attempts"] = [{"model": "gpt-5.6-sol", "effort": "xhigh", "status": "pass", "thread_id": "fallback", "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot), "diff_digest": self.snapshot["diff_digest"]}]
                elif name == "metrics":
                    current_run["metrics"]["unit_count"] = 0
                elif name == "deviation":
                    current_run["deviations"] = [{"summary": "incomplete"}]
                else:
                    current_run["deferred_security"] = [{"summary": "incomplete"}]
                self.write_json(run_dir / "contract.json", current_contract)
                self.write_json(run_dir / "run.json", current_run)
                self.write_json(unit_path, current_unit)
                self.assert_invalid(expected)

    def test_malformed_events_file_is_rejected(self) -> None:
        run_dir = self.init_run()
        (run_dir / "events.jsonl").write_text("{not-json}\n", encoding="utf-8")
        self.assert_invalid("invalid events.jsonl")

    def test_invalid_utf8_events_file_is_rejected_without_decode_details(self) -> None:
        run_dir = self.init_run()
        (run_dir / "events.jsonl").write_bytes(b"\xff\xfe\n")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(str(raised.exception), "invalid events.jsonl")
        self.assertNotIn("UnicodeDecodeError", str(raised.exception))

    def test_invalid_utf8_state_json_is_rejected_without_read_details(self) -> None:
        for kind in ("contract", "run", "unit"):
            with self.subTest(kind=kind):
                run_dir = self.init_run(f"invalid-{kind}")
                if kind == "unit":
                    target = run_dir / "units" / "unit-1.json"
                else:
                    target = run_dir / f"{kind}.json"
                hwahap_state._atomic_replace_bytes(target, b"\xff\xfe\n")
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate(f"invalid-{kind}")
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(str(raised.exception), "could not read state JSON")
                self.assertNotIn("UnicodeDecodeError", str(raised.exception))
                self.assertNotIn("codec", str(raised.exception))
                self.assertNotIn(str(target), str(raised.exception))

    def test_add_unit_rejects_invalid_title_before_writing(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        for title in (None, "", " \t", "OPENAI_API_KEY:=do-not-echo"):
            with self.subTest(title=title):
                args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                                 title=title, allowed_path=["src"], acceptance_command=["test"])
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(args)
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("do-not-echo", str(raised.exception))
                self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)
        self.assertFalse((run_dir / "units" / "unit-1.json").exists())

    def test_existing_unit_requires_nonempty_observable_title(self) -> None:
        run_dir = self.prepare_test_unit()
        unit_path = run_dir / "units" / "unit-1.json"
        for title in (None, "", " \t"):
            with self.subTest(title=title):
                unit = json.loads(unit_path.read_text())
                if title is None:
                    unit.pop("title", None)
                else:
                    unit["title"] = title
                self.write_json(unit_path, unit)
                self.assert_invalid("title")

    def test_add_unit_rejects_control_character_paths_before_writing(self) -> None:
        run_dir = self.prepare_locked_run_for_add_unit()
        state_paths = (run_dir / "contract.json", run_dir / "run.json", run_dir / "events.jsonl")
        before = tuple(path.read_bytes() for path in state_paths)
        for path_value in ("src\x00file", "src\x01file", "src\x1ffile", "src\x7ffile"):
            with self.subTest(path=path_value):
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.add_unit(Namespace(
                        workspace=str(self.workspace), run_id="test-goal", unit_id="unit-1",
                        title="observable path change", allowed_path=[path_value],
                        acceptance_command=["test"]))
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(tuple(path.read_bytes() for path in state_paths), before)

    def test_transition_event_requires_structured_evidence(self) -> None:
        run_dir = self.init_run()
        events = run_dir / "events.jsonl"
        events.write_text(json.dumps({"timestamp": "2026-08-27T00:00:00Z"}) + "\n", encoding="utf-8")
        self.assert_invalid("incomplete")
        event = {
            "timestamp": "2026-08-27T00:00:00Z",
            "type": "state_transition",
            "sequence": 1, "entity": "run", "from": "initialized", "to": "contract_locked",
            "actor": "sol-1",
            "role": "orchestrator",
            "reason": "contract locked",
            "input_digest": "sha256:abc",
            "evidence_refs": ["contract.json"],
            "review_round": 0,
        }
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "contract_locked"
        self.write_json(run_path, run)
        events.write_text(json.dumps(event) + "\n", encoding="utf-8")
        self.validate()

    def test_events_require_nonempty_string_evidence_refs(self) -> None:
        run_dir = self.init_run()
        events = run_dir / "events.jsonl"
        event = {
            "timestamp": "2026-08-27T00:00:00Z",
            "type": "state_transition",
            "sequence": 1, "entity": "run", "from": "initialized", "to": "contract_locked",
            "actor": "sol-1",
            "role": "orchestrator",
            "reason": "contract locked",
            "input_digest": "sha256:abc",
            "evidence_refs": ["contract.json"],
            "review_round": 0,
        }
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "contract_locked"
        self.write_json(run_path, run)
        for refs in ([], [""], [123]):
            with self.subTest(refs=refs):
                current = copy.deepcopy(event)
                current["evidence_refs"] = refs
                events.write_text(json.dumps(current) + "\n", encoding="utf-8")
                self.assert_invalid("invalid evidence_refs")

    def test_malformed_nested_state_types_return_hwahap_error(self) -> None:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        run_path = run_dir / "run.json"
        unit_path = run_dir / "units" / "unit-1.json"
        contract = json.loads(contract_path.read_text())
        run = json.loads(run_path.read_text())
        unit = self.passed_unit()
        self.write_json(unit_path, unit)
        for name in ("spec", "roles", "final_review", "reviews", "failure"):
            with self.subTest(field=name):
                current_contract = copy.deepcopy(contract)
                current_run = copy.deepcopy(run)
                current_unit = copy.deepcopy(unit)
                if name == "spec":
                    current_contract["spec"] = []
                    self.write_json(contract_path, current_contract)
                    self.write_json(run_path, current_run)
                    self.write_json(unit_path, current_unit)
                elif name == "roles":
                    current_run["roles"] = []
                    self.write_json(contract_path, current_contract)
                    self.write_json(run_path, current_run)
                    self.write_json(unit_path, current_unit)
                elif name == "final_review":
                    current_run["status"] = "completed"
                    current_run["final_review"] = []
                    self.write_json(contract_path, current_contract)
                    self.write_json(run_path, current_run)
                    self.write_json(unit_path, current_unit)
                elif name == "reviews":
                    current_unit["reviews"] = []
                    self.write_json(contract_path, current_contract)
                    self.write_json(run_path, current_run)
                    self.write_json(unit_path, current_unit)
                else:
                    current_unit["status"] = "failed"
                    current_unit["failure"] = []
                    self.write_json(contract_path, current_contract)
                    self.write_json(run_path, current_run)
                    self.write_json(unit_path, current_unit)
                self.assert_invalid()

    def test_terminal_run_requires_failure_evidence(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "blocked"
        self.write_json(run_path, run)
        self.write_events(run_dir, [("run", "initialized", "blocked")])
        self.assert_invalid("run: invalid failure")
        run["failure"] = {
            "code": "HW_IMPLEMENTATION_BLOCKED",
            "reason": "dependency unavailable",
            "evidence": ["command failed"],
            "recovery": "restore the dependency",
        }
        self.write_json(run_path, run)
        self.validate()

    def test_credential_bearing_commands_are_rejected_at_boundaries(self) -> None:
        run_dir = self.init_run()
        contract_path = run_dir / "contract.json"
        contract = json.loads(contract_path.read_text())
        authentication_url = "https://" + "user" + ":" + "pass" + "@example.invalid"
        private_key = "-----BEGIN " + "PRIVATE KEY-----"
        rejected = (
            "TOKEN=secret pytest", "AWS_SECRET_ACCESS_KEY=secret test",
            "AWS_ACCESS_KEY_ID=secret test", "AWS_SESSION_TOKEN=secret test",
            "GITHUB_TOKEN=secret test", "OPENAI_API_KEY=secret test",
            "FOO_TOKEN=secret test", "FOO_SECRET=secret test",
            "FOO_PASSWORD=secret test", "FOO_API_KEY=secret test",
            "FOO_ACCESS_KEY=secret test", "FOO_PRIVATE_KEY=secret test",
            "env KEY=VALUE pytest", "sh -c 'pytest'", "bash -c 'pytest'",
            "zsh -c 'pytest'", "python3 -c 'x=1'", "pytest; echo x",
            "pytest | cat", "pytest && cat", "pytest > out", "pytest\ncat",
            "pytest $(touch canary)", "sh -lc 'echo shell-wrapper-canary'",
            "env${IFS}KEY=VALUE${IFS}pytest", "pytest --token${IFS}secret",
            "pytest --token\\=secret", "dash -lc pytest", "ksh -c pytest",
            "fish -c pytest", "pytest -lc",
            "-H 'Cookie: sid=secret'", "Authorization: Bearer secret",
            "password=secret", "--api-key secret", authentication_url, private_key,
            "curl https://example.invalid/upload", "python3 tools/exfil.py",
            "make deploy", "git push origin main", "gh pr merge 1",
            "aws sts get-caller-identity", "kubectl get pods", "docker ps",
            "pytest /private/tmp/tests", "pytest ../outside", "npx pytest",
        )
        for command in rejected:
            with self.subTest(command=command):
                current = copy.deepcopy(contract)
                current["test_commands"] = [command]
                self.write_json(contract_path, current)
                before = {path: path.read_bytes() for path in (contract_path, run_dir / "run.json", run_dir / "events.jsonl")}
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.lock_contract(Namespace(workspace=str(self.workspace), run_id="test-goal", actor="sol", reason="lock", evidence_ref=["test"]))
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(str(raised.exception), "test command contains sensitive data")
                self.assertEqual({path: path.read_bytes() for path in before}, before)
        for command in ("python3 -m unittest", "pytest", "make test", "go test ./...",
                        "cargo check", "npm test", "pnpm lint", "swift test"):
            self.assertTrue(hwahap_state.safe_test_command(command))
        self.write_json(contract_path, contract)
        self.lock_contract(run_dir)
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["status"] = "contract_locked"
        self.write_json(run_path, run)
        self.write_events(run_dir, [("run", "initialized", "contract_locked")])
        args = Namespace(workspace=str(self.workspace), run_id="test-goal", unit_id="bad", title="bad", allowed_path=["src"], acceptance_command=["TOKEN=secret test"])
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.add_unit(args)
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        contract = json.loads((run_dir / "contract.json").read_text())
        contract["test_commands"] = ["AWS_SECRET_ACCESS_KEY=secret test"]
        contract["lock_sha256"] = hwahap_state.canonical_contract_digest(contract)
        self.write_json(run_dir / "contract.json", contract)
        self.assert_invalid("test command contains sensitive data")

    def test_command_and_state_credential_gates_cover_secret_key_without_echo(self) -> None:
        for value in ("SECRET_KEY=init-secret", "SERVICE_SECRET_KEY:=init-secret",
                      "OPENAI_API_KEY:=init-secret"):
            with self.subTest(value=value):
                self.assertTrue(hwahap_state.contains_sensitive_data(value))

    def test_assignment_credential_grammar_is_case_insensitive_and_stable(self) -> None:
        rejected = (
            "CLIENT-SECRET=assignment-sentinel", "github-token:=assignment-sentinel",
            "service password : assignment-sentinel", "x-api-key=assignment-sentinel",
            "private key:assignment-sentinel", "client-secret=\nassignment-sentinel",
            "client-secret=\r\nassignment-sentinel", "client-secret=\rassignment-sentinel",
            "client-secret=\\\nassignment-sentinel", "client\fsecret=assignment-sentinel",
            "client\vsecret=assignment-sentinel", "client\u00a0secret=assignment-sentinel",
            "client-secret=[redacted] assignment-sentinel",
            "client-secret=[redacted]\r\n\tresponse=assignment-sentinel",
            "CLIENT-SECRET=<assignment-sentinel>",
            "github-token:=pre<assignment-sentinel>post",
            "service-password:\"<assignment-sentinel>\"",
            "client secret: <assignment-sentinel>",
            "x-api-key=<assignment-sentinel>", "private key:=<assignment-sentinel>",
        )
        for value in rejected:
            with self.subTest(value=value):
                self.assertTrue(hwahap_state.contains_sensitive_data(value))
        for value in ("secret handling", "token usage unavailable", "client-secretary=value", "tokenization=value"):
            self.assertFalse(hwahap_state.contains_sensitive_data(value))
        self.assertFalse(hwahap_state.contains_sensitive_data("client-secret=[redacted]"))
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        original = run_path.read_bytes()
        for value in rejected:
            run = json.loads(original)
            run["goal_link"]["current"]["reason"] = value
            run["goal_link"]["current"]["evidence"] = [value]
            self.write_json(run_path, run)
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                self.validate()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("assignment-sentinel", str(raised.exception))
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(hwahap_state.main([
                    "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
            self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
            run_path.write_bytes(original)

    def test_prefixed_assignment_credentials_are_rejected_in_nested_state(self) -> None:
        values = ("CLIENT-SECRET=state-assignment-sentinel", "github-token:=state-assignment-sentinel",
                  "service-password: state-assignment-sentinel", "client secret=state-assignment-sentinel",
                  "x-api-key=state-assignment-sentinel", "private key=state-assignment-sentinel")
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        original = run_path.read_bytes()
        for value in values:
            with self.subTest(value=value):
                run = json.loads(original)
                run["goal_link"]["current"]["reason"] = value
                self.write_json(run_path, run)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("state-assignment-sentinel", str(raised.exception))
                run_path.write_bytes(original)

    def test_curl_credentials_are_rejected_without_echoing_values(self) -> None:
        continuation = "curl " + chr(92) + "\n  --user audit:linecase URL"
        continuation_crlf = "curl " + chr(92) + "\r\n  --user audit:crlfcase URL"
        values = ("curl -u user:pass URL", "curl -uuser:pass URL", continuation,
                  continuation_crlf,
                  "curl --user user:pass", "curl --user=user:pass",
                  "curl -Uuser:pass URL", "curl --proxy-user user:pass",
                  "curl --proxy-user=user:pass", "curl --oauth2-bearer secret",
                  "curl --oauth2-bearer=secret")
        for value in values:
            with self.subTest(value=value):
                self.assertTrue(hwahap_state.contains_sensitive_data(value))
                self.assertFalse(hwahap_state.safe_test_command(value))
        harmless = "curlish --user documentation"
        self.assertFalse(hwahap_state.contains_sensitive_data(harmless))
        self.assertFalse(hwahap_state.safe_test_command(harmless))
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        for value in values:
            with self.subTest(rejected=value):
                run["goal_link"]["current"]["reason"] = value
                self.write_json(run_path, run)
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn(value, str(raised.exception))

    def test_init_rejects_credential_bearing_title_before_creating_state(self) -> None:
        for title in ("OPENAI_API_KEY:=init-secret", "SECRET_KEY=init-secret"):
            with self.subTest(title=title):
                self.spec.write_text(
                    f"---\ntitle: {title}\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n",
                    encoding="utf-8",
                )
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.init_run(Namespace(
                        workspace=str(self.workspace), goal_id="secret-title", spec=str(self.spec)))
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("init-secret", str(raised.exception))
                self.assertFalse((self.workspace / ".hwahap").exists())

        source = self.workspace / "SECRET_KEY=init-secret.md"
        source.write_text(self.spec.read_text(encoding="utf-8").replace(
            "title: SECRET_KEY=init-secret", "title: Safe source"), encoding="utf-8")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(
                workspace=str(self.workspace), goal_id="secret-source", spec=str(source)))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("init-secret", str(raised.exception))
        self.assertFalse((self.workspace / ".hwahap").exists())

    def test_supported_paths_reject_every_shared_engine_obfuscator(self) -> None:
        marker = "supported-path-canary"
        codepoints = (0x00AD, 0x034F, 0x061C, 0x115F, 0x1160, 0x17B4, 0x17B5,
                      0x180B, 0x200B, 0x2028, 0x2029, 0x2060, 0x3164, 0xFE00,
                      0xFE0F, 0xFFA0, 0xE0100, 0x001F, 0xE000, 0xFDD0, 0xFFFE, 0x1FFFE)
        report_dir = self.init_run("report-probe")
        contract = json.loads((report_dir / "contract.json").read_text())
        clean_run = json.loads((report_dir / "run.json").read_text())
        events = hwahap_state.parse_events(report_dir / "events.jsonl")
        digests = hwahap_state.report_state_digests(report_dir / "contract.json", report_dir / "events.jsonl", report_dir / "units")
        launcher = MODULE_PATH.with_name("hwahap")
        for codepoint in codepoints:
            separator = chr(codepoint)
            raw = f"client{separator}secret: {marker}"
            title = raw
            with self.subTest(codepoint=hex(codepoint)):
                with tempfile.TemporaryDirectory(dir=self.workspace) as directory:
                    workspace = Path(directory)
                    spec = workspace / "spec.md"
                    spec.write_text(f"---\ntitle: {title}\nstatus: prfaq\nconfirmed_at: 2026-08-27T00:00:00Z\n---\n", encoding="utf-8")
                    self.install_agents(workspace)
                    result = subprocess.run(
                        [str(launcher), "init", "--workspace", str(workspace), "--goal-id", "probe", "--spec", str(spec)],
                        cwd=workspace, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    )
                    self.assertEqual(result.returncode, 1)
                    self.assertEqual(result.stderr, "HW_STATE_INVALID: state is invalid\n")
                    self.assertEqual(result.stdout, "")
                    self.assertFalse((workspace / ".hwahap").exists())
                    self.assertNotIn(marker, result.stdout + result.stderr)
                    self.assertNotIn(str(workspace), result.stdout + result.stderr)
                    self.assertNotIn(separator, result.stdout + result.stderr)

                errors: list[str] = []
                hwahap_state.validate_state_strings({"nested": raw}, "probe", errors)
                self.assertTrue(errors)
                self.assertNotIn(marker, " ".join(errors))
                self.assertNotIn(separator, " ".join(errors))
                probe_run = copy.deepcopy(clean_run)
                probe_run["deviations"] = [{"summary": "supported path", "root_cause": "probe", "impact": "none",
                                             "prevention": "test", "evidence": [raw]}]
                payload = hwahap_report.build_payload(self.workspace, contract, probe_run, [], events, digests)
                encoded = hwahap_report.canonical_payload_bytes(payload)
                digest = hwahap_report.canonical_payload_digest(payload)
                self.assertNotIn(marker.encode(), encoded)
                self.assertTrue(hwahap_report.validate_report_data_bytes(encoded, payload, digest))
                html = hwahap_report.render_report(payload, digest)
                self.assertNotIn(marker.encode(), html)
                self.assertTrue(hwahap_report.validate_report_bytes(html, digest, payload))

        for value in ("Authorization: Bearer [redacted]", "Proxy-Authorization: Digest [redacted]", "token_total=3"):
            self.assertFalse(hwahap_state.contains_sensitive_data(value))
            self.assertFalse(hwahap_report.contains_sensitive_data(value))

    def test_nested_string_keys_are_checked_without_echoing_them(self) -> None:
        keys = ("client-secret=whole-feature-key-canary", "Authorization: Bearer key-canary",
                "Proxy-Authorization: Digest proxy-canary", "client\u2028secret=unicode-canary")
        for key in keys:
            with self.subTest(key=key):
                errors: list[str] = []
                hwahap_state.validate_state_strings({"nested": {key: "safe"}}, "probe", errors)
                self.assertTrue(errors)
                self.assertNotIn(key, " ".join(errors))
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["deviations"] = [{"client-secret=whole-feature-key-canary": "safe",
                               "summary": "bounded deviation", "root_cause": "cause",
                               "impact": "none", "prevention": "test", "evidence": ["evidence"]}]
        run["metrics"]["scope_deviations"] = 1
        self.write_json(run_path, run)
        original = {name: (run_dir / name).read_bytes() for name in ("run.json", "events.jsonl")}
        for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
            with self.assertRaises(hwahap_state.HwahapError) as raised:
                operation()
            self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
            self.assertNotIn("whole-feature-key-canary", str(raised.exception))
        self.assertEqual((run_dir / "run.json").read_bytes(), original["run.json"])
        self.assertEqual((run_dir / "events.jsonl").read_bytes(), original["events.jsonl"])
        self.assertFalse((run_dir / "report-data.json").exists())
        self.assertFalse((run_dir / "report.html").exists())

    def test_structured_credential_pairs_are_rejected_without_writing_or_echoing(self) -> None:
        pairs = (
            ("client-secret", "pair-client-secret-canary"),
            ("github-token", "pair-github-token-canary"),
            ("service-password", "pair-service-password-canary"),
            ("client\u200bsecret", "pair-unicode-client-secret-canary"),
        )
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        baseline_run = json.loads(run_path.read_text())
        for key, secret in pairs:
            with self.subTest(key=key):
                run = copy.deepcopy(baseline_run)
                run["deviations"] = [{key: secret, "summary": "bounded deviation",
                                       "root_cause": "cause", "impact": "none",
                                       "prevention": "test", "evidence": ["evidence"]}]
                run["metrics"]["scope_deviations"] = 1
                self.write_json(run_path, run)
                original = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*") if path.is_file()
                }
                for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        operation()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(secret, str(raised.exception))
                current = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*") if path.is_file()
                }
                self.assertEqual(current, original)
                self.assertFalse((run_dir / "report-data.json").exists())
                self.assertFalse((run_dir / "report.html").exists())

    def test_sensitive_key_with_container_value_is_rejected_without_writing(self) -> None:
        run_dir = self.prepare_final_review()
        run_path = run_dir / "run.json"
        baseline_run = json.loads(run_path.read_text())
        for container in (["container-list-raw-canary"],
                          {"nested": {"value": "container-object-raw-canary"}}):
            with self.subTest(container=container):
                run = copy.deepcopy(baseline_run)
                run["deviations"] = [{"client-secret": container, "summary": "bounded deviation",
                                       "root_cause": "cause", "impact": "none",
                                       "prevention": "test", "evidence": ["evidence"]}]
                run["metrics"]["scope_deviations"] = 1
                self.write_json(run_path, run)
                original = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*") if path.is_file()
                }
                canary = json.dumps(container)
                for operation in (self.validate, lambda: hwahap_state.complete_run(self.complete_args())):
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        operation()
                    self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                    self.assertNotIn(canary, str(raised.exception))
                current = {
                    path.relative_to(run_dir): path.read_bytes()
                    for path in run_dir.rglob("*") if path.is_file()
                }
                self.assertEqual(current, original)
                self.assertFalse((run_dir / "report-data.json").exists())
                self.assertFalse((run_dir / "report.html").exists())

        for key, value in (("ordinary", []), ("status", {"nested": 1}), ("summary", None),
                           ("client-secret", "[redacted]")):
            with self.subTest(allowed_pair=(key, value)):
                errors: list[str] = []
                hwahap_state.validate_state_strings({key: value}, "probe", errors)
                self.assertEqual(errors, [])

    def test_frontmatter_does_not_split_line_separator_credentials(self) -> None:
        for codepoint in (0x2028, 0x2029):
            with self.subTest(codepoint=hex(codepoint)):
                raw = f"client{chr(codepoint)}secret: frontmatter-canary"
                self.spec.write_text(f"---\ntitle: {raw}\nstatus: prfaq\nconfirmed_at: now\n---\n", encoding="utf-8")
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.frontmatter(self.spec)
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn("frontmatter-canary", str(raised.exception))

    def test_init_rejects_unsafe_run_id_without_echo_or_write(self) -> None:
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            hwahap_state.init_run(Namespace(
                workspace=str(self.workspace), goal_id="TOKEN=do-not-echo", spec=str(self.spec)))
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertEqual(str(raised.exception), "unsafe run ID")
        self.assertNotIn("do-not-echo", str(raised.exception))
        self.assertFalse((self.workspace / ".hwahap").exists())

    def test_nested_credentials_are_rejected_without_echoing_secret(self) -> None:
        self.assertFalse(hwahap_state.contains_sensitive_data("secret handling"))
        self.assertFalse(hwahap_state.contains_sensitive_data("token usage unavailable"))
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        run = json.loads(run_path.read_text())
        run["goal_link"]["current"]["reason"] = "OPENAI_API_KEY:=do-not-echo"
        self.write_json(run_path, run)
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("do-not-echo", str(raised.exception))

        unit = {"unit_id": "unit-1", "title": "safe", "status": "planned",
                "writer": "hwahap-luna-implementer", "allowed_paths": ["src"],
                "acceptance_commands": ["pytest"], "test_receipts": [],
                "review_history": [], "improvement_history": [], "replan_count": 0,
                "failure": None, "recovery": None}
        run["goal_link"]["current"]["reason"] = "Goal not observed"
        self.write_json(run_path, run)
        self.write_json(run_dir / "units" / "unit-1.json", unit)
        events = hwahap_state.parse_events(run_dir / "events.jsonl")
        events.append({"reason": "Authorization: Bearer do-not-echo", "evidence_refs": ["test"]})
        (run_dir / "events.jsonl").write_text("\n".join(json.dumps(event) for event in events) + "\n")
        with self.assertRaises(hwahap_state.HwahapError) as raised:
            self.validate()
        self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
        self.assertNotIn("do-not-echo", str(raised.exception))

    def test_authorization_header_variants_are_rejected_without_write_or_echo(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        base = json.loads(run_path.read_text())
        variants = (
            "Authorization: Basic state-basic-secret",
            "Authorization: Digest state-digest-secret",
            'Authorization: Digest username="state-user", realm="state-realm", response="state-response"',
            "Authorization: Basic state-lf-secret\nnext-line",
            "Proxy-Authorization: Basic state-crlf-secret\r\nnext-line",
            'Authorization: Digest username="state-fold-user"\r\n  realm="state-fold-realm"\r\n\tresponse="state-fold-response"',
            "Authorization: Basic [redacted]\r\n\tusername=state-basic-redacted-fold-secret",
            "Authorization: Digest [redacted]\n  username=state-digest-redacted-fold-secret",
            "Proxy-Authorization: Basic [redacted]\r\n\tproxy=state-proxy-redacted-fold-secret",
            "Proxy-Authorization: Bearer state-proxy-bearer-secret",
            "Proxy-Authorization: Basic state-proxy-basic-secret",
            "Proxy-Authorization: Digest state-proxy-digest-secret",
            "X-Api-Key: state-api-key-secret",
            "Authorization: Basic [redacted] state-redacted-tail-secret",
            "Authorization: Digest [redacted] state-digest-redacted-tail-secret",
            "Proxy-Authorization: Digest [redacted] state-proxy-redacted-tail-secret",
            "Authorization: Basic state-prefix-secret [redacted]",
            "Authorization: Digest state-digest-prefix-secret [redacted]",
            "Proxy-Authorization: Digest state-proxy-prefix-secret [redacted]",
            "Authorization: Basic state-basic-cr-secret\rnext-line",
            "Authorization: Digest state-digest-cr-secret\r\tresponse=state-digest-cr-folded",
            "Authorization: Bearer state-bearer-cr-secret\rnext-line",
            "Proxy-Authorization: Basic state-proxy-basic-cr-secret\rnext-line",
            "Proxy-Authorization: Digest state-proxy-digest-cr-secret\r\tresponse=state-proxy-digest-cr-folded",
            "Proxy-Authorization: Bearer state-proxy-bearer-cr-secret\rnext-line",
            "Authorization: Basic [redacted]\rresponse=state-basic-redacted-cr-sentinel",
            "Authorization: Digest [redacted]\rresponse=state-digest-redacted-cr-sentinel",
            "Authorization: Bearer [redacted]\rresponse=state-bearer-redacted-cr-sentinel",
            "Proxy-Authorization: Basic [redacted]\rresponse=state-proxy-basic-redacted-cr-sentinel",
            "Proxy-Authorization: Digest [redacted]\rresponse=state-proxy-digest-redacted-cr-sentinel",
            "Proxy-Authorization: Bearer [redacted]\rresponse=state-proxy-bearer-redacted-cr-sentinel",
        )
        for safe in ("Authorization: Basic [redacted]", "Authorization: Digest [redacted]",
                     "Proxy-Authorization: Basic [redacted]", "Proxy-Authorization: Digest [redacted]",
                     "Authorization: Bearer [redacted]", "Proxy-Authorization: Bearer [redacted]"):
            self.assertFalse(hwahap_state.contains_sensitive_data(safe))
        self.assertFalse(hwahap_state.contains_sensitive_data("Authorization: Basic [redacted]\nnext-line"))
        for value in variants:
            with self.subTest(value=value):
                run = copy.deepcopy(base)
                run["goal_link"]["current"]["reason"] = value
                run["goal_link"]["current"]["evidence"] = [value]
                self.write_json(run_path, run)
                before = {path: path.read_bytes() for path in (run_dir / "contract.json", run_path, run_dir / "events.jsonl")}
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn(value, str(raised.exception))
                for token in value.replace('"', '').split():
                    if token not in {"Authorization:", "Proxy-Authorization:", "Basic", "Digest", "Bearer", "next-line"}:
                        self.assertNotIn(token, str(raised.exception))
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_other_header_variants_are_rejected_without_write_or_echo(self) -> None:
        run_dir = self.init_run()
        run_path = run_dir / "run.json"
        base = json.loads(run_path.read_text())
        variants = (
            "X-Api-Key: [redacted]\rresponse=state-api-fold-secret",
            "X-Api-Key: state-api-prefix-secret [redacted]",
            "Cookie: [redacted]\r\n\tstate-cookie-fold-secret",
            "Cookie: state-cookie-prefix-secret [redacted]",
            "Password: [redacted]\rstate-password-fold-secret",
            "Password: state-password-prefix-secret [redacted]",
            "x_api_key=Basic state-x-under-basic-secret",
            "x-api-key=Digest state-x-hyphen-digest-secret",
            "x api key: Bearer state-x-spaced-bearer-secret",
            "x_api_key=Basic [redacted]\nSECRET_KEY=state-overlap-secret",
            "Authorization: Basic <state-auth-angle-prefix>",
            "Proxy-Authorization: Digest state-proxy-angle-prefix<state-proxy-angle-suffix>",
            "X-Api-Key: <state-x-angle-prefix>",
            "x_api_key=Basic state-x-under-angle-prefix<state-x-under-angle-suffix>",
            "Cookie: <state-cookie-angle-prefix>",
            "Password: state-password-angle-prefix<state-password-angle-suffix>",
            "Private-Key: <state-private-angle-prefix>",
        )
        safe_variants = ("X-Api-Key: [redacted]", "Cookie: [redacted]", "Password: [redacted]",
                         "x_api_key=Basic [redacted]", "X_API_KEY=Digest [redacted]",
                         "x api key: Bearer [redacted]")
        for safe in safe_variants:
            self.assertFalse(hwahap_state.contains_sensitive_data(safe))
            run = copy.deepcopy(base)
            run["goal_link"]["current"]["reason"] = safe
            run["goal_link"]["current"]["evidence"] = [safe]
            self.write_json(run_path, run)
            self.validate()
        for value in variants:
            with self.subTest(value=value):
                run = copy.deepcopy(base)
                run["goal_link"]["current"]["reason"] = value
                run["goal_link"]["current"]["evidence"] = [value]
                self.write_json(run_path, run)
                before = {path: path.read_bytes() for path in (run_dir / "contract.json", run_path, run_dir / "events.jsonl")}
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    self.validate()
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertNotIn(value.rsplit(" ", 1)[-1], str(raised.exception))
                self.assertEqual({path: path.read_bytes() for path in before}, before)

    def test_public_cli_errors_are_static_and_registered(self) -> None:
        self.assertTrue(set(hwahap_state.FAILURE_CODES) <= set(hwahap_state.PUBLIC_ERROR_MESSAGES))
        action = next(action for action in hwahap_state.parser()._actions if getattr(action, "choices", None))
        self.assertTrue(all(callable(command.get_default("handler")) for command in action.choices.values()))
        marker = "Authorization: Bearer /private/tmp/cli-canary"
        cases = (["unknown", marker], ["validate"], ["goal-sync", "--mode", "invalid"])
        for argv in cases:
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(hwahap_state.main(argv), 1)
            self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
            self.assertNotIn(marker, stderr.getvalue())
        with patch.object(hwahap_state, "validate_run", side_effect=RuntimeError(marker)):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(hwahap_state.main(["validate", "--workspace", marker, "--run-id", "run"]), 1)
            self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: command failed\n")

    def test_units_read_failure_is_stable_at_cli_boundary(self) -> None:
        self.init_run()
        marker = "Proxy-Authorization: Digest /private/tmp/units-canary"
        before = (self.workspace / ".hwahap" / "runs" / "test-goal" / "run.json").read_bytes()
        with patch.object(hwahap_state, "unit_paths_for_read", side_effect=OSError(marker)):
            stderr = io.StringIO()
            with redirect_stderr(stderr):
                self.assertEqual(hwahap_state.main(["validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
        self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
        self.assertNotIn(marker, stderr.getvalue())
        self.assertEqual((self.workspace / ".hwahap" / "runs" / "test-goal" / "run.json").read_bytes(), before)

    def test_final_review_unit_integrity_survives_later_run_states(self) -> None:
        run_dir = self.prepare_final_review()
        unit_path = run_dir / "units" / "unit-1.json"
        tampered = json.loads(unit_path.read_text())
        tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
        self.write_json(unit_path, tampered)
        self.assert_invalid("final_review requires a passed unit")

        run = json.loads((run_dir / "run.json").read_text())
        run["status"] = "final_review"
        run["final_review"] = {"status": "fail", "attempts": [{
            "model": "gpt-5.6-sol", "effort": "ultra", "status": "fail", "thread_id": "final-fail",
            "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
            "diff_digest": self.snapshot["diff_digest"],
        }]}
        self.write_json((run_dir / "run.json"), run)
        self.write_json(unit_path, self.passed_unit())
        self.write_events(run_dir, self.phase_events("passed") + [("run", "reviewing", "final_review")])
        with redirect_stdout(io.StringIO()):
            hwahap_state.transition(self.transition_args(
                "run", "awaiting_user", failure_code="HW_FINAL_REVIEW_FAILED",
                failure_reason="review failed", failure_evidence=["review"], failure_recovery="ask user"))
        tampered = json.loads(unit_path.read_text())
        tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
        self.write_json(unit_path, tampered)
        self.assert_invalid("final_review requires a passed unit")

        self.write_json(unit_path, self.passed_unit())
        run = json.loads((run_dir / "run.json").read_text())
        run["status"] = "final_review"
        run.pop("failure", None)
        run["final_review"] = {"status": "pass", "attempts": [{
            "model": "gpt-5.6-sol", "effort": "ultra", "status": "pass", "thread_id": "final-pass",
            "evidence": ["review"], "diff_snapshot": copy.deepcopy(self.snapshot),
            "diff_digest": self.snapshot["diff_digest"],
        }]}
        self.write_json(run_dir / "run.json", run)
        self.write_events(run_dir, self.phase_events("passed") + [("run", "reviewing", "final_review")])
        with redirect_stdout(io.StringIO()):
            hwahap_state.complete_run(self.complete_args())
        tampered = json.loads(unit_path.read_text())
        tampered.update({"status": "planned", "review_history": [], "test_receipts": []})
        self.write_json(unit_path, tampered)
        self.assert_invalid("final_review requires a passed unit")

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

    def test_final_snapshot_scope_rejects_malformed_passed_unit_paths_stably(self) -> None:
        run_dir = self.prepare_final_review()
        run_path, events_path = run_dir / "run.json", run_dir / "events.jsonl"
        unit_path = run_dir / "units" / "unit-1.json"
        original_run, original_events = run_path.read_bytes(), events_path.read_bytes()
        for malformed in (None, "src", {"path": "src"}, ["src", None], ["src", {"path": "src"}]):
            with self.subTest(malformed=malformed):
                unit = self.passed_unit()
                unit["allowed_paths"] = malformed
                self.write_json(unit_path, unit)
                self.assert_invalid("allowed_paths")
                stderr = io.StringIO()
                with redirect_stderr(stderr):
                    self.assertEqual(hwahap_state.main([
                        "validate", "--workspace", str(self.workspace), "--run-id", "test-goal"]), 1)
                self.assertEqual(stderr.getvalue(), "HW_STATE_INVALID: state is invalid\n")
                with self.assertRaises(hwahap_state.HwahapError) as raised:
                    hwahap_state.complete_run(self.complete_args())
                self.assertEqual(raised.exception.code, "HW_STATE_INVALID")
                self.assertEqual(run_path.read_bytes(), original_run)
                self.assertEqual(events_path.read_bytes(), original_events)
                self.write_json(unit_path, self.passed_unit())
        errors = []
        hwahap_state.validate_final_review_snapshot_scope(
            {"attempts": [{"diff_snapshot": {"changed_paths": ["src/a"]}}]},
            {"allowed_paths": ["src"], "forbidden_changes": []}, [], errors)
        self.assertTrue(errors)

    def test_scope_audit_is_derived_and_deduplicates_changed_paths(self) -> None:
        run_dir = self.prepare_final_review()
        contract = json.loads((run_dir / "contract.json").read_text())
        run = json.loads((run_dir / "run.json").read_text())
        unit = json.loads((run_dir / "units" / "unit-1.json").read_text())
        snapshot = copy.deepcopy(self.snapshot)
        snapshot["changed_paths"] = ["src", "src", "src/lib"]
        run["final_review"]["attempts"][0]["diff_snapshot"] = snapshot
        audit = hwahap_state.build_scope_audit(run, contract, [unit])
        self.assertEqual([item["path"] for item in audit["paths"]], ["src", "src/lib"])
        self.assertEqual(audit["paths"][0]["matched_contract_rules"], ["src"])
        self.assertEqual(audit["paths"][0]["covering_passed_units"][0]["unit_id"], "unit-1")
        errors: list[str] = []
        hwahap_state.validate_final_review_snapshot_scope(run["final_review"], contract, [unit], errors)
        self.assertFalse(errors)


if __name__ == "__main__":
    unittest.main()
