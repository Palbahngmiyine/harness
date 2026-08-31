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


class HwahapStateCase64(StateFixtureMixin01, StateFixtureMixin02, StateFixtureMixin03,
                        StateFixtureMixin04, StateFixtureMixin05, StateFixtureMixin06,
                        unittest.TestCase):
    def test_bounded_process_output_rejects_large_or_stalled_processes(self) -> None:
        command = [sys.executable, "-c", "print('x' * 4096)"]
        with self.assertRaises(ValueError):
            hwahap_state._bounded_process_output(command, self.workspace, {"PATH": os.defpath}, 64, 1)
        stalled = [sys.executable, "-c", "import time; time.sleep(2)"]
        with self.assertRaises(subprocess.TimeoutExpired):
            hwahap_state._bounded_process_output(stalled, self.workspace, {"PATH": os.defpath}, 64, 0.05)
