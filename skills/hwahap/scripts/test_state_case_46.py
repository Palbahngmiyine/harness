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
