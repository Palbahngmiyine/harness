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
