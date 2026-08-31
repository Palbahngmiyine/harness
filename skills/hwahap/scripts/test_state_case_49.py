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
        def test_invalid_utf8_state_json_is_rejected_without_read_details(self) -> None:
            for kind in ("contract", "run", "unit"):
                with self.subTest(kind=kind):
                    run_id = "test-goal" if kind == "unit" else f"invalid-{kind}"
                    run_dir = self.prepare_test_unit() if kind == "unit" else self.init_run(run_id)
                    if kind == "unit":
                        target = run_dir / "units" / "unit-1.json"
                    else:
                        target = run_dir / f"{kind}.json"
                    target.write_bytes(b"\xff\xfe\n")
                    with self.assertRaises(hwahap_state.HwahapError) as raised:
                        self.validate(run_id)
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
