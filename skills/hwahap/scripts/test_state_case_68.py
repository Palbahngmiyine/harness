"""Case 68: reject unsafe recovery parents before touching the journal."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import hwahap_state as facade


class PrivateRecoveryBoundary(unittest.TestCase):
    def _fixture(self):
        root = Path(tempfile.mkdtemp(prefix="case68-"))
        run = root / "run"
        units = run / "units"
        units.mkdir(mode=0o700, parents=True)
        os.chmod(run, 0o700)
        data = {name: (name + "\n").encode() for name in (
            "contract.json", "run.json", "events.jsonl", "report-data.json", "report.html")}
        for name, value in data.items():
            (run / name).write_bytes(value)
        journal = {"run_id": "run", "files": {
            name: hashlib.sha256(value).hexdigest() for name, value in data.items()}}
        journal_bytes = json.dumps(journal, sort_keys=True).encode()
        (run / ".report-recovery.json").write_bytes(journal_bytes)
        self.assertEqual(json.loads(journal_bytes), journal)
        return root, run, {p: p.read_bytes() for p in run.iterdir() if p.is_file()}

    def _call(self, function, root, run):
        old = facade.state_paths
        facade.state_paths = lambda workspace, run_id: (root / "state", run)
        try:
            if function is facade.validate_run:
                function(argparse.Namespace(workspace=str(root), run_id="run", quiet=True))
            else:
                function(str(root), "run")
        except Exception as error:
            self.assertEqual(getattr(error, "code", None), "HW_STATE_INVALID")
            return 1, "HW_STATE_INVALID: state is invalid\n"
        finally:
            facade.state_paths = old
        self.fail("unsafe recovery boundary was accepted")

    def test_invalid_private_parents_are_rejected_by_both_call_paths(self):
        for fault in ("mode", "symlink", "owner"):
            for function in (facade.command_paths, facade.validate_run):
                root, run, before = self._fixture()
                if fault == "mode":
                    os.chmod(run, 0o755)
                elif fault == "symlink":
                    (run / "units").rmdir()
                    (run / "units").symlink_to("elsewhere")
                else:
                    old = facade.validate_state_directory
                    def reject_owner(path, label):
                        if label == "run":
                            raise facade.HwahapError("HW_STATE_INVALID", "owner")
                        return old(path, label)
                    facade.validate_state_directory = reject_owner
                status, stderr = self._call(function, root, run)
                if fault == "owner":
                    facade.validate_state_directory = old
                self.assertEqual((status, stderr), (1, "HW_STATE_INVALID: state is invalid\n"))
                self.assertEqual(before, {p: p.read_bytes() for p in run.iterdir() if p.is_file()})


if __name__ == "__main__":
    unittest.main()
