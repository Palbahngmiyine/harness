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


class HwahapStateCase65(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03,
                        StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06,
                        unittest.TestCase):
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
