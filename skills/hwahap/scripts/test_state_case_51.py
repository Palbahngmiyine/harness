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
            self.assert_invalid("pending report is invalid for terminal run")

        def test_credential_bearing_commands_are_rejected_at_boundaries(self) -> None:
            run_dir = self.init_run()
            contract_path = run_dir / "contract.json"
            contract = json.loads(contract_path.read_text())
            self.bind_goal()
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
                "password=secret", "--api-key secret", "https://user:pass@example.invalid",
                "-----BEGIN PRIVATE KEY-----",
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
                    self.assertEqual(str(raised.exception), "credential-bearing test command is unsafe")
                    self.assertEqual({path: path.read_bytes() for path in before}, before)
            for command in ("python3 -m unittest", "pytest", "make test"):
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
            self.assert_invalid("credential-bearing test command")

        def test_command_and_state_credential_gates_cover_secret_key_without_echo(self) -> None:
            for value in ("SECRET_KEY=init-secret", "SERVICE_SECRET_KEY:=init-secret",
                          "OPENAI_API_KEY:=init-secret"):
                with self.subTest(value=value):
                    self.assertTrue(hwahap_state.credential_bearing_text(value))
