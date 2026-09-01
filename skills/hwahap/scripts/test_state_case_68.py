"""Case 68: reject unsafe recovery parents before touching the journal."""
from __future__ import annotations
from contextlib import nullcontext
try:
    from .test_statekit_base import *
    from .test_statekit_01 import *
except ImportError:
    from test_statekit_base import *
    from test_statekit_01 import *


class HwahapStateCase68(StateFixtureMixin01, unittest.TestCase):
    def _journal(self, run_dir: Path) -> None:
        names = ("run.json", "report-data.json", "report.html", "events.jsonl")
        for name in names[1:3]:
            (run_dir / name).write_bytes(b"{}\n")
        target = {name: (run_dir / name).read_bytes() for name in names}
        originals = {name: (True, target[name]) for name in names}
        journal, _ = hwahap_state._recovery_setup("goal_complete_sync", originals, target)
        path = run_dir / ".report-recovery.json"
        path.write_bytes(journal)
        path.chmod(0o600)
        self.assertIsNotNone(hwahap_state._read_report_recovery_journal(run_dir))

    def _public(self, command: str, run_dir: Path, owner: bool) -> tuple[int, str]:
        args = [command, "--workspace", str(self.workspace), "--run-id", run_dir.name]
        if command == "lock":
            args += ["--actor", "sol-1", "--reason", "test", "--evidence-ref", "test"]
        error = io.StringIO()
        owner_os = hwahap_state.validate_state_directory.__globals__["os"]
        owner_patch = patch.object(owner_os, "geteuid", return_value=os.geteuid() + 1)
        with (owner_patch if owner else nullcontext()), patch.object(
                hwahap_state, "_recover_report_transaction", side_effect=AssertionError), redirect_stderr(error):
            status = hwahap_state.main(args)
        return status, error.getvalue()

    def test_private_recovery_boundary(self) -> None:
        tracked = (".report-recovery.json", "contract.json", "run.json", "events.jsonl",
                   "report-data.json", "report.html")
        for fault in ("mode", "symlink", "owner"):
            for command in ("validate", "lock"):
                run = self.init_run(f"case68-{fault}-{command}")
                self._journal(run)
                before = {name: (run / name).read_bytes() for name in tracked}
                if fault == "mode":
                    os.chmod(run, 0o755)
                elif fault == "symlink":
                    (run / "units").rmdir()
                    (run / "units").symlink_to("missing")
                status, stderr = self._public(command, run, fault == "owner")
                self.assertEqual((status, stderr), (1, "HW_STATE_INVALID: state is invalid\n"))
                self.assertEqual(before, {name: (run / name).read_bytes() for name in tracked})


if __name__ == "__main__":
    unittest.main()
