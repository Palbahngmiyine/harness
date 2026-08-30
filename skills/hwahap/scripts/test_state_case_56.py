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
            self.assertFalse(hwahap_state.credential_bearing_text("secret handling"))
            self.assertFalse(hwahap_state.credential_bearing_text("token usage unavailable"))
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
