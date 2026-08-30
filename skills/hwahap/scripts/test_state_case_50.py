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
